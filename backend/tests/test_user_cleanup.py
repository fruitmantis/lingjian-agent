"""Deletion boundary, revalidation and transaction tests on isolated storage."""
from datetime import datetime, timedelta, timezone
import uuid

import pytest

from backend.app import user_cleanup as cleanup, development_lifecycle as life
from backend.app.database import get_db
from backend.app.development_types import DevelopmentRequest, Submit
from .conftest import auth_headers, make_user, make_task, make_partner
from .support.legacy_identity import legacy_browser as browser, legacy_passkey as register


def stamp(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def age(user, days, task=None):
    old = stamp(days)
    with get_db() as conn:
        conn.execute('UPDATE users SET created_at=?,last_login_at=?,last_active_at=? WHERE id=?', (old, old, old, user['id']))
        if task:
            conn.execute('UPDATE match_records SET created_at=?,updated_at=? WHERE id=?', (old, old, task))
    return old


def preview(client, admin, user):
    response = client.get(f"/admin/users/{user['id']}/deletion-preview", headers=auth_headers(admin))
    assert response.status_code == 200, response.text
    return response.json()


def remove(client, admin, user, result):
    return client.request('DELETE', '/admin/users/' + user['id'], headers=auth_headers(admin),
                          json={'confirmationToken': result['confirmationToken'] or 'invalid'})


@pytest.fixture
def identities(client):
    return make_user('cleanup_admin', role='admin'), browser(client).json()


def test_empty_browser_deletes_credentials_but_keeps_audit_and_admin(client, identities):
    admin, session = identities; user = session['user']
    result = preview(client, admin, user)
    assert result['allowed'] and result['privateData'] == [] and result['credentialCount'] == 1
    assert result['retainedAuditCount'] > 0
    assert remove(client, admin, user, result).status_code == 204
    assert client.get('/auth/me', headers={'Authorization': 'Bearer ' + session['access_token']}).status_code == 401
    with get_db() as conn:
        assert conn.execute('SELECT 1 FROM users WHERE id=?', (user['id'],)).fetchone() is None
        assert conn.execute('SELECT count(*) FROM identity_credentials WHERE user_id=?', (user['id'],)).fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM user_audit_logs WHERE target_user_id=?', (user['id'],)).fetchone()[0] >= 2
        assert conn.execute('SELECT 1 FROM users WHERE id=?', (admin['id'],)).fetchone()
    logs = client.get('/admin/user-audit-logs', headers=auth_headers(admin)).json()['items']
    assert any(row['action'] == 'admin.user_deleted' and row['targetName'] == '已删除用户' for row in logs)
    assert remove(client, admin, user, result).status_code == 404


@pytest.mark.parametrize('days,allowed', [(89, False), (91, True)])
def test_private_history_retention(client, identities, days, allowed):
    admin, session = identities; user = session['user']
    task = make_task(user, 'private'); age(user, days, task)
    other = make_user('other'); other_task = make_task(other, 'preserved')
    result = preview(client, admin, user)
    assert result['allowed'] == allowed and result['retentionDays'] == 90
    assert result['privateData'][0]['count'] == 1
    if allowed:
        assert remove(client, admin, user, result).status_code == 204
    else:
        assert result['confirmationToken'] is None
        assert remove(client, admin, user, result).status_code == 409
    with get_db() as conn:
        assert bool(conn.execute('SELECT 1 FROM match_records WHERE id=?', (task,)).fetchone()) == (not allowed)
        assert conn.execute('SELECT 1 FROM match_records WHERE id=?', (other_task,)).fetchone()


def test_retention_configuration_and_invalid_value(client, identities, monkeypatch):
    admin, session = identities; user = session['user']; task = make_task(user, 'private'); age(user, 31, task)
    assert not preview(client, admin, user)['allowed']
    monkeypatch.setenv('BROWSER_IDENTITY_RETENTION_DAYS', '30')
    assert preview(client, admin, user)['allowed']
    monkeypatch.setenv('BROWSER_IDENTITY_RETENTION_DAYS', '0')
    with pytest.raises(RuntimeError): cleanup.browser_identity_retention_days()


@pytest.mark.parametrize('kind', ['demand', 'opportunity', 'suggestion', 'feedback', 'published'])
def test_public_references_block_even_after_retention(client, identities, kind):
    admin, session = identities; user = session['user']; task = make_task(user, 'private'); old = age(user, 100, task)
    with get_db() as conn:
        if kind == 'demand':
            conn.execute('INSERT INTO demand_profiles(id,match_record_id,requirement_text,created_at) VALUES (?,?,?,?)', ('ref', task, 'public', old))
        elif kind == 'opportunity':
            conn.execute('INSERT INTO project_opportunities(id,match_record_id,requirement_text,created_at,updated_at) VALUES (?,?,?,?,?)', ('ref', task, 'public', old, old))
        elif kind == 'suggestion':
            conn.execute('INSERT INTO capability_tag_suggestions(id,suggested_name,source_match_record_id,created_at,updated_at) VALUES (?,?,?,?,?)', ('ref', 'public', task, old, old))
        elif kind == 'feedback':
            conn.execute('INSERT INTO feedback_issue(id,submitter_id,description,status,created_at,updated_at) VALUES (?,?,?,?,?,?)', ('ref', user['id'], 'public', 'pending', old, old))
        else:
            conn.execute("INSERT INTO enablement_resources(id,draft_json,created_by,created_at,updated_at) VALUES ('ref','{}',?,?,?)", (user['id'], old, old))
            conn.execute("INSERT INTO enablement_resource_versions(source_id,version,payload_json,authorization_epoch,reviewed_revision,published_by,published_at) VALUES ('ref',1,'{}',1,1,?,?)", (user['id'], old))
    result = preview(client, admin, user)
    assert not result['allowed'] and result['publicReferences']
    assert remove(client, admin, user, result).status_code == 409
    with get_db() as conn: assert conn.execute('SELECT 1 FROM users WHERE id=?', (user['id'],)).fetchone()


def passkey_identity(client, mixed=False):
    registered = register(client)
    browser_cookie = None
    if mixed:
        other = browser(client)
        browser_cookie = 'banfei_browser_identity=' + other.cookies['banfei_browser_identity']
        with get_db() as conn:
            conn.execute('UPDATE identity_credentials SET user_id=? WHERE user_id=?',
                         (registered[0]['user']['id'], other.json()['user']['id']))
    return registered, browser_cookie


@pytest.mark.parametrize('mixed', [False, True])
def test_empty_passkey_deletion_revokes_all_credentials_and_session(client, mixed):
    admin = make_user('cleanup_admin', role='admin')
    registered, browser_cookie = passkey_identity(client, mixed)
    session, credential, private, handle, _, _ = registered
    user = session['user']
    result = preview(client, admin, user)
    assert result['allowed'] and result['privateData'] == [] and result['publicReferences'] == []
    assert result['eligibleAfter'] is None and result['credentialCount'] == (2 if mixed else 1)
    assert remove(client, admin, user, result).status_code == 204
    assert client.get('/auth/me', headers={'Authorization': 'Bearer ' + session['access_token']}).status_code == 401
    # Retired ordinary authentication routes stay closed, including after deletion.
    assert client.post('/auth/identity/passkey/authenticate/options').status_code == 404
    assert client.post('/auth/identity/browser').status_code == 404
    assert client.get('/auth/me', headers=auth_headers(admin)).status_code == 200
    with get_db() as conn:
        assert conn.execute('SELECT 1 FROM users WHERE id=?', (user['id'],)).fetchone() is None
        assert conn.execute('SELECT count(*) FROM identity_credentials WHERE user_id=?', (user['id'],)).fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM user_audit_logs WHERE target_user_id=?', (user['id'],)).fetchone()[0] >= 2


@pytest.mark.parametrize('mixed', [False, True])
@pytest.mark.parametrize('days', [1, 120])
def test_passkey_private_history_never_expires(client, mixed, days):
    admin = make_user('cleanup_admin', role='admin')
    user = passkey_identity(client, mixed)[0][0]['user']
    task = make_task(user, 'preserved'); age(user, days, task)
    result = preview(client, admin, user)
    assert not result['allowed'] and result['confirmationToken'] is None and result['eligibleAfter'] is None
    assert '长期身份存在业务历史' in result['reason']
    assert result['privateData'][0]['count'] == 1
    assert remove(client, admin, user, result).status_code == 409
    with get_db() as conn:
        assert conn.execute('SELECT 1 FROM match_records WHERE id=?', (task,)).fetchone()


def test_passkey_public_reference_blocks_even_without_private_history(client):
    admin = make_user('cleanup_admin', role='admin')
    user = register(client)[0]['user']; old = age(user, 120)
    with get_db() as conn:
        conn.execute('INSERT INTO feedback_issue(id,submitter_id,description,status,created_at,updated_at) VALUES (?,?,?,?,?,?)',
                     ('ref', user['id'], 'preserved', 'pending', old, old))
    result = preview(client, admin, user)
    assert not result['allowed'] and result['privateData'] == []
    assert result['publicReferences'] == [{'key': 'feedback_issue', 'label': '问题反馈', 'count': 1}]
    assert '公共、共享' in result['reason'] and result['eligibleAfter'] is None
    assert remove(client, admin, user, result).status_code == 409


def test_new_passkey_history_invalidates_empty_preview(client):
    admin = make_user('cleanup_admin', role='admin')
    user = register(client)[0]['user']
    result = preview(client, admin, user); assert result['allowed']
    task = make_task(user, 'added after preview'); age(user, 120, task)
    response = remove(client, admin, user, result)
    assert response.status_code == 409 and '长期身份存在业务历史' in response.json()['detail']
    with get_db() as conn:
        assert conn.execute('SELECT 1 FROM users WHERE id=?', (user['id'],)).fetchone()
        assert conn.execute('SELECT 1 FROM match_records WHERE id=?', (task,)).fetchone()


@pytest.mark.parametrize('kind', ['admin', 'unconfigured'])
def test_admin_and_unconfigured_users_never_participate(client, kind):
    admin = make_user('cleanup_admin', role='admin')
    user = admin if kind == 'admin' else make_user('unconfigured')
    age(user, 120)
    result = preview(client, admin, user)
    assert not result['allowed'] and result['confirmationToken'] is None


def test_recent_activity_is_recorded_and_blocks_stale_preview(client, identities):
    admin, session = identities; user = session['user']; task = make_task(user, 'private'); age(user, 100, task)
    result = preview(client, admin, user); assert result['allowed']
    # Legacy sessions are rejected; a concurrent activity write still invalidates
    # a previously issued deletion preview. Admin reads must not refresh activity.
    assert client.get('/auth/me', headers={'Authorization': 'Bearer ' + session['access_token']}).status_code == 401
    assert preview(client, admin, user)['allowed']
    with get_db() as conn:
        conn.execute('UPDATE users SET last_active_at=? WHERE id=?', (stamp(0), user['id']))
    assert remove(client, admin, user, result).status_code == 409
    assert not preview(client, admin, user)['allowed']


def test_data_changes_and_wrong_admin_or_target_invalidate_confirmation(client, identities):
    admin, session = identities; user = session['user']
    result = preview(client, admin, user)
    other = make_user('second_admin', role='admin')
    assert remove(client, other, user, result).status_code == 409
    assert remove(client, admin, other, result).status_code == 409
    with get_db() as conn: conn.execute('UPDATE users SET display_name=? WHERE id=?', ('changed', user['id']))
    assert remove(client, admin, user, result).status_code == 409
    headers = auth_headers(make_user('unauthorized_cleanup_user'))
    assert client.get(f"/admin/users/{user['id']}/deletion-preview", headers=headers).status_code == 403
    assert client.request('DELETE', f"/admin/users/{user['id']}", headers=headers, json={'confirmationToken': result['confirmationToken']}).status_code == 403


def private_plan(user, monkeypatch):
    make_partner()
    old = age(user, 100)
    monkeypatch.setattr(life, 'now', lambda: old)
    monkeypatch.setattr(life, 'expired', lambda run: False)  # Build a completed historical fixture without model work.
    payload = Submit(submission_id='cleanup-plan', request=DevelopmentRequest(target_partner_id='partner-1', development_direction='private'))
    accepted = life.create(payload, user)
    run = life.claim(accepted['run_id'])
    life.complete(run['id'], run['execution_token'], {'diagnoses': [], 'stages': [{'title': 'private stage', 'items': [{'title': 'private'}]}]}, [], lambda *_: None)
    return accepted


def test_full_private_plan_deletes_atomically_preserving_shared_partner(client, identities, monkeypatch):
    admin, session = identities; user = session['user']; private_plan(user, monkeypatch)
    result = preview(client, admin, user)
    assert result['allowed'], result
    assert {'development_runs', 'development_versions', 'development_version_items'} <= {x['key'] for x in result['privateData']}
    assert remove(client, admin, user, result).status_code == 204
    with get_db() as conn:
        for table, _, _ in cleanup.PRIVATE:
            assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM partners').fetchone()[0] == 1


@pytest.mark.parametrize('kind', ['transfer', 'cross_reference', 'running'])
def test_shared_and_running_plans_refused(client, identities, monkeypatch, kind):
    admin, session = identities; user = session['user']; accepted = private_plan(user, monkeypatch)
    with get_db() as conn:
        if kind == 'transfer':
            life.audit(conn, accepted['plan_id'], user['id'], 'transfer_copy')
        elif kind == 'cross_reference':
            conn.execute('INSERT INTO development_requests(id,owner_user_id,target_partner_id,payload_json,created_at,created_by) VALUES (?,?,?,?,?,?)',
                         ('other-request', admin['id'], 'partner-1', '{"source_task_id":"'+accepted['plan_id']+'"}', stamp(100), admin['id']))
        else:
            conn.execute("UPDATE development_runs SET status='running' WHERE id=?", (accepted['run_id'],))
    result = preview(client, admin, user)
    assert not result['allowed']


def test_delete_failure_rolls_back_everything(client_no_raise, identities, monkeypatch):
    admin, session = identities; user = session['user']; task = make_task(user, 'private'); age(user, 100, task)
    result = preview(client_no_raise, admin, user)
    original = cleanup.delete_private_history
    def fail(conn, uid):
        original(conn, uid)
        raise RuntimeError('injected failure after history deletion')
    monkeypatch.setattr(cleanup, 'delete_private_history', fail)
    assert remove(client_no_raise, admin, user, result).status_code == 500
    with get_db() as conn:
        assert conn.execute('SELECT 1 FROM users WHERE id=?', (user['id'],)).fetchone()
        assert conn.execute('SELECT 1 FROM match_records WHERE id=?', (task,)).fetchone()
        assert conn.execute('SELECT 1 FROM identity_credentials WHERE user_id=?', (user['id'],)).fetchone()
        assert conn.execute("SELECT count(*) FROM user_audit_logs WHERE action='admin.user_deleted'").fetchone()[0] == 0


def test_unknown_activity_does_not_expire_private_history(client, identities):
    admin, session = identities; user = session['user']; task = make_task(user, 'private'); age(user, 200, task)
    with get_db() as conn: conn.execute('UPDATE users SET last_active_at=NULL WHERE id=?', (user['id'],))
    result = preview(client, admin, user)
    assert not result['allowed'] and result['eligibleAfter'] is None


def test_new_public_reference_invalidates_previous_private_deletion(client, identities):
    admin, session = identities; user = session['user']; task = make_task(user, 'private'); old = age(user, 100, task)
    result = preview(client, admin, user); assert result['allowed']
    with get_db() as conn:
        conn.execute('INSERT INTO demand_profiles(id,match_record_id,requirement_text,created_at) VALUES (?,?,?,?)', ('late-public', task, 'public', old))
    response = remove(client, admin, user, result)
    assert response.status_code == 409 and '公共' in response.json()['detail']


def test_empty_identity_activity_change_invalidates_confirmation(client, identities):
    from .test_local_identity import browser as new_identity
    admin, _ = identities; session = new_identity(client).json(); user = session['user']; result = preview(client, admin, user)
    client.get('/auth/me', headers={'Authorization': 'Bearer ' + session['access_token']})
    response = remove(client, admin, user, result)
    assert response.status_code == 409 and '变化' in response.json()['detail']
