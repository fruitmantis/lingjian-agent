"""Explicit schema 15 -> 16: deleted Key digests only, no existing-data changes."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from sqlalchemy.engine import make_url
from backend.app.postgres_storage import engine_for


def migrate(conn, fault=None):
    conn.exec_driver_sql('SELECT pg_advisory_xact_lock(179183912)')
    version = conn.execute(text("SELECT value FROM app_metadata WHERE key='schema_version'")).scalar()
    if version not in ('15', '16'):
        raise RuntimeError('Expected schema 15 or 16')
    from backend.app.storage_models import revoked_identity_keys
    revoked_identity_keys.create(conn, checkfirst=True)
    if fault:
        fault()
    conn.execute(text("UPDATE app_metadata SET value='16' WHERE key='schema_version'"))
    return {'schema_version': 16, 'backfilled_revocations': 0, 'deleted_records': 0}


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
        print('Revoked identity key migration failed: '+type(error).__name__+'; transaction rolled back.', file=sys.stderr)
        sys.exit(1)
