"""Initialize editable course/lab taxonomy in app_metadata; no schema/resource changes."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.engine import make_url
from backend.app.database import get_db
from backend.app.resource_categories import initialize, read, KEY


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-dir',type=Path,required=True)
    parser.add_argument('--database-name',default='banfei_agent',help='Expected local database name; must match DATABASE_URL')
    args=parser.parse_args()
    url=make_url(os.environ['DATABASE_URL'])
    if not url.drivername.startswith('postgresql') or url.database!=args.database_name or url.host not in ('localhost','127.0.0.1'):
        raise RuntimeError('Only the explicitly named local PostgreSQL database is allowed')
    os.umask(0o077)
    args.backup_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
    env=dict(os.environ,PGHOST=url.host,PGPORT=str(url.port or 5432),PGDATABASE=url.database,PGUSER=url.username or '',PGPASSWORD=url.password or '')
    with (args.backup_dir/'before.pgdump').open('xb') as output:
        subprocess.run(['pg_dump','--format=custom','--no-owner','--no-acl'],env=env,stdout=output,stderr=subprocess.PIPE,check=True)
    with get_db() as conn:
        conn.lock_writer()
        existed=bool(conn.execute('SELECT 1 FROM app_metadata WHERE key=?',(KEY,)).fetchone())
        initialize(conn)
        result={'created':not existed,'category_count':len(read(conn)),'schema_version':conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0],'time':datetime.now(timezone.utc).isoformat()}
    (args.backup_dir/'result.json').write_text(json.dumps(result))
    print(json.dumps(result))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print('Category initialization failed: '+type(error).__name__+'; no resource data was modified.',file=sys.stderr)
        sys.exit(1)
