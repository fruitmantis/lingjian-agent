"""Ordinary long-lived Key contract. Every record lives in isolated test storage."""
import json
import secrets
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from backend.app.auth import create_token
from backend.app.database import get_db
from backend.app.identity_keys import digest, reveal_identity_key
from backend.app.routers.local_identity import BROWSER_COOKIE, KEY_LOGIN_MAX_BODY_BYTES
from .conftest import auth_headers, make_user, make_task

HEADERS = {'Origin': 'http://localhost:3000'}


def browser(client, cookie=None, create=True):
    return client.post('/auth/identity/session', json={'create': create},
                       headers={**HEADERS, **({'Cookie': cookie} if cookie else {})})


def bearer(response):
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def key_for(client, response):
    value = client.get('/auth/identity/key', headers=bearer(response))
    assert value.status_code == 200 and value.headers['cache-control'] == 'no-store'
    return value.json()['key']


def counts():
    with get_db() as conn:
        return tuple(conn.execute('SELECT count(*) FROM ' + table).fetchone()[0]
                     for table in ('users', 'user_identity_keys', 'identity_credentials'))


def test_first_visit_creates_one_encrypted_key_and_restores_same_identity(client):
    first = browser(client)
    assert first.status_code == 200 and first.json()['created'] is True
    user = first.json()['user']; key = key_for(client, first)
    assert len(key) == 46 and user['identity_method'] == 'key' and user['role'] == 'user'
    cookie = BROWSER_COOKIE + '=' + first.cookies[BROWSER_COOKIE]
    before = counts()
    for _ in range(3):
        restored = browser(client, cookie)
        assert restored.json()['created'] is False and restored.json()['user']['id'] == user['id']
        assert key_for(client, restored) == key
    assert counts() == before
    assert 'HttpOnly' in first.headers['set-cookie'] and 'SameSite=strict' in first.headers['set-cookie']
    with get_db() as conn:
        row = conn.execute('SELECT * FROM user_identity_keys WHERE user_id=?', (user['id'],)).fetchone()
        assert row['key_hash'] == digest(key) and key not in row['encrypted_key']
        assert reveal_identity_key(row) == key
        assert conn.execute('SELECT hashed_password FROM users WHERE id=?', (user['id'],)).fetchone()[0] is None
        audits = [dict(r) for r in conn.execute('SELECT * FROM user_audit_logs')]
        assert key not in json.dumps(audits)
    assert 'key' not in user


def test_key_restores_history_after_cookie_loss_and_never_adds_user(client):
    first = browser(client); user = first.json()['user']; key = key_for(client, first)
    task = make_task(user, 'original private task')
    before = counts()
    restored = client.post('/auth/identity/key/login', headers=HEADERS, json={'key': '  '+key+'\n'})
    assert restored.status_code == 200 and restored.json()['user']['id'] == user['id']
    assert counts()[:2] == before[:2]
    assert key_for(client, restored) == key
    assert client.get('/agent/tasks/'+task, headers=bearer(restored)).status_code == 200
    assert browser(client, BROWSER_COOKIE+'='+restored.cookies[BROWSER_COOKIE]).json()['user']['id'] == user['id']
    other = browser(client)
    assert key_for(client, other) != key
    assert client.get('/agent/tasks/'+task, headers=bearer(other)).status_code == 404
    # Owner-only credential endpoint has no caller-selected user ID.
    assert client.get('/auth/identity/key?user_id='+user['id'], headers=bearer(other)).json()['key'] != key
    assert client.get('/auth/identity/key').status_code == 401


@pytest.mark.parametrize('value', [
    'wrong', '', 'bf_'+secrets.token_urlsafe(32), 'x'*300, 123, {'key':'fake'},
    "bf_' OR 1=1--", 'bf_<script>alert(1)</script>', 'bf_$(id)', 'bf_../../etc/passwd',
])
def test_wrong_key_never_creates_or_echoes_secret(client, value):
    before = counts()
    response = client.post('/auth/identity/key/login', headers=HEADERS, json={'key': value})
    assert response.status_code == 401
    code = 'unknown_key' if isinstance(value, str) and value.startswith('bf_') and len(value) == 46 else 'invalid_key'
    assert response.json()['detail']['code'] == code
    assert response.headers['cache-control'] == 'no-store'
    assert 'set-cookie' not in response.headers and counts() == before


