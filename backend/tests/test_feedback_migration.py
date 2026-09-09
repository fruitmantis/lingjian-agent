import os
import pytest
from sqlalchemy import inspect, text
from backend.app.postgres_storage import engine_for
from backend.app.storage_models import feedback_issue, feedback_attachment
from scripts.migrate_feedback import migrate
from .conftest import make_user


def test_additive_migration_rollback_and_repeatability(client):
    url = os.environ['DATABASE_URL']
    if not url.startswith('postgresql'):
        pytest.skip('Explicit PostgreSQL validation required')
    user = make_user('migration-preserved')
    engine = engine_for(url)
    with engine.begin() as conn:
        feedback_attachment.drop(conn)
        feedback_issue.drop(conn)
        before = conn.execute(text('SELECT * FROM users ORDER BY id')).all()
    def fault():
        raise RuntimeError('injected DDL fault')
    with pytest.raises(RuntimeError, match='injected'):
        with engine.begin() as conn:
            migrate(conn, fault=fault)
    with engine.begin() as conn:
        assert 'feedback_issue' not in inspect(conn).get_table_names()
        assert migrate(conn)['added_tables'] == ['feedback_attachment', 'feedback_issue']
        assert migrate(conn)['added_tables'] == []
        assert conn.execute(text('SELECT * FROM users ORDER BY id')).all() == before
        assert conn.execute(text("SELECT value FROM app_metadata WHERE key='schema_version'")).scalar() == '12'
