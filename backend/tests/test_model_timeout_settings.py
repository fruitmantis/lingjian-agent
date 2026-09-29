"""Global policy CRUD: isolated storage, no provider calls or private file writes."""
from concurrent.futures import ThreadPoolExecutor
import pytest
from backend.app import model_timeout_settings as settings
from backend.app.database import get_db
from backend.tests.conftest import auth_headers, make_user

PATH = '/admin/model-configs/timeout-settings'


@pytest.mark.parametrize('method', ['get', 'put'])
def test_configuration_is_admin_only(client, method):
    kwargs = {'json': {'timeoutSeconds':600, 'timeoutRetries':1}} if method == 'put' else {}
    assert getattr(client, method)(PATH, **kwargs).status_code == 401
    user = make_user('policy-user')
    assert getattr(client, method)(PATH, headers=auth_headers(user), **kwargs).status_code == 403
    assert settings.describe() == {'timeoutSeconds':300, 'timeoutRetries':3}


def test_policy_save_is_immediate_and_persistent(client, monkeypatch):
    admin = make_user('policy-admin', role='admin'); headers = auth_headers(admin)
    with get_db() as conn:
        conn.execute("INSERT INTO app_metadata VALUES ('unrelated-config','keep')")
    initial = client.get(PATH, headers=headers)
    assert initial.status_code == 200 and initial.headers['cache-control'] == 'no-store'
    assert initial.json() == {'timeoutSeconds':300, 'timeoutRetries':3}
    result = client.put(PATH, headers=headers, json={'timeoutSeconds':420, 'timeoutRetries':0})
    assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
    assert result.json() == settings.describe() == {'timeoutSeconds':420, 'timeoutRetries':0}
    assert client.get(PATH, headers=headers).json() == result.json()
    with get_db() as conn:
        assert settings.get_settings(conn).model_dump() == result.json()
        assert conn.execute("SELECT value FROM app_metadata WHERE key='unrelated-config'").fetchone()[0] == 'keep'
    monkeypatch.setenv('MODEL_TIMEOUT_SECONDS', '1'); monkeypatch.setenv('MODEL_TIMEOUT_RETRIES', '0')
    assert settings.describe() == result.json()


def test_nonsecret_policy_read_requires_authentication_and_has_no_user_write(client):
    user = make_user('policy-reader'); headers = auth_headers(user)
    assert client.get('/model-timeout-settings').status_code == 401
    response = client.get('/model-timeout-settings', headers=headers)
    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
    assert response.json() == {'timeoutSeconds':300, 'timeoutRetries':3}
    assert client.put('/model-timeout-settings', headers=headers, json=response.json()).status_code == 405


@pytest.mark.parametrize('patch', [
    {'timeoutSeconds':0}, {'timeoutSeconds':-1}, {'timeoutSeconds':'NaN'}, {'timeoutSeconds':True},
    {'timeoutRetries':-1}, {'timeoutRetries':1.5}, {'timeoutRetries':True},
    {'DATABASE_URL':'not-allowed'}, {'path':'/tmp/other-file'},
])
def test_invalid_or_extra_fields_do_not_modify_policy(client, patch):
    before = settings.describe(); admin = make_user('policy-invalid-admin', role='admin')
    result = client.put(PATH, headers=auth_headers(admin), json={**before, **patch})
    assert result.status_code == 422 and settings.describe() == before


def test_write_failure_preserves_policy(client, monkeypatch):
    from contextlib import contextmanager
    before = settings.describe(); admin = make_user('policy-failed-admin', role='admin')
    @contextmanager
    def failed_commit():
        with get_db() as conn:
            yield conn
            raise RuntimeError('Synthetic commit failure')
    monkeypatch.setattr(settings, 'get_db', failed_commit)
    result = client.put(PATH, headers=auth_headers(admin), json={'timeoutSeconds':420, 'timeoutRetries':1})
    assert result.status_code == 500
    assert result.json()['detail'] == '服务异常，请联系管理员。'
    assert settings.describe() == before


def test_concurrent_saves_do_not_mix_fields():
    policies = [settings.TimeoutSettings(timeoutSeconds=420, timeoutRetries=1),
                settings.TimeoutSettings(timeoutSeconds=600, timeoutRetries=2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(settings.save, policies))
    assert settings.get_settings() in policies


@pytest.mark.parametrize('rollback', [False, True])
def test_cleanup_migration_is_transactional_and_preserves_models(rollback):
    from backend.app.model_timeout_schema import migrate
    with get_db() as conn:
        conn.execute("UPDATE app_metadata SET value='17' WHERE key='schema_version'")
        conn.execute('ALTER TABLE model_configs ADD COLUMN timeout_seconds INTEGER DEFAULT 123')
        before = [dict(row) for row in conn.execute('SELECT * FROM model_configs ORDER BY id')]
    def fault(): raise RuntimeError('Synthetic migration failure')
    try:
        with get_db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            migrate(conn, fault if rollback else None)
    except RuntimeError:
        if not rollback: raise
    with get_db() as conn:
        after = [dict(row) for row in conn.execute('SELECT * FROM model_configs ORDER BY id')]
        assert after == (before if rollback else [{k:v for k,v in row.items() if k!='timeout_seconds'} for row in before])
        assert conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] == ('17' if rollback else '18')
        if not rollback: assert migrate(conn)['already_current']
