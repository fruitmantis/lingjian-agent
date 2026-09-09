"""One-shot, lossless v12 SQLite -> empty PostgreSQL import. No seeds or source writes.

DATABASE_URL must point to the explicitly prepared PostgreSQL database. Existing
PostgreSQL tables are never dropped, emptied or overwritten by this tool.
"""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sqlalchemy import inspect,select,text,func
from backend.app.postgres_storage import engine_for
from backend.app.storage_models import metadata,create_postgres_schema


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def ordered_tables():
    remaining=dict(metadata.tables);done=set();result=[]
    while remaining:
        ready=[name for name,table in remaining.items() if {fk.column.table.name for fk in table.foreign_keys}-{name}<=done]
        if not ready:
            # The existing Plan/Run/Version pointers form a cycle. Only that cycle
            # uses deferred checks, which are forced immediate before commit.
            ready=[name for name in ('development_plans','development_runs','development_versions') if name in remaining]
        if not ready:raise RuntimeError('Unknown schema dependency cycle')
        for name in ready:result.append(remaining.pop(name));done.add(name)
    return result


def digest(rows):
    encoded=[json.dumps(list(row),ensure_ascii=False,separators=(',',':'),allow_nan=False) for row in rows]
    return hashlib.sha256('\n'.join(sorted(encoded)).encode()).hexdigest()


def source_inventory(source):
    with closing(sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True)) as c:
        if c.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:raise RuntimeError('Source integrity check failed')
        if c.execute('PRAGMA foreign_key_check').fetchall():raise RuntimeError('Source has foreign-key violations; no import allowed')
        names={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if names!=set(metadata.tables):raise RuntimeError('Source table set differs from the v12 mapping')
        if c.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()!=('12',):raise RuntimeError('Only schema v12 is supported')
        inventory={}
        for table in metadata.tables.values():
            actual=[row[1] for row in c.execute('PRAGMA table_info("'+table.name+'")')]
            expected=list(table.c.keys())
            legacy_errors=(table.name=='match_records' and actual==[name for name in expected if name!='last_error_details'])
            if actual!=expected and not legacy_errors:raise RuntimeError('Column mapping differs for '+table.name)
            # Older v12 snapshots have no diagnostics; keep the source read-only.
            projection=','.join('NULL AS "'+name+'"' if legacy_errors and name=='last_error_details' else '"'+name+'"' for name in expected)
            rows=c.execute('SELECT '+projection+' FROM "'+table.name+'"').fetchall()
            inventory[table.name]={'count':len(rows),'sha256':digest(rows)}
        return inventory


def reconcile(connection,inventory):
    result={}
    for table in metadata.tables.values():
        rows=connection.execute(select(table)).all()
        value={'count':len(rows),'sha256':digest(rows)}
        if value!=inventory[table.name]:raise RuntimeError('Data reconciliation failed for '+table.name)
        result[table.name]=value
    invalid=connection.exec_driver_sql("SELECT count(*) FROM pg_constraint WHERE connamespace=current_schema()::regnamespace AND contype='f' AND NOT convalidated").scalar()
    if invalid:raise RuntimeError('Unvalidated PostgreSQL foreign keys')
    return result


def import_snapshot(source,url,*,fault=None):
    """One transaction includes DDL, all rows, checks and sequence alignment."""
    inventory=source_inventory(source)
    engine=engine_for(url)
    with engine.begin() as conn:
        # Serializes concurrent invocations before checking the target's emptiness.
        conn.exec_driver_sql('SELECT pg_advisory_xact_lock(179183913)')
        if inspect(conn).get_table_names():
            raise RuntimeError('Target must be empty; refusing to overwrite existing PostgreSQL tables')
        create_postgres_schema(conn)
        conn.exec_driver_sql('SET CONSTRAINTS ALL DEFERRED')
        with closing(sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True)) as src:
            src.row_factory=sqlite3.Row
            for table in ordered_tables():
                cursor=src.execute('SELECT * FROM "'+table.name+'"')
                while batch:=cursor.fetchmany(500):conn.execute(table.insert(),[dict(row) for row in batch])
                if fault:fault(table.name)
        conn.exec_driver_sql('SET CONSTRAINTS ALL IMMEDIATE')
        sequence_count=0
        for table in metadata.tables.values():
            for column in table.c:
                if column.identity is not None:
                    seq=conn.execute(text('SELECT pg_get_serial_sequence(:table,:column)'),{'table':table.name,'column':column.name}).scalar()
                    maximum=conn.execute(select(func.max(column))).scalar()
                    conn.execute(text('SELECT setval(CAST(:sequence AS regclass),:value,:called)'),{'sequence':seq,'value':max(1,maximum or 0),'called':maximum is not None})
                    sequence_count+=1
        compared=reconcile(conn,inventory)
    # A fresh connection verifies the committed database, not an in-transaction view.
    with engine.connect() as conn:
        conn.exec_driver_sql('SET TRANSACTION READ ONLY')
        reconcile(conn,inventory)
    return {'tables':compared,'table_count':len(compared),'row_count':sum(t['count'] for t in compared.values()),'aligned_sequences':sequence_count,'foreign_keys':'PASS','row_value_reconciliation':'PASS'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path)
    parser.add_argument('--evidence-dir',required=True,type=Path)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    source=args.source.resolve();out=args.evidence_dir.resolve()
    if not source.is_file() or args.source.is_symlink() or source.stat().st_nlink!=1:raise RuntimeError('Source must be an existing regular database file')
    if out.exists():raise RuntimeError('Use a new evidence directory; existing evidence is never overwritten')
    out.mkdir(parents=True,mode=0o700)
    before=sha(source);backup=out/'sqlite-consistent-backup.db'
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(backup)) as dst:src.backup(dst)
    os.chmod(backup,0o600)
    inventory=source_inventory(backup)
    result={'source':str(source),'backup':str(backup),'source_sha256_before':before,'source_sha256_after':sha(source),'backup_sha256':sha(backup),'source_tables':inventory,'checked_at':datetime.now(timezone.utc).isoformat(),'status':'PREFLIGHT PASS'}
    if before!=result['source_sha256_after']:raise RuntimeError('Source changed while backing up; stop application writes and retry')
    if args.apply:
        url=os.environ.get('DATABASE_URL','')
        if not url.startswith(('postgresql://','postgresql+psycopg://')):raise RuntimeError('Explicit PostgreSQL DATABASE_URL required')
        result['import']=import_snapshot(backup,url)
        result['status']='IMPORTED AND RECONCILED'
    result['source_sha256_after']=sha(source)
    if result['source_sha256_after']!=before:raise RuntimeError('Source changed; do not switch runtime')
    with os.fdopen(os.open(out/'migration-result.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({'status':result['status'],'table_count':len(inventory),'row_count':sum(t['count'] for t in inventory.values()),'source_unchanged':True,'report':str(out/'migration-result.json')}))

if __name__=='__main__':
    try:main()
    except Exception as error:
        # Never echo driver errors containing SQL parameters or a connection URL.
        print('Migration blocked ('+type(error).__name__+'). No runtime switch was performed.',file=sys.stderr)
        raise SystemExit(1)