@pytest.mark.parametrize('transport', ['declared', 'chunked', 'misdeclared', 'single-chunk', 'utf8'])
def test_key_login_rejects_large_body_before_parsing_or_database(client, monkeypatch, transport):
    from backend.app.routers import local_identity
    identity = browser(client); key = key_for(client, identity)
    admin = auth_headers(make_user('body_limit_admin', role='admin'))
    before = counts()
    headers = {**HEADERS, 'Content-Type': 'application/json',
               'Cookie': BROWSER_COOKIE+'='+identity.cookies[BROWSER_COOKIE]}
    if transport == 'declared':
        headers['Content-Length'] = str(KEY_LOGIN_MAX_BODY_BYTES + 1)
    elif transport == 'misdeclared':
        headers['Content-Length'] = '1'
    payload = json.dumps({'key': key}).encode()
    if transport == 'utf8':
        payload = json.dumps({'key': key, 'extra': '界'*1500}, ensure_ascii=False).encode()
        assert len(payload.decode()) < KEY_LOGIN_MAX_BODY_BYTES < len(payload)
        chunks = [payload]
    elif transport == 'single-chunk':
        chunks = [payload + b' ' * KEY_LOGIN_MAX_BODY_BYTES]
    else:
        chunks = [payload, b' '*(KEY_LOGIN_MAX_BODY_BYTES-len(payload)), b' ']
    consumed = []
    async def body():
        for chunk in chunks:
            consumed.append(len(chunk))
            yield chunk
        raise AssertionError('Oversized request must stop reading immediately')
    def forbidden(*args, **kwargs):
        raise AssertionError('Oversized request must not parse JSON or access storage')
    with monkeypatch.context() as patch:
        patch.setattr(local_identity, 'json', SimpleNamespace(loads=forbidden))
        patch.setattr(local_identity, 'get_db', forbidden)
        response = client.post('/auth/identity/key/login', headers=headers, content=body())
    assert response.status_code == 413
    assert response.json()['detail']['code'] == 'request_too_large'
    assert response.headers['cache-control'] == 'no-store' and response.headers['pragma'] == 'no-cache'
    assert key not in response.text and 'set-cookie' not in response.headers
    assert consumed == ([] if transport == 'declared' else [len(chunk) for chunk in chunks])
    assert counts() == before
    assert client.get('/auth/me', headers=bearer(identity)).status_code == 200
    assert browser(client, headers['Cookie'], create=False).json()['user']['id'] == identity.json()['user']['id']
    assert client.get('/auth/me', headers=admin).status_code == 200


@pytest.mark.parametrize('chunked', [False, True])
def test_key_login_accepts_body_at_byte_limit_and_restores_history(client, chunked):
    identity = browser(client); key = key_for(client, identity)
    task = make_task(identity.json()['user'], 'body limit history')
    before = counts()
    payload = json.dumps({'key': key, 'extra': ''}).encode()
    payload = payload[:-2] + b'x'*(KEY_LOGIN_MAX_BODY_BYTES-len(payload)) + payload[-2:]
    assert len(payload) == KEY_LOGIN_MAX_BODY_BYTES
    async def body():
        for start in range(0, len(payload), 37):
            yield payload[start:start+37]
    response = client.post('/auth/identity/key/login', headers={**HEADERS, 'Content-Type': 'application/json'},
                           content=body() if chunked else payload)
    assert response.status_code == 200 and response.json()['user']['id'] == identity.json()['user']['id']
    assert counts()[:2] == before[:2] and key_for(client, response) == key
    assert client.get('/agent/tasks/'+task, headers=bearer(response)).status_code == 200


@pytest.mark.parametrize('payload', [b'{"key": "broken', b'{"key":"\xff"}', b'['*1500+b']'*1500])
def test_key_login_malformed_small_body_is_safe_and_never_reaches_storage(client, monkeypatch, payload):
    from backend.app.routers import local_identity
    before = counts()
    def forbidden():
        raise AssertionError('Malformed JSON must not reach storage')
    with monkeypatch.context() as patch:
        patch.setattr(local_identity, 'get_db', forbidden)
        response = client.post('/auth/identity/key/login', headers={**HEADERS, 'Content-Type': 'application/json'}, content=payload)
    assert response.status_code == 401 and response.json()['detail']['code'] == 'invalid_key'
    assert response.headers['cache-control'] == 'no-store' and 'set-cookie' not in response.headers
    assert counts() == before


