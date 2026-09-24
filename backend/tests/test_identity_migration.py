import os
import pytest
from sqlalchemy import inspect, text
from backend.app.postgres_storage import engine_for
from scripts.migrate_local_identity import migrate
from .conftest import make_user

@pytest.mark.skipif(not os.getenv('BANFEI_TEST_DATABASE_URL'),reason='PostgreSQL migration')
def test_identity_migration_atomic_and_idempotent(client):
    admin=make_user('migration_admin',role='admin')
    engine=engine_for(os.environ['DATABASE_URL'])
    with engine.begin() as conn:
        conn.exec_driver_sql('DROP TABLE identity_credentials')
        conn.exec_driver_sql('DROP TABLE identity_challenges')
        conn.exec_driver_sql('ALTER TABLE users DROP CONSTRAINT ck_admin_password')
        conn.exec_driver_sql('ALTER TABLE users ALTER COLUMN hashed_password SET NOT NULL')
        conn.execute(text("UPDATE app_metadata SET value='12' WHERE key='schema_version'"))
        before=conn.execute(text('SELECT * FROM users ORDER BY id')).all()
    def fail():raise RuntimeError('injected')
    with pytest.raises(RuntimeError):
        with engine.begin() as conn:migrate(conn,fault=fail)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT value FROM app_metadata WHERE key='schema_version'")).scalar()=='12'
        assert 'identity_credentials' not in inspect(conn).get_table_names()
        assert not next(c for c in inspect(conn).get_columns('users') if c['name']=='hashed_password')['nullable']
    with engine.begin() as conn:migrate(conn);migrate(conn)
    with engine.connect() as conn:
        assert conn.execute(text('SELECT * FROM users ORDER BY id')).all()==before
        assert conn.execute(text("SELECT value FROM app_metadata WHERE key='schema_version'")).scalar()=='13'
        with pytest.raises(Exception):conn.execute(text('UPDATE users SET hashed_password=NULL WHERE id=:id'),{'id':admin['id']})
