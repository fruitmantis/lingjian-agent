"""Read-only fingerprint of a dedicated disposable PostgreSQL test schema."""
import hashlib
import json
import os
from sqlalchemy import select
from sqlalchemy.engine import make_url
from backend.app.postgres_storage import engine_for
from backend.app.storage_models import metadata


def fingerprint(url):
    parsed = make_url(url)
    if parsed.database != 'banfei_validation' or parsed.host not in ('127.0.0.1', 'localhost'):
        raise RuntimeError('Only the dedicated local test database may be fingerprinted')
    with engine_for(url).connect() as conn:
        conn.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        rows = {name: sorted(json.dumps(list(row), ensure_ascii=False) for row in conn.execute(select(table)))
                for name, table in metadata.tables.items()}
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


if __name__ == '__main__':
    print(fingerprint(os.environ['DATABASE_URL']))