def test_explicit_logout_revokes_only_current_browser_preserves_key_history_and_admin(client):
    first = browser(client); key = key_for(client, first); user = first.json()['user']; task = make_task(user, 'kept')
    other_device = client.post('/auth/identity/key/login', headers=HEADERS, json={'key': key})
    admin = make_user('independent_admin', role='admin'); admin_headers = auth_headers(admin)
    cookie = BROWSER_COOKIE+'='+first.cookies[BROWSER_COOKIE]
    response = client.post('/auth/identity/logout', headers={**HEADERS, **bearer(first), 'Cookie':cookie})
    assert response.status_code == 200 and response.json() == {'remembered': True}
    assert response.cookies[BROWSER_COOKIE] != first.cookies[BROWSER_COOKIE]
    assert 'HttpOnly' in response.headers['set-cookie'] and 'access_token' not in response.json()
    assert client.get('/auth/me', headers=bearer(first)).status_code == 401
    assert browser(client, cookie, create=False).status_code == 404
    assert client.get('/agent/tasks/'+task, headers=bearer(other_device)).status_code == 200
    assert client.get('/auth/me', headers=admin_headers).status_code == 200
    assert key_for(client, other_device) == key
    before = counts()
    restored = browser(client, BROWSER_COOKIE+'='+response.cookies[BROWSER_COOKIE], create=False)
    assert restored.json()['user']['id'] == user['id'] and restored.json()['created'] is False
    assert counts() == before and key_for(client, restored) == key
    assert client.get('/agent/tasks/'+task, headers=bearer(restored)).status_code == 200
    assert client.post('/auth/logout-all', headers=admin_headers).status_code == 204
    assert client.get('/auth/me', headers=bearer(restored)).status_code == 200


def test_key_switch_revokes_previous_browser_session_without_merging(client):
    a,b = browser(client), browser(client); before = counts(); key = key_for(client,b)
    failed = client.post('/auth/identity/key/login', headers={**HEADERS,'Cookie':BROWSER_COOKIE+'='+a.cookies[BROWSER_COOKIE]},json={'key':'wrong'})
    assert failed.status_code == 401 and client.get('/auth/me',headers=bearer(a)).status_code == 200
    changed = client.post('/auth/identity/key/login', headers={**HEADERS,'Cookie':BROWSER_COOKIE+'='+a.cookies[BROWSER_COOKIE]},json={'key':key})
    assert changed.json()['user']['id'] == b.json()['user']['id'] and counts() == before
    assert client.get('/auth/me',headers=bearer(a)).status_code == 401


def test_admin_and_legacy_auth_boundaries(client):
    user = browser(client); admin = make_user('password_admin',role='admin')
    assert client.get('/auth/identity/key',headers=auth_headers(admin)).status_code == 403
    assert client.get('/admin/users',headers=bearer(user)).status_code == 403
    assert client.post('/auth/admin/login',json={'username':user.json()['user']['username'],'password':'any'}).status_code == 401
    assert client.post('/auth/change-password',headers=bearer(user),json={'current_password':'old','new_password':'Password123'}).status_code == 403
    assert client.post('/auth/admin/login',json={'username':admin['username'],'password':admin['password']}).status_code == 200
    legacy = make_user('legacy_user')
    with get_db() as conn:
        before = dict(conn.execute('SELECT * FROM users WHERE id=?',(legacy['id'],)).fetchone())
    for method in ['password','passkey','browser','key']:
        token = create_token(legacy['id'],legacy['username'],'user',auth_method=method)
        assert client.get('/auth/me',headers={'Authorization':'Bearer '+token}).status_code == 401
    for path in ['/auth/login','/auth/identity/browser','/auth/identity/passkey/register/options','/auth/identity/passkey/authenticate/options']:
        assert client.post(path,headers=HEADERS,json={}).status_code == 404
    with get_db() as conn:
        assert dict(conn.execute('SELECT * FROM users WHERE id=?',(legacy['id'],)).fetchone()) == before
        assert not conn.execute('SELECT 1 FROM user_identity_keys WHERE user_id=?',(legacy['id'],)).fetchone()


def test_disabled_key_does_not_create_new_identity(client):
    first=browser(client);key=key_for(client,first);cookie=BROWSER_COOKIE+'='+first.cookies[BROWSER_COOKIE]
    with get_db() as conn:conn.execute("UPDATE users SET status='disabled' WHERE id=?",(first.json()['user']['id'],))
    before=counts()
    assert browser(client,cookie).status_code==401
    assert client.post('/auth/identity/key/login',headers=HEADERS,json={'key':key}).status_code==401
    assert client.get('/auth/identity/key',headers=bearer(first)).status_code==401
    assert counts()==before


