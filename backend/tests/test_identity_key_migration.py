import os
import pytest
from sqlalchemy import inspect, text
from backend.app.postgres_storage import engine_for
from scripts.migrate_identity_keys import migrate
from .conftest import make_user


@pytest.mark.skipif(not os.getenv('BANFEI_TEST_DATABASE_URL'), reason='PostgreSQL migration')
def test_key_migration_atomic_idempotent_preserves_existing_users(client):
    make_user('legacy_key_migration_user')
    engine=engine_for(os.environ['DATABASE_URL'])
    with engine.begin() as conn:
        conn.exec_driver_sql('DROP TABLE user_identity_keys')
        conn.execute(text("UPDATE app_metadata SET value='14' WHERE key='schema_version'"))
        before=conn.execute(text('SELECT * FROM users ORDER BY id')).all()
    def fail():raise RuntimeError('isolated rollback')
    with pytest.raises(RuntimeError):
        with engine.begin() as conn:migrate(conn,fault=fail)
    with engine.connect() as conn:
        assert 'user_identity_keys' not in inspect(conn).get_table_names()
        assert conn.execute(text("SELECT value FROM app_metadata WHERE key='schema_version'")).scalar()=='14'
    with engine.begin() as conn:
        migrate(conn);migrate(conn)
        assert conn.execute(text('SELECT * FROM users ORDER BY id')).all()==before
        assert conn.execute(text('SELECT count(*) FROM user_identity_keys')).scalar()==0
        assert conn.execute(text("SELECT value FROM app_metadata WHERE key='schema_version'")).scalar()=='15'
