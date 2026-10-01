"""A fresh PG schema initializes directly and runtime verification never reseeds it."""
import os
import subprocess
import sys
from backend.app.postgres_storage import engine_for
from .postgres_support import empty_postgres_schema, snapshot


def test_empty_pg_schema_initializes_current_version_in_subprocess():
    with empty_postgres_schema() as url:
        env = dict(os.environ, DATABASE_URL=url)
        subprocess.run([sys.executable, 'scripts/initialize_postgres.py'], env=env, check=True, capture_output=True)
        with engine_for(url).connect() as conn:
            before = snapshot(conn)
            assert len(before) == 35
            assert conn.exec_driver_sql("SELECT value FROM app_metadata WHERE key='schema_version'").scalar() == '18'
        for _ in range(2):
            subprocess.run([sys.executable, '-c', 'from backend.app.database import initialize_storage; initialize_storage()'], env=env, check=True, capture_output=True)
        with engine_for(url).connect() as conn: assert snapshot(conn) == before