def test_origin_rate_limit_and_transaction_rollback(client_no_raise,monkeypatch):
    from backend.app.routers import local_identity
    assert client_no_raise.post('/auth/identity/session',json={'create':True}).status_code==403
    before=counts()
    original=local_identity.make_user
    def fail(conn,user_id):original(conn,user_id);raise RuntimeError('isolated rollback')
    monkeypatch.setattr(local_identity,'make_user',fail)
    response=browser(client_no_raise)
    assert response.status_code==500 and 'set-cookie' not in response.headers and counts()==before
    local_identity._ATTEMPTS.clear()
    for _ in range(60):assert browser(client_no_raise,create=False).status_code==404
    assert browser(client_no_raise,create=False).status_code==429


def test_cipher_fails_closed_and_does_not_rotate_key(client,monkeypatch):
    first=browser(client);key=key_for(client,first);before=counts()
    monkeypatch.setenv('BANFEI_IDENTITY_ENCRYPTION_KEY',Fernet.generate_key().decode())
    response=client.get('/auth/identity/key',headers=bearer(first))
    assert response.status_code==503 and key not in response.text and counts()==before
    monkeypatch.delenv('BANFEI_IDENTITY_ENCRYPTION_KEY')
    from backend.app.main import initialize_application
    with pytest.raises(RuntimeError,match='BANFEI_IDENTITY_ENCRYPTION_KEY'):initialize_application()


def test_admin_projection_never_exposes_key_and_cleanup_preserves_history(client):
    admin=make_user('key_admin',role='admin');headers=auth_headers(admin)
    first=browser(client);uid=first.json()['user']['id'];key=key_for(client,first)
    detail=client.get('/admin/users/'+uid,headers=headers)
    assert detail.json()['auth_methods']==['key'] and key not in detail.text
    assert key not in client.get('/admin/users',headers=headers).text
    preview=client.get('/admin/users/'+uid+'/deletion-preview',headers=headers).json()
    assert preview['allowed'] and preview['credentialCount']==2
    make_task(first.json()['user'],'preserved')
    assert not client.get('/admin/users/'+uid+'/deletion-preview',headers=headers).json()['allowed']
    empty=browser(client);empty_id=empty.json()['user']['id'];empty_key=key_for(client,empty)
    preview=client.get('/admin/users/'+empty_id+'/deletion-preview',headers=headers).json()
    assert client.delete('/admin/users/'+empty_id,headers=headers,json={'confirmationToken':preview['confirmationToken']}).status_code==204
    assert client.post('/auth/identity/key/login',headers=HEADERS,json={'key':empty_key}).status_code==401


def test_bearer_without_valid_browser_session_cannot_impersonate_owner(client):
    first, other = browser(client), browser(client)
    from backend.app.auth import decode_token
    owner = first.json()['user']; other_claims = decode_token(other.json()['access_token'])
    for session_id in (None, 'forged', other_claims['sid']):
        token = create_token(owner['id'],owner['username'],'user',auth_method='key',session_id=session_id)
        assert client.get('/auth/identity/key',headers={'Authorization':'Bearer '+token}).status_code == 401
    response = client.post('/auth/identity/logout',headers={**HEADERS,**bearer(first)})
    assert response.status_code == 200 and response.json()['remembered']
    restored = browser(client,BROWSER_COOKIE+'='+response.cookies[BROWSER_COOKIE],create=False)
    assert restored.json()['user']['id'] == owner['id']
    assert client.get('/auth/me',headers=bearer(first)).status_code == 401
    assert client.get('/auth/me',headers=bearer(other)).status_code == 200


def test_ciphertext_is_bound_to_owner_and_http_login_errors_are_secret_free(client):
    a,b = browser(client),browser(client); a_key = key_for(client,a); b_key = key_for(client,b)
    with get_db() as conn:
        other = conn.execute('SELECT encrypted_key FROM user_identity_keys WHERE user_id=?',(b.json()['user']['id'],)).fetchone()[0]
        conn.execute('UPDATE user_identity_keys SET encrypted_key=? WHERE user_id=?',(other,a.json()['user']['id']))
    response = client.get('/auth/identity/key',headers=bearer(a))
    assert response.status_code == 503 and a_key not in response.text and b_key not in response.text
    response = client.post('/auth/identity/key/login',headers=HEADERS,content='{"key": "broken')
    assert response.status_code == 401 and response.json()['detail']['code'] == 'invalid_key'


