"""Administrator method display is derived from credentials, never login history."""
import pytest

from backend.app.database import get_db
from .conftest import auth_headers, make_user
from .support.legacy_identity import legacy_browser as browser, legacy_passkey as register


def displayed(client, admin, user):
    headers = auth_headers(admin)
    response = client.get('/admin/users', headers=headers, params={'keyword': user['username']})
    assert response.status_code == 200
    items = response.json()['items']
    assert len(items) == 1 and items[0]['id'] == user['id']
    detail = client.get('/admin/users/' + user['id'], headers=headers)
    assert detail.status_code == 200
    assert items[0]['auth_methods'] == detail.json()['auth_methods']
    for record in (items[0], detail.json()):
        assert not {'hashed_password', 'credential_id', 'public_key', 'secret_hash',
                    'auth_password', 'auth_passkey', 'auth_browser', 'identity_key_hash',
                    'identity_key_encrypted', 'key_hash', 'encrypted_key', 'key'} & record.keys()
    assert items[0]['identity_key_hint'] is None and detail.json()['identity_key_hint'] is None
    return detail.json()['auth_methods']


@pytest.mark.parametrize('methods', [[], ['browser'], ['passkey'], ['passkey', 'browser']])
def test_admin_auth_methods_follow_actual_credentials(client, methods):
    admin = make_user('method_admin', role='admin')
    if 'passkey' in methods:
        user = register(client)[0]['user']
    elif 'browser' in methods:
        user = browser(client).json()['user']
    else:
        # A historical ordinary password hash must not imply password authentication.
        user = make_user('unmapped_ordinary')
    if methods == ['passkey', 'browser']:
        # Isolated fixture with two valid browser secrets for the same passkey user.
        # No account-binding endpoint or runtime data migration is introduced.
        for _ in range(2):
            response = browser(client)
            with get_db() as conn:
                conn.execute('UPDATE identity_credentials SET user_id=? WHERE user_id=?',
                             (user['id'], response.json()['user']['id']))
            cookie = 'banfei_browser_identity=' + response.cookies['banfei_browser_identity']
            assert client.post('/auth/identity/browser',headers={'Cookie':cookie}).status_code == 404
    assert displayed(client, admin, user) == methods
    assert displayed(client, admin, admin) == ['password']
    if methods == ['passkey', 'browser']:
        # Read fresh mappings; the latest login audit still says browser.
        with get_db() as conn:
            conn.execute("DELETE FROM identity_credentials WHERE user_id=? AND kind='browser'", (user['id'],))
        assert displayed(client, admin, user) == ['passkey']


def test_admin_auth_methods_remain_admin_only_and_role_valid(client):
    admin = make_user('method_admin', role='admin')
    from .test_local_identity import browser as new_identity
    ordinary = new_identity(client).json()
    headers = {'Authorization': 'Bearer ' + ordinary['access_token']}
    assert client.get('/admin/users', headers=headers).status_code == 403
    assert client.get('/admin/users/' + admin['id'], headers=headers).status_code == 403
    assert client.get('/admin/users/missing', headers=auth_headers(admin)).status_code == 404
    # A misplaced local mapping cannot authenticate an admin; don't label it usable.
    with get_db() as conn:
        conn.execute('UPDATE identity_credentials SET user_id=? WHERE user_id=?',
                     (admin['id'], ordinary['user']['id']))
    assert displayed(client, admin, admin) == ['password']


