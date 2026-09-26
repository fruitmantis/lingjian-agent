"""Explicit schema 13 -> 14: one activity timestamp, no user/data deletion."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from backend.app.postgres_storage import engine_for


def migrate(conn, fault=None):
    conn.exec_driver_sql('SELECT pg_advisory_xact_lock(179183912)')
    version = conn.execute(text("SELECT value FROM app_metadata WHERE key='schema_version'")).scalar()
    if version not in ('13', '14'):
        raise RuntimeError('Expected schema 13 or 14')
    if 'last_active_at' not in {c['name'] for c in inspect(conn).get_columns('users')}:
        conn.exec_driver_sql('ALTER TABLE users ADD COLUMN last_active_at TEXT')
    if version == '13':
        # Historical sessions did not record activity. Start a full grace period,
        # never infer inactivity from an old login timestamp.
        conn.execute(text("UPDATE users SET last_active_at=:now WHERE role='user' AND last_active_at IS NULL"),
                     {'now': datetime.now(timezone.utc).isoformat()})
    if fault:
        fault()
    conn.execute(text("UPDATE app_metadata SET value='14' WHERE key='schema_version'"))
    return {'schema_version': 14, 'deleted_records': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-dir', type=Path, required=True)
    parser.add_argument('--database-name', default='banfei_agent', help='Expected local database name; must match DATABASE_URL')
    args = parser.parse_args()
    url = make_url(os.environ['DATABASE_URL'])
    if not url.drivername.startswith('postgresql') or url.database != args.database_name or url.host not in ('localhost', '127.0.0.1'):
        raise RuntimeError('Only the explicitly named local PostgreSQL database is allowed')
    os.umask(0o077)
    args.backup_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    env = dict(os.environ, PGHOST=url.host, PGPORT=str(url.port or 5432), PGDATABASE=url.database,
               PGUSER=url.username or '', PGPASSWORD=url.password or '')
    with (args.backup_dir / 'before.pgdump').open('xb') as output:
        subprocess.run(['pg_dump', '--format=custom', '--no-owner', '--no-acl'], env=env,
                       stdout=output, stderr=subprocess.PIPE, check=True)
    with engine_for(os.environ['DATABASE_URL']).begin() as conn:
        conn.exec_driver_sql("SET LOCAL lock_timeout='5s'")
        result = migrate(conn)
    (args.backup_dir / 'result.json').write_text(json.dumps(result))
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Activity migration failed: '+type(error).__name__+'; transaction rolled back.', file=sys.stderr)
        sys.exit(1)
