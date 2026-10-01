"""Explicit, backed-up UPDATE-only repair of an existing development database.
Never imports application initialization or seed code. No schema operations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from sqlalchemy import inspect
import sys
from datetime import datetime, timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.app.business_taxonomy import classify, tokens
from backend.app.postgres_storage import connect, validated_url

FIELDS={'partners':{'industries':'industry','service_areas':'region'},
        'demand_profiles':{'industry_tags':'industry','region_tags':'region'},
        'project_opportunities':{'industry':'industry','region':'region'}}

def digest(value): return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()

def state(conn, exclude_fields=False):
    result={};inspector=inspect(conn.connection)
    for table in inspector.get_table_names():
        cols=[c['name'] for c in inspector.get_columns(table)]
        if exclude_fields:cols=[c for c in cols if c not in FIELDS.get(table,{})]
        query=','.join('"'+c+'"' for c in cols)
        rows=[list(r) for r in conn.execute(f'SELECT {query} FROM "{table}"')]
        result[table]={'count':len(rows),'hash':digest(sorted(rows,key=lambda r:json.dumps(r,default=str)))}
    return result

def checks(conn):
    inspector=inspect(conn.connection)
    return {table:{'columns':[c['name'] for c in inspector.get_columns(table)],
                   'foreign_keys':inspector.get_foreign_keys(table)} for table in inspector.get_table_names()}

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
    conn.lock_writer()
    try:
        if state(conn)!=before: raise RuntimeError('Database changed after backup; retry with a fresh snapshot')
        baseline=checks(conn);other=state(conn,True)
        for n,c in enumerate(changes,1):
            if c['field'] not in FIELDS.get(c['table'],{}): raise ValueError('Column outside UPDATE allowlist')
            cursor=conn.execute(f'UPDATE "{c["table"]}" SET "{c["field"]}"=? WHERE id=? AND "{c["field"]}" IS NOT DISTINCT FROM ?', (c['after'],c['id'],c['before']))
            if cursor.rowcount!=1: raise RuntimeError('Concurrent update conflict')
            if inject_after==n: raise RuntimeError('Synthetic fault injection')
        if checks(conn)!=baseline or state(conn,True)!=other:raise RuntimeError('Integrity, foreign keys, schema or unrelated data changed')
        conn.commit()
    except BaseException:
        conn.rollback();raise

def run(url,apply=False,backup_dir=None):
    parsed=validated_url(url)
    if parsed.host not in ('127.0.0.1','localhost') or parsed.database not in ('banfei_agent','banfei_agent_test','banfei_validation'):
        raise ValueError('Only the local PostgreSQL application or dedicated validation database is allowed')
    with connect(url,readonly=True) as conn:
        before=state(conn);changes,pending=plan(conn);baseline=checks(conn)
    result={'mode':'apply' if apply else 'readonly','before':before,'updates':changes,'pending':pending,'checks_before':baseline}
    if not apply:return result
    if backup_dir is None:raise ValueError('A new private backup directory is required')
    folder=Path(backup_dir);folder.mkdir(mode=0o700,parents=True,exist_ok=False)
    backup=folder/'before.pgdump'
    env=dict(os.environ,PGHOST=parsed.host,PGPORT=str(parsed.port or 5432),PGDATABASE=parsed.database,PGUSER=parsed.username or '',PGPASSWORD=parsed.password or '')
    with connect(url) as conn:
        conn.begin_read();conn.lock_writer()
        if state(conn)!=before:raise RuntimeError('Database changed before backup')
        schema=conn.execute('SELECT current_schema()').fetchone()[0]
        exported=conn.execute('SELECT pg_export_snapshot()').fetchone()[0]
        with backup.open('xb') as stream:
            os.chmod(backup,0o600)
            subprocess.run(['pg_dump','--format=custom','--no-owner','--no-acl','--schema='+schema,'--snapshot='+exported],env=env,stdout=stream,stderr=subprocess.PIPE,check=True)
        update_transaction(conn,changes,before)
        result.update(backup=str(backup),after=state(conn),checks_after=checks(conn),transaction='COMMITTED')
    report=folder/'updates.json';report.write_text(json.dumps(result,ensure_ascii=False,indent=2));os.chmod(report,0o600)
    return result

if __name__=='__main__':
    from backend.app.config import database_url
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');p.add_argument('--backup-dir',type=Path);args=p.parse_args()
    result=run(database_url(),args.apply,args.backup_dir)
    print(json.dumps({'mode':result['mode'],'updated_fields':len(result['updates']),'pending_fields':len(result['pending'])}))