@pytest.mark.parametrize('status', ['active', 'disabled'])
def test_admin_key_hint_matches_actual_owner_and_only_exposes_mask(client, status):
    from .test_local_identity import browser as new_identity, bearer, key_for
    admin = make_user('key_hint_admin', role='admin'); headers = auth_headers(admin)
    first = new_identity(client); second = new_identity(client)
    identities = [first, second]
    keys = {item.json()['user']['id']: key_for(client, item) for item in identities}
    expected = {uid: key[:5]+'…'+key[-5:] for uid, key in keys.items()}
    user = first.json()['user']
    with get_db() as conn:
        conn.execute('UPDATE users SET status=? WHERE id=?', (status, user['id']))
        stored = {row['user_id']: dict(row) for row in conn.execute('SELECT * FROM user_identity_keys')}
    responses = []
    # List and detail are independently owner-bound; pagination uses the same mapping.
    for page in (1, 2):
        response = client.get('/admin/users', headers=headers, params={'role': 'user', 'pageSize': 1, 'page': page})
        assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
        record = response.json()['items'][0]
        assert record['identity_key_hint'] == expected[record['id']]
        assert response.json()['total'] == 2
        responses.append(response)
    filtered = client.get('/admin/users', headers=headers, params={'keyword': user['username'], 'status': status})
    assert filtered.json()['total'] == 1 and filtered.json()['items'][0]['identity_key_hint'] == expected[user['id']]
    responses.append(filtered)
    for uid in keys:
        detail = client.get('/admin/users/'+uid, headers=headers)
        assert detail.status_code == 200 and detail.headers['cache-control'] == 'no-store'
        assert detail.json()['identity_key_hint'] == expected[uid]
        assert not {'key', 'encrypted_key', 'key_hash', 'identity_key_hash', 'identity_key_encrypted'} & detail.json().keys()
        responses.append(detail)
    for response in responses:
        for uid, key in keys.items():
            assert key not in response.text and key[5:-5] not in response.text
            assert stored[uid]['encrypted_key'] not in response.text and stored[uid]['key_hash'] not in response.text
    assert client.get('/admin/users', headers=bearer(second)).status_code == 403
    assert client.get('/admin/users/'+user['id'], headers=bearer(second)).status_code == 403
    assert client.get('/admin/users').status_code == 401
    assert client.get('/admin/users/'+user['id']).status_code == 401
    assert 'identity_key_hint' not in client.get('/auth/me', headers=bearer(second)).json()
    assert 'identity_key_hint' not in second.json()['user']
    assert key_for(client, second) == keys[second.json()['user']['id']]
    with get_db() as conn:
        assert {row['user_id']: dict(row) for row in conn.execute('SELECT * FROM user_identity_keys')} == stored
        audits = str([dict(row) for row in conn.execute('SELECT * FROM user_audit_logs')])
        for key in keys.values(): assert key not in audits


@pytest.mark.parametrize('damage', ['ciphertext', 'owner', 'hash'])
def test_admin_key_hint_damage_does_not_hide_other_users_or_expose_secrets(client, damage):
    from .test_local_identity import browser as new_identity, key_for
    admin = make_user('hint_damage_admin', role='admin'); headers = auth_headers(admin)
    first = new_identity(client); second = new_identity(client)
    first_id = first.json()['user']['id']; second_id = second.json()['user']['id']
    first_key = key_for(client, first); second_key = key_for(client, second)
    with get_db() as conn:
        if damage == 'ciphertext':
            conn.execute('UPDATE user_identity_keys SET encrypted_key=? WHERE user_id=?', ('invalid-ciphertext', first_id))
        elif damage == 'owner':
            other = conn.execute('SELECT encrypted_key FROM user_identity_keys WHERE user_id=?', (second_id,)).fetchone()[0]
            conn.execute('UPDATE user_identity_keys SET encrypted_key=? WHERE user_id=?', (other, first_id))
        else:
            conn.execute('UPDATE user_identity_keys SET key_hash=? WHERE user_id=?', ('0'*64, first_id))
        before = [dict(row) for row in conn.execute('SELECT * FROM user_identity_keys ORDER BY user_id')]
    response = client.get('/admin/users', headers=headers)
    assert response.status_code == 200 and first_key not in response.text and second_key not in response.text
    items = {item['id']: item for item in response.json()['items']}
    assert items[first_id]['identity_key_hint'] is None and items[first_id]['auth_methods'] == ['key']
    assert items[second_id]['identity_key_hint'] == second_key[:5]+'…'+second_key[-5:]
    detail = client.get('/admin/users/'+first_id, headers=headers)
    assert detail.status_code == 200 and detail.json()['identity_key_hint'] is None
    with get_db() as conn:
        assert [dict(row) for row in conn.execute('SELECT * FROM user_identity_keys ORDER BY user_id')] == before


def test_admin_key_hint_ignores_keys_misplaced_on_password_admin(client):
    from backend.app.identity_keys import create_identity_key
    admin = make_user('hint_password_admin', role='admin')
    with get_db() as conn: create_identity_key(conn, admin['id'])
    assert displayed(client, admin, admin) == ['password']
