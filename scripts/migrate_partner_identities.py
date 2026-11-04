"""Explicit schema 24 -> 25 partner identity migration, with a verified full backup.

No backfill or model calls. For rollback, verify the pre-migration dump in a separate
database before an operator changes the runtime DSN. Never discard maintained identities.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy.engine import make_url
from backend.app.postgres_storage import engine_for,Connection
from backend.app.partner_identity_schema import migrate


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-dir',required=True,type=Path)
    parser.add_argument('--database-name', default='banfei_agent', help='Expected local database name; must match DATABASE_URL')
    args=parser.parse_args()
    url=make_url(os.environ['DATABASE_URL'])
    if not url.drivername.startswith('postgresql') or url.database!=args.database_name or url.host not in ('localhost','127.0.0.1'):
        raise RuntimeError('Only the explicitly named local PostgreSQL database is allowed')
    os.umask(0o077);args.backup_dir.mkdir(parents=True,mode=0o700,exist_ok=False)
    env=dict(os.environ,PGHOST=url.host,PGPORT=str(url.port or 5432),PGDATABASE=url.database,PGUSER=url.username or '',PGPASSWORD=url.password or '')
    backup=args.backup_dir/'before.pgdump'
    with backup.open('xb') as output:
        subprocess.run(['pg_dump','--format=custom','--no-owner','--no-acl'],env=env,stdout=output,stderr=subprocess.PIPE,check=True)
    subprocess.run(['pg_restore','--list',str(backup)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True)
    subprocess.run(['pg_restore','--file=/dev/null',str(backup)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=True)
    from backend.app.storage_models import metadata
    def business_counts(conn):
        return {table:conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in metadata.tables if table not in ('app_metadata',)}
    with engine_for(os.environ['DATABASE_URL']).begin() as raw:
        raw.exec_driver_sql("SET LOCAL lock_timeout='5s'")
        conn=Connection(raw);before=business_counts(conn);result=migrate(conn);after=business_counts(conn)
        if before!=after: raise RuntimeError('Business row counts changed; refusing migration')
        result['business_row_counts_unchanged']=True
    (args.backup_dir/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    try: main()
    except Exception as error:
        print('Partner identity migration failed: '+type(error).__name__+'; no credentials printed.',file=sys.stderr)
        sys.exit(1)