def test_logout_replay_or_unproven_identity_cannot_create_remembered_credentials(client):
    first=browser(client)
    signed_out=client.post('/auth/identity/logout',headers={**HEADERS,**bearer(first)})
    cookie=BROWSER_COOKIE+'='+signed_out.cookies[BROWSER_COOKIE]
    before=counts()
    for headers in (HEADERS, {**HEADERS,**bearer(first)}, {**HEADERS,'Cookie':BROWSER_COOKIE+'=forged'}):
        response=client.post('/auth/identity/logout',headers=headers)
        assert response.status_code==200 and response.json()=={'remembered':False}
        assert 'Max-Age=0' in response.headers['set-cookie'] and counts()==before
    restored=browser(client,cookie,create=False)
    assert restored.json()['user']['id']==first.json()['user']['id']


def test_logout_remembrance_rejects_expired_version_and_disabled_user(client):
    first=browser(client);uid=first.json()['user']['id']
    with get_db() as conn:conn.execute('UPDATE users SET token_version=token_version+1 WHERE id=?',(uid,))
    response=client.post('/auth/identity/logout',headers={**HEADERS,**bearer(first)})
    assert response.json()=={'remembered':False}
    second=browser(client)
    with get_db() as conn:conn.execute("UPDATE users SET status='disabled' WHERE id=?",(second.json()['user']['id'],))
    response=client.post('/auth/identity/logout',headers={**HEADERS,**bearer(second),'Cookie':BROWSER_COOKIE+'='+second.cookies[BROWSER_COOKIE]})
    assert response.json()=={'remembered':False}


def test_logout_failure_rolls_back_revocation(client_no_raise,monkeypatch):
    from backend.app.routers import local_identity
    first=browser(client_no_raise);before=counts()
    def fail(*_):raise RuntimeError('isolated remembered binding failure')
    monkeypatch.setattr(local_identity,'add_browser_session',fail)
    response=client_no_raise.post('/auth/identity/logout',headers={**HEADERS,**bearer(first),'Cookie':BROWSER_COOKIE+'='+first.cookies[BROWSER_COOKIE]})
    assert response.status_code==500 and 'set-cookie' not in response.headers and counts()==before
    assert client_no_raise.get('/auth/me',headers=bearer(first)).status_code==200
    assert browser(client_no_raise,BROWSER_COOKIE+'='+first.cookies[BROWSER_COOKIE],create=False).json()['user']['id']==first.json()['user']['id']


def delete_key_user(client, admin_headers, user_id):
    preview = client.get('/admin/users/'+user_id+'/deletion-preview', headers=admin_headers)
    assert preview.json()['allowed']
    return client.delete('/admin/users/'+user_id, headers=admin_headers,
                         json={'confirmationToken': preview.json()['confirmationToken']})


def test_deleted_key_is_identified_without_exposing_key_or_changing_other_browser(client):
    admin = auth_headers(make_user('revocation_admin', role='admin'))
    deleted = browser(client); key = key_for(client, deleted); uid = deleted.json()['user']['id']
    other = browser(client); other_cookie = BROWSER_COOKIE+'='+other.cookies[BROWSER_COOKIE]
    assert delete_key_user(client, admin, uid).status_code == 204
    before = counts()
    response = client.post('/auth/identity/key/login', headers={**HEADERS, 'Cookie': other_cookie}, json={'key': key})
    assert response.status_code == 401 and response.json()['detail']['code'] == 'identity_deleted'
    assert response.json()['detail']['browser_identity_available'] is True
    own = client.post('/auth/identity/key/login', headers={**HEADERS, 'Cookie': BROWSER_COOKIE+'='+deleted.cookies[BROWSER_COOKIE]}, json={'key': key})
    assert own.json()['detail']['browser_identity_available'] is False
    assert response.headers['cache-control'] == 'no-store' and 'set-cookie' not in response.headers
    assert key not in response.text and uid not in response.text and counts() == before
    assert client.get('/auth/me', headers=bearer(deleted)).status_code == 401
    assert browser(client, BROWSER_COOKIE+'='+deleted.cookies[BROWSER_COOKIE], create=False).status_code == 404
    assert client.get('/auth/me', headers=bearer(other)).status_code == 200
    assert client.get('/auth/me', headers=admin).status_code == 200
    with get_db() as conn:
        records = [dict(row) for row in conn.execute('SELECT * FROM revoked_identity_keys')]
        assert len(records) == 1 and set(records[0]) == {'key_hash', 'revoked_at'}
        assert records[0]['key_hash'] == digest(key)
        assert key not in json.dumps(records) and uid not in json.dumps(records)
        assert not conn.execute('SELECT * FROM user_identity_keys WHERE user_id=?', (uid,)).fetchone()
        audits = json.dumps([dict(row) for row in conn.execute('SELECT * FROM user_audit_logs')])
        assert key not in audits and digest(key) not in audits


