"""Account deletion revokes access without deleting or transferring business data."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from backend.app import user_cleanup as cleanup, development_lifecycle as life
from backend.app.auth import ALGORITHM
from backend.app.config import get_jwt_secret_key
from backend.app.database import get_db
from backend.app.development_types import DevelopmentRequest, Submit
from backend.app.storage_models import metadata as storage_metadata
from .conftest import auth_headers, make_user, make_task, make_partner
from .test_local_identity import browser, bearer, key_for, HEADERS, BROWSER_COOKIE
from .support.legacy_identity import legacy_browser, legacy_passkey


def preview(client, admin, user):
    response = client.get(f"/admin/users/{user['id']}/deletion-preview", headers=auth_headers(admin))
    assert response.status_code == 200, response.text
    return response.json()


def remove(client, admin, user, result):
    return client.request('DELETE', '/admin/users/' + user['id'], headers=auth_headers(admin),
                          json={'confirmationToken': result['confirmationToken'] or 'invalid'})


def business_snapshot():
    excluded = {'users', 'identity_credentials', 'identity_challenges', 'user_identity_keys',
                'revoked_identity_keys', 'user_audit_logs'}
    with get_db() as conn:
        return {table: sorted(json.dumps(dict(row), sort_keys=True) for row in conn.execute(f'SELECT * FROM {table}'))
                for table in storage_metadata.tables if table not in excluded}


@pytest.fixture
def identities(client):
    return make_user('cleanup_admin', role='admin'), browser(client)


def test_deletion_revokes_all_sessions_and_keys_but_preserves_user_and_audit(client, identities):
    admin, first = identities; user = first.json()['user']; key = key_for(client, first)
    second = client.post('/auth/identity/key/login', headers=HEADERS, json={'key': key})
    with get_db() as conn:
        conn.execute("INSERT INTO identity_credentials(id,user_id,kind,credential_id,public_key,created_at) VALUES ('old-passkey',?,'passkey','legacy-id','legacy-public-key',?)", (user['id'], user['created_at']))
        conn.execute("INSERT INTO identity_challenges(id,challenge,binding_hash,purpose,user_id,expires_at) VALUES ('challenge','challenge','binding','register',?,?)", (user['id'], user['created_at']))
    assert remove(client, admin, user, preview(client, admin, user)).status_code == 204
    for session in (first, second):
        assert client.get('/auth/me', headers=bearer(session)).status_code == 401
        assert client.get('/auth/identity/key', headers=bearer(session)).status_code == 401
        cookie = BROWSER_COOKIE+'='+session.cookies[BROWSER_COOKIE]
        assert browser(client, cookie, create=False).status_code == 404
    response = client.post('/auth/identity/key/login', headers=HEADERS, json={'key': key})
    assert response.status_code == 401 and response.json()['detail']['code'] == 'identity_deleted'
    with get_db() as conn:
        row = conn.execute('SELECT * FROM users WHERE id=?', (user['id'],)).fetchone()
        assert row['status'] == 'deleted' and row['token_version'] == 1
        for table in ('identity_credentials', 'identity_challenges', 'user_identity_keys'):
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE user_id=?', (user['id'],)).fetchone()[0] == 0
        log = conn.execute("SELECT * FROM user_audit_logs WHERE action='admin.user_deleted'").fetchone()
        assert log['actor_user_id'] == admin['id'] and log['target_user_id'] == user['id']
        assert datetime.fromisoformat(log['created_at']) >= datetime.fromisoformat(user['created_at'])
        assert json.loads(log['summary'])['business_data_preserved'] is True and key not in log['summary']
    logs = client.get('/admin/user-audit-logs', headers=auth_headers(admin)).json()['items']
    assert any(row['action'] == 'admin.user_deleted' and row['targetName'] == '已删除用户' for row in logs)
    assert client.get('/auth/me', headers=auth_headers(admin)).status_code == 200


@pytest.mark.parametrize('kind', ['key', 'browser', 'passkey', 'mixed', 'password', 'admin'])
@pytest.mark.parametrize('days', [0, 100])
def test_all_account_types_with_private_and_public_history_can_be_deleted(client, kind, days, monkeypatch):
    admin = make_user('cleanup_admin', role='admin')
    if kind == 'key': user = browser(client).json()['user']
    elif kind == 'browser': user = legacy_browser(client).json()['user']
    elif kind in ('passkey', 'mixed'):
        user = legacy_passkey(client)[0]['user']
        if kind == 'mixed':
            extra = legacy_browser(client).json()['user']
            with get_db() as conn: conn.execute('UPDATE identity_credentials SET user_id=? WHERE user_id=?', (user['id'], extra['id']))
    else: user = make_user('old_account', role='admin' if kind == 'admin' else 'user')
    task = make_task(user, 'preserved history')
    old = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with get_db() as conn:
        conn.execute('UPDATE users SET last_active_at=?,last_login_at=? WHERE id=?', (old, old, user['id']))
        conn.execute('INSERT INTO demand_profiles(id,match_record_id,requirement_text,created_at) VALUES (?,?,?,?)', ('demand', task, 'public', old))
        conn.execute('INSERT INTO project_opportunities(id,match_record_id,requirement_text,created_at,updated_at) VALUES (?,?,?,?,?)', ('opportunity', task, 'public', old, old))
        conn.execute('INSERT INTO capability_tag_suggestions(id,suggested_name,source_match_record_id,created_at,updated_at) VALUES (?,?,?,?,?)', ('suggestion', 'public', task, old, old))
        conn.execute('INSERT INTO feedback_issue(id,submitter_id,description,status,created_at,updated_at) VALUES (?,?,?,?,?,?)', ('feedback', user['id'], 'preserved feedback', 'pending', old, old))
        conn.execute("INSERT INTO enablement_resources(id,draft_json,created_by,created_at,updated_at) VALUES ('resource','{}',?,?,?)", (user['id'], old, old))
        conn.execute("INSERT INTO enablement_resource_versions(source_id,version,payload_json,authorization_epoch,reviewed_revision,published_by,published_at) VALUES ('resource',1,'{}',1,1,?,?)", (user['id'], old))
    monkeypatch.setenv('BROWSER_IDENTITY_RETENTION_DAYS', 'invalid-unused-value')
    before = business_snapshot()
    result = preview(client, admin, user); assert result['allowed'], result
    assert remove(client, admin, user, result).status_code == 204
    assert business_snapshot() == before
    headers = auth_headers(admin)
    task_detail = client.get('/agent/tasks/'+task, headers=headers).json()
    assert task_detail['createdBy'] == '已删除用户'
    assert client.get('/admin/feedback/feedback', headers=headers).json()['submitter'] == '已删除用户'
    assert client.get('/admin/feedback', headers=headers).json()['items'][0]['submitter'] == '已删除用户'


def private_plan(user):
    make_partner()
    accepted = life.create(Submit(submission_id='cleanup-plan', request=DevelopmentRequest(
        target_partner_id='partner-1', development_direction='private')), user)
    run = life.claim(accepted['run_id'])
    life.complete(run['id'], run['execution_token'], {'diagnoses': [], 'stages': [{'title': 'private stage', 'items': [{'title': 'private', 'source_type':'course', 'source_id':'historical-unavailable-resource', 'source_version':1}]}]}, [], lambda *_: None)
    return accepted


def test_completed_plan_versions_shared_references_and_permissions_are_unchanged(client, identities):
    admin, session = identities; user = session.json()['user']; accepted = private_plan(user)
    other = browser(client); other_user = other.json()['user']
    with get_db() as conn:
        life.audit(conn, accepted['plan_id'], user['id'], 'transfer_copy')
        conn.execute('INSERT INTO development_requests(id,owner_user_id,target_partner_id,payload_json,created_at,created_by) VALUES (?,?,?,?,?,?)',
                     ('other-request', other_user['id'], 'partner-1', json.dumps({'source_task_id': accepted['plan_id']}), user['created_at'], other_user['id']))
    before = business_snapshot()
    assert remove(client, admin, user, preview(client, admin, user)).status_code == 204
    assert business_snapshot() == before
    assert client.get('/development/plans/'+accepted['plan_id'], headers=bearer(other)).status_code == 404
    assert client.get('/development/plans/'+accepted['plan_id'], headers=auth_headers(admin)).status_code == 200
    tasks = client.get('/admin/tasks', headers=auth_headers(admin)).json()['items']
    assert next(task for task in tasks if task['id'] == accepted['plan_id'])['ownerName'] == '已删除用户'


def test_new_identity_never_inherits_deleted_history(client, identities):
    admin, old = identities; user = old.json()['user']; key = key_for(client, old)
    task = make_task(user, 'retained private task')
    assert remove(client, admin, user, preview(client, admin, user)).status_code == 204
    new = browser(client, BROWSER_COOKIE+'='+old.cookies[BROWSER_COOKIE])
    assert new.json()['created'] and new.json()['user']['id'] != user['id']
    assert key_for(client, new) != key
    assert client.get('/agent/tasks/'+task, headers=bearer(new)).status_code == 404
    assert not client.get('/agent/tasks', headers=bearer(new)).json()['items']
    assert client.get('/agent/tasks/'+task, headers=auth_headers(admin)).status_code == 200


@pytest.mark.parametrize('role', ['user', 'admin'])
def test_deleted_account_hidden_and_never_reenabled(client, role):
    admin = make_user('operator', role='admin'); user = make_user('target', role=role)
    old_headers = auth_headers(user)
    result = preview(client, admin, user)
    assert remove(client, admin, user, result).status_code == 204
    headers = auth_headers(admin)
    for query in ('', '?status=active', '?status=disabled', '?keyword=target', '?role='+role):
        assert user['id'] not in {row['id'] for row in client.get('/admin/users'+query, headers=headers).json()['items']}
    assert client.get('/admin/users/'+user['id'], headers=headers).status_code == 404
    assert client.get('/admin/users/'+user['id']+'/deletion-preview', headers=headers).status_code == 404
    assert remove(client, admin, user, result).status_code == 404
    assert client.patch('/admin/users/'+user['id'], headers=headers, json={'display_name':'restored'}).status_code == 404
    for status in ('active', 'disabled'):
        assert client.patch('/admin/users/'+user['id']+'/status', headers=headers, json={'status':status}).status_code == 404
    for action in ('reset-password', 'unlock'):
        assert client.post('/admin/users/'+user['id']+'/'+action, headers=headers).status_code == 404
    assert client.get('/auth/me', headers=old_headers).status_code == 401
    assert client.post('/auth/admin/login', json={'username':user['username'],'password':user['password']}).status_code == 401


def test_current_operator_cannot_delete_self(client):
    admin = make_user('operator', role='admin')
    result = preview(client, admin, admin)
    assert not result['allowed'] and '当前操作账号' in result['reason']
    assert remove(client, admin, admin, result).status_code == 409


def test_last_usable_admin_cannot_be_deleted_by_locked_admin_session(client):
    # Temporary login lock does not invalidate an existing admin session, but
    # that locked account cannot substitute for the last usable login account.
    admin = make_user('locked-operator', role='admin', locked_until='2999-01-01T00:00:00+00:00')
    target = make_user('only-usable-admin', role='admin')
    with get_db() as conn: conn.execute("UPDATE users SET status='disabled' WHERE username='bootstrap_admin'")
    result = preview(client, admin, target)
    assert not result['allowed'] and '最后一个可用管理员' in result['reason']


@pytest.mark.parametrize('kind,state', [('match','matching'),('match','enriching'),('plan','pending'),('plan','running')])
def test_running_task_blocks_deletion_even_after_confirmation(client, identities, kind, state):
    admin, session = identities; user = session.json()['user']
    result = preview(client, admin, user); assert result['allowed']
    if kind == 'match': make_task(user, 'in progress', task_status=state)
    else:
        accepted = private_plan(user)
        with get_db() as conn: conn.execute('UPDATE development_runs SET status=? WHERE id=?', (state, accepted['run_id']))
    latest = preview(client, admin, user)
    assert not latest['allowed'] and '任务结束后再删除' in latest['reason']
    response = remove(client, admin, user, result)
    assert response.status_code == 409 and '任务结束后再删除' in response.json()['detail']


def test_history_and_activity_added_after_confirmation_do_not_block_delete(client, identities):
    admin, session = identities; user = session.json()['user']
    result = preview(client, admin, user)
    task = make_task(user, 'history after preview')
    assert client.get('/auth/me', headers=bearer(session)).status_code == 200
    before = business_snapshot()
    assert remove(client, admin, user, result).status_code == 204
    assert business_snapshot() == before


def test_confirmation_binding_expiry_and_authorization(client, identities):
    admin, session = identities; user = session.json()['user']; result = preview(client, admin, user)
    other = make_user('second_admin', role='admin')
    assert remove(client, other, user, result).status_code == 409
    assert remove(client, admin, other, result).status_code == 409
    payload = jwt.decode(result['confirmationToken'], get_jwt_secret_key(), algorithms=[ALGORITHM])
    payload['exp'] = 0
    expired = {'confirmationToken':jwt.encode(payload, get_jwt_secret_key(), algorithm=ALGORITHM)}
    assert remove(client, admin, user, expired).status_code == 409
    headers = bearer(browser(client))
    assert client.get('/admin/users/'+user['id']+'/deletion-preview', headers=headers).status_code == 403
    assert client.delete('/admin/users/'+user['id'], headers=headers, json={'confirmationToken':result['confirmationToken']}).status_code == 403
    assert client.patch('/admin/users/'+user['id']+'/status', headers=auth_headers(admin), json={'status':'disabled'}).status_code == 200
    assert remove(client, admin, user, result).status_code == 409


def test_transaction_failure_rolls_back_deletion_revocation_and_audit(client_no_raise, identities, monkeypatch):
    admin, session = identities; user = session.json()['user']; key = key_for(client_no_raise, session)
    make_task(user, 'preserved'); before = business_snapshot()
    result = preview(client_no_raise, admin, user)
    def fail(*args, **kwargs): raise RuntimeError('isolated audit failure after account deletion')
    monkeypatch.setattr(cleanup, 'record_audit', fail)
    assert remove(client_no_raise, admin, user, result).status_code == 500
    assert business_snapshot() == before
    with get_db() as conn:
        assert conn.execute('SELECT status,token_version FROM users WHERE id=?', (user['id'],)).fetchone()[0] == 'active'
        assert conn.execute('SELECT count(*) FROM revoked_identity_keys').fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM user_audit_logs WHERE action='admin.user_deleted'").fetchone()[0] == 0
    assert client_no_raise.get('/auth/me', headers=bearer(session)).status_code == 200
    assert client_no_raise.post('/auth/identity/key/login', headers=HEADERS, json={'key':key}).status_code == 200


def test_concurrent_admin_deletes_leave_a_valid_admin(client):
    first = make_user('first_admin', role='admin'); second = make_user('second_admin', role='admin')
    with get_db() as conn: conn.execute("UPDATE users SET status='disabled' WHERE username='bootstrap_admin'")
    first_preview = preview(client, first, second); second_preview = preview(client, second, first)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda args: remove(client, *args), [(first,second,first_preview), (second,first,second_preview)]))
    assert sorted(response.status_code for response in responses) == [204, 401]
    with get_db() as conn:
        assert conn.execute("SELECT count(*) FROM users WHERE role='admin' AND status='active'").fetchone()[0] == 1


@pytest.mark.parametrize('entry', ['task', 'match', 'retry', 'plan'])
def test_deletion_during_scope_check_cannot_start_a_task(client, identities, monkeypatch, entry):
    from backend.app.routers import match as matching
    import uuid
    admin, session = identities; user = session.json()['user']
    if entry == 'plan': make_partner()
    task_id = make_task(user, 'retry after scope', task_status='failed') if entry == 'retry' else None
    def delete_in_gate(*args, **kwargs):
        assert remove(client, admin, user, preview(client, admin, user)).status_code == 204
    monkeypatch.setattr(matching if entry != 'plan' else life, 'require_scope', delete_in_gate)
    path, payload = {
        'task': ('/agent/tasks', {'requestId':str(uuid.uuid4()), 'requirement':'伙伴推荐'}),
        'match': ('/agent/match', {'requirement':'伙伴推荐'}),
        'retry': ('/agent/tasks/'+str(task_id)+'/retry', {}),
        'plan': ('/development/plans', {'submission_id':'delete-in-scope','request':{'target_partner_id':'partner-1','development_direction':'发展方向'}}),
    }[entry]
    response = client.post(path, headers=bearer(session), json=payload)
    assert response.status_code == 401, response.text
    with get_db() as conn:
        assert conn.execute("SELECT count(*) FROM match_records WHERE task_status IN ('matching','enriching')").fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM development_plans').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM development_runs').fetchone()[0] == 0


@pytest.mark.parametrize('kind', ['resource', 'case'])
def test_published_resource_permissions_reviews_and_files_survive_admin_deletion(client, kind):
    from .test_enablement import create, grant, published
    from backend.app import enablement as service
    from backend.app.database import UPLOADS_DIR
    admin = make_user('operator', role='admin'); creator = make_user('publisher', role='admin')
    with get_db() as conn: tag = conn.execute('SELECT id FROM capability_tags WHERE enabled=1 LIMIT 1').fetchone()[0]
    metadata = {'resource_type':'course','title':'保留资源','summary':'仅测试','level':'basic',
                'source_url':'https://example.com/course'}
    row = published(grant(create(creator, metadata, kind), creator, kind, flags=(True,False,False)), creator, kind)
    source_type = 'case' if kind == 'case' else 'course'
    reader = browser(client); headers = bearer(reader)
    path = '/enablement/resources/'+source_type+'/'+row['source_id']
    assert client.get(path, headers=headers).status_code == 200
    assert client.post(path+'/redirect', headers=headers, json={'source_version':1}).status_code == 200
    with get_db() as conn:
        stamp = datetime.now(timezone.utc).isoformat()
        conn.execute('INSERT INTO feedback_issue(id,submitter_id,description,created_at,updated_at) VALUES (?,?,?,?,?)', ('with-file',creator['id'],'retain image',stamp,stamp))
        conn.execute('INSERT INTO feedback_attachment(id,issue_id,filename,storage_name,content_type,size_bytes,created_at) VALUES (?,?,?,?,?,?,?)', ('file','with-file','image.png','test.png','image/png',8,stamp))
    file = UPLOADS_DIR/'feedback'/'test.png'; file.parent.mkdir(parents=True,exist_ok=True); file.write_bytes(b'fixture!')
    before = business_snapshot()
    assert remove(client, admin, creator, preview(client, admin, creator)).status_code == 204
    assert business_snapshot() == before and file.read_bytes() == b'fixture!'
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    if kind == 'case': assert response.json()['review']['reviewer_name'] == '已删除用户'
    with get_db() as conn:
        assert service.row_for(conn,kind,row['source_id'])['model_allowed'] == 0
    assert client.get('/admin/feedback/with-file/attachments/file', headers=auth_headers(admin)).content == b'fixture!'
    result = service.detail(kind,row['source_id'])
    if kind == 'case': assert result['reviews'][0]['reviewer_name'] == '已删除用户'
    else: assert not result['reviews']
