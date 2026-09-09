"""Explicit additive feedback migration. Backup first; never rewrite existing business data."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from backend.app.postgres_storage import engine_for
from backend.app.storage_models import feedback_issue, feedback_attachment


def migrate(conn, fault=None):
    if conn.execute(text("SELECT value FROM app_metadata WHERE key='schema_version'")).scalar() != '12':
        raise RuntimeError('Expected existing v12 database')
    conn.exec_driver_sql('SELECT pg_advisory_xact_lock(179183912)')
    before = set(inspect(conn).get_table_names())
    for table in (feedback_issue, feedback_attachment):
        table.create(conn, checkfirst=True)
    if fault:
        fault()
    for table in (feedback_issue, feedback_attachment):
        if set(table.c.keys()) != {c['name'] for c in inspect(conn).get_columns(table.name)}:
            raise RuntimeError('Unexpected feedback schema')
    return {'status': 'PASS', 'added_tables': sorted({'feedback_issue', 'feedback_attachment'} - before),
            'schema_version': '12 (additive feedback tables)', 'existing_business_tables': 'unchanged'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-dir', type=Path, required=True)
    args = parser.parse_args()
    url = make_url(os.environ['DATABASE_URL'])
    if not url.drivername.startswith('postgresql') or url.database != 'banfei_agent' or url.host not in ('127.0.0.1', 'localhost'):
        raise RuntimeError('Only the current local banfei_agent runtime is allowed')
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
    (args.backup_dir / 'result.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Feedback migration failed: ' + type(exc).__name__ + '; no partial transaction committed.', file=sys.stderr)
        sys.exit(1)
