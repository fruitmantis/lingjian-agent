"""Admin read-only employee projection, using disposable PG schemas only."""
from .test_local_identity import browser, bearer, HEADERS
import pytest

@pytest.mark.parametrize('number', ['000-A', None])
def test_admin_list_and_detail_show_saved_employee_without_new_edit_permission(client, identity_set, number):
    identity = browser(client)
    if number is not None:
        assert client.patch('/auth/me', headers=bearer(identity), json={'employee_number': number}).status_code == 200
    uid = identity.json()['user']['id']
    login = client.post('/auth/admin/login', headers=HEADERS, json={'username':'admin1','password':'ValidationPass123'})
    assert login.status_code == 200
    headers = bearer(login)
    listing = client.get('/admin/users', headers=headers)
    assert listing.status_code == 200 and listing.headers['cache-control'] == 'no-store'
    item = next(row for row in listing.json()['items'] if row['id'] == uid)
    detail = client.get('/admin/users/'+uid, headers=headers)
    assert detail.status_code == 200 and detail.headers['cache-control'] == 'no-store'
    assert item['employee_number'] == detail.json()['employee_number'] == number
    assert not {'key', 'key_hash', 'encrypted_key'} & item.keys()
    assert client.get('/admin/users', headers=bearer(identity)).status_code == 403
    assert client.get('/admin/users/'+uid, headers=bearer(identity)).status_code == 403
