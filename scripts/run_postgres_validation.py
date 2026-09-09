"""Run existing regression against a disposable, dedicated PostgreSQL test database.

BANFEI_TEST_DATABASE_URL must be configured privately. Never use the runtime DSN.
Services on 3000/8000/18180 must already be stopped before browser/process tests.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sqlalchemy.engine import make_url
from backend.tests.postgres_support import empty_postgres_schema


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite', choices=['backend', 'browser'])
    args, forwarded = parser.parse_known_args()
    value = os.getenv('BANFEI_TEST_DATABASE_URL', '')
    if not value:
        raise SystemExit('Private BANFEI_TEST_DATABASE_URL is required')
    parsed = make_url(value)
    if parsed.database != 'banfei_validation' or parsed.host not in ('127.0.0.1', 'localhost'):
        raise SystemExit('Only the dedicated local PostgreSQL validation database is allowed')
    environment = dict(os.environ)
    if args.suite == 'backend':
        return subprocess.call([sys.executable, '-m', 'pytest', 'backend/tests', *forwarded], cwd=ROOT, env=environment)
    with empty_postgres_schema() as url:
        environment.update(DATABASE_URL=url, PLAYWRIGHT_DATABASE_URL=url, PLAYWRIGHT_REUSE_SERVER='0')
        environment.setdefault('ENABLEMENT_EVIDENCE_DIR', '/tmp/banfei-postgres-evidence/enablement')
        environment.setdefault('HUAWEI_VISUAL_EVIDENCE_DIR', '/tmp/banfei-postgres-evidence/huawei')
        return subprocess.call(['npm', 'run', 'test:e2e', '--', *forwarded], cwd=ROOT/'frontend', env=environment)


if __name__ == '__main__':
    raise SystemExit(main())