def test_deletion_failure_rolls_back_revoked_key_and_all_credentials(client_no_raise, monkeypatch):
    from backend.app import user_cleanup
    admin = auth_headers(make_user('rollback_revocation_admin', role='admin'))
    identity = browser(client_no_raise); key = key_for(client_no_raise, identity)
    before = counts()
    def fail(*args, **kwargs): raise RuntimeError('isolated late deletion failure')
    monkeypatch.setattr(user_cleanup, 'record_audit', fail)
    assert delete_key_user(client_no_raise, admin, identity.json()['user']['id']).status_code == 500
    assert counts() == before
    with get_db() as conn:
        assert conn.execute('SELECT count(*) FROM revoked_identity_keys').fetchone()[0] == 0
    assert client_no_raise.post('/auth/identity/key/login', headers=HEADERS, json={'key': key}).status_code == 200


def test_disabled_and_legacy_missing_keys_have_distinct_codes_and_no_revocation(client):
    identity = browser(client); key = key_for(client, identity); uid = identity.json()['user']['id']
    with get_db() as conn: conn.execute("UPDATE users SET status='disabled' WHERE id=?", (uid,))
    disabled = client.post('/auth/identity/key/login', headers=HEADERS, json={'key': key})
    assert disabled.json()['detail']['code'] == 'identity_disabled' and 'set-cookie' not in disabled.headers
    assert browser(client, BROWSER_COOKIE+'='+identity.cookies[BROWSER_COOKIE]).json()['detail']['code'] == 'identity_disabled'
    with get_db() as conn:
        assert conn.execute('SELECT count(*) FROM revoked_identity_keys').fetchone()[0] == 0
        conn.execute('DELETE FROM identity_credentials WHERE user_id=?', (uid,))
        conn.execute('DELETE FROM user_identity_keys WHERE user_id=?', (uid,))
        conn.execute('DELETE FROM users WHERE id=?', (uid,))
    missing = client.post('/auth/identity/key/login', headers=HEADERS, json={'key': key})
    assert missing.json()['detail']['code'] == 'unknown_key' and '已失效' in missing.json()['detail']['message']
    assert missing.json()['detail']['browser_identity_available'] is False


def test_explicit_new_identity_replaces_only_current_browser_and_never_reuses_revoked_key(client, monkeypatch):
    from backend.app import identity_keys
    admin = auth_headers(make_user('new_after_deletion_admin', role='admin'))
    deleted = browser(client); key = key_for(client, deleted)
    assert delete_key_user(client, admin, deleted.json()['user']['id']).status_code == 204
    current = browser(client); current_key = key_for(client, current)
    second = client.post('/auth/identity/key/login', headers=HEADERS, json={'key': current_key})
    cookie = BROWSER_COOKIE+'='+current.cookies[BROWSER_COOKIE]
    invalid = client.post('/auth/identity/session', headers={**HEADERS, 'Cookie': cookie}, json={'replace': True})
    assert invalid.status_code == 400
    assert browser(client, cookie).json()['user']['id'] == current.json()['user']['id']
    # Simulate the astronomically unlikely random collision with a revoked Key.
    random = identity_keys.secrets.token_urlsafe
    generated = iter([key[3:], random(32)])
    monkeypatch.setattr(identity_keys.secrets, 'token_urlsafe', lambda _: next(generated, random(32)))
    created = client.post('/auth/identity/session', headers={**HEADERS, 'Cookie': cookie}, json={'create': True, 'replace': True})
    assert created.status_code == 200 and created.json()['created']
    assert created.json()['user']['id'] not in {current.json()['user']['id'], deleted.json()['user']['id']}
    assert key_for(client, created) != key
    assert client.get('/auth/me', headers=bearer(current)).status_code == 401
    assert client.get('/auth/me', headers=bearer(second)).status_code == 200
    assert client.get('/auth/me', headers=admin).status_code == 200
    assert client.post('/auth/identity/key/login', headers=HEADERS, json={'key': key}).json()['detail']['code'] == 'identity_deleted'
    assert client.post('/auth/identity/key/login', headers=HEADERS, json={'key': current_key}).status_code == 200
