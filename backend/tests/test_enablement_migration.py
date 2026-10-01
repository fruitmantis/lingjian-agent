"""Native PG initialization replaces retired file-snapshot migration replay."""
import os
import pytest
from sqlalchemy import event, inspect
from sqlalchemy.exc import DBAPIError
from backend.app.postgres_storage import engine_for, initialize_empty_schema, verify_schema
from backend.app.database import get_db, initialize_storage
from .postgres_support import empty_postgres_schema, snapshot as state


def assert_initialization_rollback_and_retry(failure_point):
    with empty_postgres_schema() as url:
        engine = engine_for(url)
        writes = []
        def fault(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().startswith(('CREATE ', 'ALTER ', 'INSERT ')):
                writes.append(statement.split()[0])
                if len(writes) == failure_point:
                    conn.exec_driver_sql('SELECT 1 / 0')
        if failure_point:
            event.listen(engine, 'after_cursor_execute', fault)
            try:
                with pytest.raises(DBAPIError, match='division by zero'):
                    initialize_empty_schema(url)
                assert len(writes) == failure_point
                with engine.connect() as conn:
                    assert inspect(conn).get_table_names() == []
                    assert conn.exec_driver_sql('SELECT count(*) FROM pg_proc WHERE pronamespace=current_schema()::regnamespace').scalar() == 0
            finally:
                event.remove(engine, 'after_cursor_execute', fault)
        initialize_empty_schema(url)
        verify_schema(url)
        with engine.connect() as conn:
            before = state(conn)
            assert conn.exec_driver_sql("SELECT value FROM app_metadata WHERE key='schema_version'").scalar() == '18'
        with pytest.raises(RuntimeError, match='empty'):
            initialize_empty_schema(url)
        verify_schema(url)
        with engine.connect() as conn: assert state(conn) == before


@pytest.mark.parametrize('failure_point', [1, 3, 7, 10])
def test_migration_failure_is_atomic_and_retry_recovers(failure_point):
    assert_initialization_rollback_and_retry(failure_point)


def test_current_schema_verification_is_idempotent_and_preserves_every_row(client):
    with get_db() as conn: before = state(conn)
    initialize_storage(); initialize_storage()
    with get_db() as conn: assert state(conn) == before


def test_new_schema_is_independent_of_existing_schema(client):
    with get_db() as conn: before = state(conn)
    with empty_postgres_schema() as url:
        initialize_empty_schema(url)
        with engine_for(url).begin() as conn:
            conn.exec_driver_sql("INSERT INTO partners(id,name,created_at) VALUES ('isolated','synthetic','now')")
    with get_db() as conn: assert state(conn) == before


def test_existing_database_cannot_be_reinitialized(client):
    with get_db() as conn: before = state(conn)
    with pytest.raises(RuntimeError, match='empty'): initialize_empty_schema(os.environ['DATABASE_URL'])
    with get_db() as conn: assert state(conn) == before
