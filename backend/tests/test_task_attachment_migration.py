"""Schema 24 attachment columns roll back to 23 and re-apply without touching business rows."""
import os

from sqlalchemy import inspect, text

from backend.app.postgres_storage import Connection, engine_for
from backend.app.task_attachment_schema import migrate, rollback

from .conftest import make_task, make_user


def match_columns(raw):
    return {column['name'] for column in inspect(raw).get_columns('match_records')}


def schema_version(conn):
    return str(conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0])


def test_attachment_schema_rollback_and_migrate_are_reversible(client):
    user = make_user('attachment_schema_user')
    task_id = make_task(user, 'ATTACHMENT-SCHEMA')
    engine = engine_for(os.environ['DATABASE_URL'])
    with engine.begin() as raw:
        # Recreate schema 24 before testing the historical attachment migration.
        raw.exec_driver_sql("ALTER TABLE partners DROP COLUMN identities")
        raw.exec_driver_sql("UPDATE app_metadata SET value='24' WHERE key='schema_version'")
        raw.execute(text('UPDATE match_records SET attachment_name=:name,attachment_text=:body WHERE id=:id'),
                    {'name': '需求.txt', 'body': '附件正文', 'id': task_id})

    with engine.begin() as raw:
        conn = Connection(raw)
        assert schema_version(conn) == '24'
        result = rollback(conn)
        assert result['schema_version'] == 23
        assert set(result['removed_columns']) == {'match_records.attachment_name', 'match_records.attachment_text'}
        assert not {'attachment_name', 'attachment_text'} & match_columns(raw)
        assert schema_version(conn) == '23'
        assert conn.execute('SELECT count(*) FROM match_records WHERE id=?', (task_id,)).fetchone()[0] == 1
        assert rollback(conn) == {'schema_version': 23, 'already_current': True}

    with engine.begin() as raw:
        conn = Connection(raw)
        result = migrate(conn)
        assert result['schema_version'] == 24
        assert set(result['added_columns']) == {'match_records.attachment_name', 'match_records.attachment_text'}
        assert {'attachment_name', 'attachment_text'} <= match_columns(raw)
        assert conn.execute('SELECT count(*) FROM match_records WHERE id=?', (task_id,)).fetchone()[0] == 1
        assert migrate(conn) == {'schema_version': 24, 'already_current': True}
