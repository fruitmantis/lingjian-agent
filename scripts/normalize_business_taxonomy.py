"""Explicit, backed-up UPDATE-only repair of an existing development database.
Never imports application initialization or seed code. No schema operations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from datetime import datetime, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.business_taxonomy import classify, tokens

FIELDS={'partners':{'industries':'industry','service_areas':'region'},
        'demand_profiles':{'industry_tags':'industry','region_tags':'region'},
        'project_opportunities':{'industry':'industry','region':'region'}}

def digest(value): return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()

def state(conn, exclude_fields=False):
    result={}
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        cols=[x[1] for x in conn.execute(f'PRAGMA table_info("{table}")')]
        if exclude_fields: cols=[x for x in cols if x not in FIELDS.get(table,{})]
        query=','.join('"'+x+'"' for x in cols)
        rows=conn.execute(f'SELECT {query} FROM "{table}"').fetchall()
        result[table]={'count':len(rows),'hash':digest(sorted([list(r) for r in rows],key=lambda r:json.dumps(r,default=str)))}
    return result

def checks(conn):
    return {'integrity':conn.execute('PRAGMA integrity_check').fetchall(),
            'foreign_keys':conn.execute('PRAGMA foreign_key_check').fetchall(),
            'schema_hash':digest(conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name').fetchall())}

def plan(conn):
    changes=[];pending=[]
    for table,fields in FIELDS.items():
        for col,kind in fields.items():
            for row_id,value in conn.execute(f'SELECT id,"{col}" FROM "{table}"').fetchall():
                known,unknown=classify(value,kind)
                if unknown:pending.append({'table':table,'id':row_id,'field':col,'values':unknown})
                # Preserve unresolved tokens and unknown sentinels verbatim; only deterministic aliases change.
                revised=[]
                for token in tokens(value):
                    normalized,unresolved=classify(token,kind)
                    for x in normalized or unresolved or [token]:
                        if x not in revised:revised.append(x)
                new=','.join(revised)
                if value is not None and new!=value:
                    changes.append({'table':table,'id':row_id,'field':col,'before':value,'after':new})
    return changes,pending

def update_transaction(conn,changes,before,inject_after=None):
    conn.execute('BEGIN IMMEDIATE')
    try:
        if state(conn)!=before: raise RuntimeError('Database changed after backup; retry with a fresh snapshot')
        baseline=checks(conn);other=state(conn,True)
        for n,c in enumerate(changes,1):
            if c['field'] not in FIELDS.get(c['table'],{}): raise ValueError('Column outside UPDATE allowlist')
            cursor=conn.execute(f'UPDATE "{c["table"]}" SET "{c["field"]}"=? WHERE id=? AND "{c["field"]}" IS ?', (c['after'],c['id'],c['before']))
            if cursor.rowcount!=1: raise RuntimeError('Concurrent update conflict')
            if inject_after==n: raise RuntimeError('Synthetic fault injection')
        if checks(conn)!=baseline or state(conn,True)!=other:raise RuntimeError('Integrity, foreign keys, schema or unrelated data changed')
        conn.commit()
    except BaseException:
        conn.rollback();raise

def run(db,apply=False):
    db=Path(db).absolute(); root=Path(__file__).resolve().parents[1]
    # Restrict real execution to this worktree's exact dev DB; /tmp only for tests.
    if db != root/'.isolation/runtime/dev/app.db' and not db.is_relative_to('/tmp'):
        raise ValueError('Only the current independent dev DB or /tmp test databases are allowed')
    if not db.is_file() or db.resolve()!=db or db.stat().st_nlink!=1:
        raise ValueError('Database must exist and cannot use symlinks or hardlinks')
    mode='rw' if apply else 'ro';conn=sqlite3.connect(f'file:{db}?mode={mode}',uri=True,isolation_level=None)
    try:
        conn.execute('PRAGMA foreign_keys=ON')
        baseline=checks(conn)
        if baseline['integrity']!=[('ok',)]:raise RuntimeError('Integrity check failed')
        before=state(conn);changes,pending=plan(conn)
        result={'database':str(db),'mode':mode,'before':before,'checks_before':baseline,'updates':changes,'pending':pending}
        if apply:
            stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            folder=db.parent/'taxonomy-backups';folder.mkdir(exist_ok=True,mode=0o700)
            backup=folder/f'before-{stamp}.db'
            with sqlite3.connect(backup) as snapshot:conn.backup(snapshot)
            os.chmod(backup,0o600)
            # Ensure the snapshot and checked baseline are the same live state.
            with sqlite3.connect(f'file:{backup}?mode=ro',uri=True) as snapshot:
                if state(snapshot)!=before: raise RuntimeError('Backup baseline drift; no updates applied')
            update_transaction(conn,changes,before)
            result.update(backup=str(backup),after=state(conn),checks_after=checks(conn),transaction='COMMITTED')
            report=folder/f'updates-{stamp}.json';report.write_text(json.dumps(result,ensure_ascii=False,indent=2));os.chmod(report,0o600)
            print(json.dumps({'updated_fields':len(changes),'pending_fields':len(pending),'report':str(report),'backup':str(backup)},ensure_ascii=False))
        return result
    finally:conn.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--apply',action='store_true');args=p.parse_args()
    result=run(args.db,args.apply)
    if not args.apply:print(json.dumps(result,ensure_ascii=False,indent=2))
