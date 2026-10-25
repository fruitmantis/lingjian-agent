"""Optional self-reported employee labels and additive PG schema migration."""
import os
import pytest
from sqlalchemy import inspect
from backend.app.database import get_db
from backend.app.employee_number_schema import migrate
from backend.app.model_provider_schema import migrate as migrate_providers
from backend.app.model_context_schema import migrate as migrate_context
from backend.app.model_resolver import MODEL_SELECT
from backend.app.postgres_storage import verify_schema
from .postgres_support import snapshot
from .conftest import make_task
from .test_model_providers import legacy_schema
from .test_local_identity import browser, bearer, key_for, counts, HEADERS


def test_optional_employee_number_preserves_name_key_user_and_task(client):
    identity = browser(client); headers = bearer(identity); user = identity.json()['user']
    key = key_for(client, identity); task = make_task(user, 'employee label history')
    assert user['employee_number'] is None
    response = client.patch('/auth/me', headers=headers, json={'employee_number': '  001-A  '})
    assert response.status_code == 200
    assert response.json()['employee_number'] == '001-A'
    assert response.json()['display_name'] == user['display_name']
    assert response.json()['id'] == user['id'] and key_for(client, identity) == key
    assert client.get('/auth/me', headers=headers).json()['employee_number'] == '001-A'
    assert client.get('/agent/tasks/'+task, headers=headers).status_code == 200
    name = client.patch('/auth/me', headers=headers, json={'display_name': '保留显示名称'})
    assert name.json()['employee_number'] == '001-A'


@pytest.mark.parametrize('value', [None, '', '   '])
def test_employee_number_can_be_cleared(client, value):
    identity = browser(client); headers = bearer(identity)
    assert client.patch('/auth/me', headers=headers, json={'employee_number': 'E-001'}).status_code == 200
    assert client.patch('/auth/me', headers=headers, json={'employee_number': value}).json()['employee_number'] is None


@pytest.mark.parametrize('payload', [{'employee_number': 'x'*65}, {'employee_number': 123}, {}, {'display_name': None}])
def test_profile_update_validation_is_not_a_new_login_path(client, payload):
    identity = browser(client); before = counts()
    assert client.patch('/auth/me', headers=bearer(identity), json=payload).status_code == 422
    assert counts() == before


def test_duplicate_employee_number_is_allowed_without_merging_or_authenticating(client):
    first, second = browser(client), browser(client)
    for identity in (first, second):
        result = client.patch('/auth/me', headers=bearer(identity), json={'employee_number': 'E-007'})
        assert result.status_code == 200
    assert first.json()['user']['id'] != second.json()['user']['id']
    assert key_for(client, first) != key_for(client, second)
    before = counts()
    assert client.post('/auth/identity/key/login', headers=HEADERS, json={'key': 'E-007'}).status_code == 401
    assert counts() == before


def test_profile_update_is_current_owner_only(client):
    first, second = browser(client), browser(client)
    result = client.patch('/auth/me', headers=bearer(first), json={'employee_number': 'SELF', 'user_id': second.json()['user']['id']})
    assert result.json()['id'] == first.json()['user']['id']
    assert client.get('/auth/me', headers=bearer(second)).json()['employee_number'] is None
    assert client.patch('/auth/me', json={'employee_number': 'NOAUTH'}).status_code == 401


def make_schema20():
    with get_db() as conn:
        legacy_schema(conn)
        conn.execute('ALTER TABLE users DROP COLUMN employee_number')
        conn.execute("UPDATE app_metadata SET value='20' WHERE key='schema_version'")


def test_additive_migration_preserves_every_business_row_key_and_owner(client):
    identity = browser(client); make_task(identity.json()['user'], 'retained before schema21')
    make_schema20()
    with get_db() as conn:
        before = snapshot(conn)
        metadata = [tuple(row) for row in conn.execute("SELECT key,value FROM app_metadata WHERE key!='schema_version' ORDER BY key")]
        assert migrate(conn)['schema_version'] == 21
        after = snapshot(conn, {'users': ['employee_number']})
        assert {k:v for k,v in after.items() if k != 'app_metadata'} == {k:v for k,v in before.items() if k != 'app_metadata'}
        assert conn.execute('SELECT count(*) FROM users WHERE employee_number IS NOT NULL').fetchone()[0] == 0
        assert conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] == '21'
        models = [dict(row) for row in conn.execute('SELECT * FROM model_configs ORDER BY id')]
        assert migrate_providers(conn)['schema_version'] == '22'
        assert migrate_context(conn)['schema_version'] == '23'
        current = snapshot(conn, {'users': ['employee_number']})
        unchanged = set(before) - {'app_metadata', 'model_configs'}
        assert {name: current[name] for name in unchanged} == {name: before[name] for name in unchanged}
        assert [tuple(row) for row in conn.execute("SELECT key,value FROM app_metadata WHERE key!='schema_version' ORDER BY key")] == metadata
        current_models = [dict(row) for row in conn.execute(MODEL_SELECT+' ORDER BY m.id')]
        assert len(current_models) == len(models)
        for original, model in zip(models, current_models):
            assert {key: model[key] for key in original} == original
    verify_schema(os.environ['DATABASE_URL'])
    assert client.get('/auth/me', headers=bearer(identity)).status_code == 200


def test_migration_failure_rolls_back_column_version_and_all_rows(client):
    browser(client); make_schema20()
    with get_db() as conn: before = snapshot(conn)
    def fail(): raise RuntimeError('synthetic schema21 failure')
    with pytest.raises(RuntimeError, match='synthetic schema21'):
        with get_db() as conn: migrate(conn, fail)
    with get_db() as conn:
        assert snapshot(conn) == before
        assert 'employee_number' not in {c['name'] for c in inspect(conn.connection).get_columns('users')}


def test_schema21_migration_is_idempotent_and_preserves_employee_value(client):
    identity = browser(client)
    response = client.patch('/auth/me', headers=bearer(identity), json={'employee_number': 'KEEP'})
    assert response.status_code == 200 and response.json()['employee_number'] == 'KEEP'
    with get_db() as conn:
        legacy_schema(conn)
        before = snapshot(conn); migrate(conn); migrate(conn)
        assert snapshot(conn) == before


def test_runtime_rejects_old_schema_without_automatic_migration(client):
    make_schema20()
    with get_db() as conn: before = snapshot(conn)
    with pytest.raises(RuntimeError, match='^PostgreSQL schema is incomplete; explicit migration required$'):
        verify_schema(os.environ['DATABASE_URL'])
    with get_db() as conn:
        assert snapshot(conn) == before
        assert conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] == '20'
        assert 'employee_number' not in {c['name'] for c in inspect(conn.connection).get_columns('users')}


def test_runtime_rejects_schema21_stamp_without_automatic_migration(client):
    with get_db() as conn:
        conn.execute("UPDATE app_metadata SET value='21' WHERE key='schema_version'")
        before = snapshot(conn)
    with pytest.raises(RuntimeError, match='^PostgreSQL schema version is not 23; refusing automatic changes$'):
        verify_schema(os.environ['DATABASE_URL'])
    with get_db() as conn:
        assert snapshot(conn) == before
