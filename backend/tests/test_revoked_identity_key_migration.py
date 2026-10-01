import os
import pytest
from sqlalchemy import inspect, text
from backend.app.postgres_storage import engine_for
from scripts.migrate_revoked_identity_keys import migrate
from .test_local_identity import browser, key_for


def test_revoked_key_migration_atomic_idempotent_preserves_all_existing_data(client):
    identity = browser(client); key_for(client, identity)
    engine = engine_for(os.environ['DATABASE_URL'])
    with engine.begin() as conn:
        conn.exec_driver_sql('DROP TABLE revoked_identity_keys')
        conn.execute(text("UPDATE app_metadata SET value='15' WHERE key='schema_version'"))
        before = {name: conn.exec_driver_sql('SELECT * FROM "'+name+'"').all()
                  for name in inspect(conn).get_table_names() if name != 'app_metadata'}
    def fail(): raise RuntimeError('isolated migration rollback')
    with pytest.raises(RuntimeError):
        with engine.begin() as conn: migrate(conn, fault=fail)
    with engine.connect() as conn:
        assert 'revoked_identity_keys' not in inspect(conn).get_table_names()
        assert conn.execute(text("SELECT value FROM app_metadata WHERE key='schema_version'")).scalar() == '15'
    with engine.begin() as conn:
        migrate(conn)
        assert conn.execute(text('SELECT count(*) FROM revoked_identity_keys')).scalar() == 0
        conn.execute(text("INSERT INTO revoked_identity_keys VALUES (:hash, '2026-09-24T00:00:00+00:00')"), {'hash': 'a'*64})
        migrate(conn)
        assert conn.execute(text('SELECT count(*) FROM revoked_identity_keys')).scalar() == 1
        assert conn.execute(text("SELECT value FROM app_metadata WHERE key='schema_version'")).scalar() == '16'
        assert {col['name'] for col in inspect(conn).get_columns('revoked_identity_keys')} == {'key_hash', 'revoked_at'}
        assert not inspect(conn).get_foreign_keys('revoked_identity_keys')
        for name, rows in before.items():
            assert conn.exec_driver_sql('SELECT * FROM "'+name+'"').all() == rows


def test_revoked_key_migration_refuses_unexpected_version(client):
    engine = engine_for(os.environ['DATABASE_URL'])
    with engine.begin() as conn:
        conn.execute(text("UPDATE app_metadata SET value='14' WHERE key='schema_version'"))
    with pytest.raises(RuntimeError, match='Expected schema'):
        with engine.begin() as conn: migrate(conn)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT value FROM app_metadata WHERE key='schema_version'")).scalar() == '14'
