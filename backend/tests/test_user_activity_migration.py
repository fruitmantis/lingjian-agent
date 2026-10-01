import os
import pytest
from sqlalchemy import inspect, text
from backend.app.postgres_storage import engine_for
from scripts.migrate_user_activity import migrate
from .conftest import make_user


def test_activity_migration_atomic_and_idempotent(client):
    user = make_user('activity_legacy_user')
    engine = engine_for(os.environ['DATABASE_URL'])
    with engine.begin() as conn:
        conn.exec_driver_sql('ALTER TABLE users DROP COLUMN last_active_at')
        conn.execute(text("UPDATE app_metadata SET value='13' WHERE key='schema_version'"))
        before = conn.execute(text('SELECT * FROM users ORDER BY id')).all()
    def fail(): raise RuntimeError('injected')
    with pytest.raises(RuntimeError):
        with engine.begin() as conn: migrate(conn, fault=fail)
    with engine.connect() as conn:
        assert 'last_active_at' not in {c['name'] for c in inspect(conn).get_columns('users')}
        assert conn.execute(text("SELECT value FROM app_metadata WHERE key='schema_version'")).scalar() == '13'
    with engine.begin() as conn:
        migrate(conn)
        activity = conn.execute(text('SELECT last_active_at FROM users WHERE id=:id'), {'id': user['id']}).scalar()
        migrate(conn)
        assert conn.execute(text('SELECT last_active_at FROM users WHERE id=:id'), {'id': user['id']}).scalar() == activity
        assert [tuple(row[:-1]) for row in conn.execute(text('SELECT * FROM users ORDER BY id')).all()] == [tuple(row) for row in before]
        assert conn.execute(text("SELECT value FROM app_metadata WHERE key='schema_version'")).scalar() == '14'
