"""Explicit additive v12 patch. Back up PostgreSQL before adding nullable task diagnostics."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect,select
from sqlalchemy.engine import make_url
from backend.app.postgres_storage import engine_for
from backend.app.storage_models import metadata
from scripts.migrate_sqlite_to_postgres import digest

def migrate(conn,fault=None):
 columns={c['name'] for c in inspect(conn).get_columns('match_records')}
 before={t.name:digest(conn.execute(select(*[c for c in t.c if c.name!='last_error_details'])).all()) for t in metadata.tables.values()}
 conn.exec_driver_sql('ALTER TABLE match_records ADD COLUMN IF NOT EXISTS last_error_details TEXT')
 if fault:fault()
 after={t.name:digest(conn.execute(select(*[c for c in t.c if c.name!='last_error_details'])).all()) for t in metadata.tables.values()}
 if before!=after:raise RuntimeError('Existing data changed')
 return {'added': 'last_error_details' not in columns,'existing_tables_unchanged':len(before),'schema_version':'12 (additive nullable column)','status':'PASS'}

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--backup-dir',type=Path,required=True);args=parser.parse_args()
 url=make_url(os.environ['DATABASE_URL'])
 if not url.drivername.startswith('postgresql'):raise RuntimeError('Explicit PostgreSQL URL required')
 out=args.backup_dir;out.mkdir(mode=0o700,parents=True,exist_ok=False);os.umask(0o077)
 env=dict(os.environ,PGHOST=url.host or 'localhost',PGPORT=str(url.port or 5432),PGDATABASE=url.database,PGUSER=url.username or '',PGPASSWORD=url.password or '')
 with (out/'before.pgdump').open('xb') as file:subprocess.run(['pg_dump','--format=custom','--no-owner','--no-acl'],env=env,stdout=file,stderr=subprocess.PIPE,check=True)
 engine=engine_for(os.environ['DATABASE_URL'])
 with engine.begin() as conn:
  conn.exec_driver_sql("SET LOCAL lock_timeout='5s'")
  result=migrate(conn)
 (out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':
 try:main()
 except Exception as exc:print('Migration failed: '+type(exc).__name__+'; transaction rolled back.',file=sys.stderr);sys.exit(1)
