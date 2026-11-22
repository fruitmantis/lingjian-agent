"""Explicit schema 25 -> 26 capability hierarchy migration, with a verified full backup.

Preserves all business rows, existing Level-1 tag UUIDs and resource_capability_map links,
adds two-tier capability structure, and separates Level-2 partner certifications cleanly.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy.engine import make_url
from backend.app.capability_hierarchy_schema import migrate
from backend.app.postgres_storage import Connection, engine_for, verify_schema_connection

PRESERVED_TABLES = (
    'partners', 'cases', 'deliverables', 'partner_documents', 'partner_profile_sources',
    'match_records', 'development_plans', 'development_requests', 'development_runs',
    'development_versions', 'development_version_items', 'demand_profiles',
    'project_opportunities', 'enablement_resources', 'enablement_resource_versions',
    'resource_capability_map', 'capability_tag_suggestions', 'users',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-dir', required=True, type=Path)
    parser.add_argument('--database-name', default='banfei_agent', help='Expected local database name; must match DATABASE_URL')
    args = parser.parse_args()
    url = make_url(os.environ['DATABASE_URL'])
    if not url.drivername.startswith('postgresql') or url.database != args.database_name or url.host not in ('localhost', '127.0.0.1'):
        raise RuntimeError('Only the explicitly named local PostgreSQL database is allowed')
    os.umask(0o077)
    args.backup_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    env = dict(
        os.environ,
        PGHOST=url.host,
        PGPORT=str(url.port or 5432),
        PGDATABASE=url.database,
        PGUSER=url.username or '',
        PGPASSWORD=url.password or '',
    )
    backup = args.backup_dir / 'before.pgdump'
    with backup.open('xb') as output:
        subprocess.run(['pg_dump', '--format=custom', '--no-owner', '--no-acl'], env=env, stdout=output, stderr=subprocess.PIPE, check=True)
    subprocess.run(['pg_restore', '--list', str(backup)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
    subprocess.run(['pg_restore', '--file=/dev/null', str(backup)], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)

    def row_counts(conn):
        return {table: conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in PRESERVED_TABLES}

    with engine_for(os.environ['DATABASE_URL']).begin() as raw:
        raw.exec_driver_sql("SET LOCAL lock_timeout='5s'")
        conn = Connection(raw)
        before = row_counts(conn)
        result = migrate(conn)
        after = row_counts(conn)
        if before != after:
            raise RuntimeError('Preserved business row counts changed; refusing migration')
        result['business_row_counts_unchanged'] = True
        verify_schema_connection(raw)
    try:
        (args.backup_dir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as report_error:
        print(
            'Database committed to schema 26, but failed to write result report: '
            + type(report_error).__name__ + ': ' + str(report_error),
            file=sys.stderr,
        )
        sys.exit(2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Capability hierarchy migration failed: ' + type(error).__name__ + ': ' + str(error), file=sys.stderr)
        sys.exit(1)
