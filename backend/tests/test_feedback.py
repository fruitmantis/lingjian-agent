from contextlib import contextmanager
from io import BytesIO

import pytest
from PIL import Image

from backend.app.database import get_db
from backend.app.routers import feedback
from .conftest import auth_headers, make_user


def image_file(fmt='PNG'):
    stream = BytesIO()
    Image.new('RGB', (12, 8), 'white').save(stream, format=fmt)
    ext, mime = feedback.FORMATS[fmt]
    return ('images', ('screenshot' + ext, stream.getvalue(), mime))


def count_issues():
    with get_db() as conn:
        return conn.execute('SELECT count(*) FROM feedback_issue').fetchone()[0]


def test_submit_identity_admin_review_and_private_screenshots(client):
    user = make_user('feedback-user'); admin = make_user('feedback-admin', role='admin')
    h = auth_headers(user); ah = auth_headers(admin)
    result = client.post('/feedback', headers=h, data={'description': '  第一行问题\n第二行  '}, files=[image_file(), image_file('JPEG')])
    assert result.status_code == 201 and result.json() == {'message': '问题已提交'}
    listing = client.get('/admin/feedback', headers=ah)
    assert listing.headers['cache-control'] == 'no-store'
    item = listing.json()['items'][0]
    assert item['submitter'] == user['username'] and item['screenshot_count'] == 2 and item['status'] == 'pending'
    issue_id = item['id']
    detail = client.get('/admin/feedback/' + issue_id, headers=ah).json()
    assert detail['description'] == '第一行问题\n第二行'
    assert 'storage_name' not in str(detail) and 'submitter_id' not in detail
    with get_db() as conn:
        assert conn.execute('SELECT submitter_id FROM feedback_issue WHERE id=?', (issue_id,)).fetchone()[0] == user['id']
    for attachment in detail['attachments']:
        path = f"/admin/feedback/{issue_id}/attachments/{attachment['id']}"
        response = client.get(path, headers=ah)
        assert response.status_code == 200 and response.headers['content-type'].startswith('image/')
        assert response.headers['cache-control'] == 'no-store'
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert client.get(path, headers=h).status_code == 403
        assert client.get(path).status_code == 401
        assert client.get(path.replace(issue_id, 'wrong-issue'), headers=ah).status_code == 404
    for state in ('resolved', 'pending'):
        assert client.patch('/admin/feedback/' + issue_id, headers=ah, json={'status': state}).status_code == 204
        assert client.get('/admin/feedback/' + issue_id, headers=ah).json()['status'] == state
    assert client.patch('/admin/feedback/' + issue_id, headers=ah, json={'status': 'closed'}).status_code == 422
    assert client.get('/admin/feedback?offset=1', headers=ah).json() == {'items': [], 'total': 1}


def test_user_can_only_submit_and_auth_is_required(client):
    user = make_user('feedback-user'); h = auth_headers(user)
    assert client.post('/feedback', data={'description': '问题'}).status_code == 401
    assert client.post('/feedback', headers=h, data={'description': '无截图的问题'}).status_code == 201
    for path in ('/admin/feedback', '/admin/feedback/unknown', '/admin/feedback/unknown/attachments/unknown'):
        assert client.get(path, headers=h).status_code == 403
    assert client.patch('/admin/feedback/unknown', headers=h, json={'status': 'resolved'}).status_code == 403
    assert client.get('/feedback', headers=h).status_code == 405
    assert client.get('/feedback/unknown', headers=h).status_code == 404
    disabled = make_user('feedback-disabled', status='disabled')
    assert client.post('/feedback', headers=auth_headers(disabled), data={'description': '问题'}).status_code in (401, 403)


@pytest.mark.parametrize('description', ['', '   ', 'a' * 5001], ids=['empty', 'whitespace', 'too-long'])
def test_description_required_and_bounded(client, description):
    h = auth_headers(make_user('feedback-user'))
    assert client.post('/feedback', headers=h, data={'description': description}).status_code == 422
    assert count_issues() == 0


@pytest.mark.parametrize('fmt', ['PNG', 'JPEG', 'WEBP', 'GIF'])
def test_common_image_formats(client, fmt):
    h = auth_headers(make_user('feedback-user'))
    assert client.post('/feedback', headers=h, data={'description': '格式验证'}, files=[image_file(fmt)]).status_code == 201


@pytest.mark.parametrize('filename,content,mime', [
    ('bad.svg', b'<svg></svg>', 'image/svg+xml'),
    ('fake.png', b'not an image', 'image/png'),
    ('empty.png', b'', 'image/png'),
    ('wrong.jpg', image_file()[1][1], 'image/jpeg'),
    ('wrong.png', image_file()[1][1], 'text/html'),
])
def test_invalid_images_roll_back_all_new_files(client, filename, content, mime):
    h = auth_headers(make_user('feedback-user'))
    response = client.post('/feedback', headers=h, data={'description': '坏图'}, files=[image_file(), ('images', (filename, content, mime))])
    assert response.status_code == 422
    assert count_issues() == 0
    assert not list((feedback.UPLOADS_DIR / 'feedback').glob('*'))


def test_count_size_limits_and_identity_spoofing(client, monkeypatch):
    h = auth_headers(make_user('feedback-user'))
    assert client.post('/feedback', headers=h, data={'description': '太多'}, files=[image_file()] * 6).status_code == 400
    monkeypatch.setattr(feedback, 'MAX_IMAGE_BYTES', 30)
    assert client.post('/feedback', headers=h, data={'description': '太大'}, files=[image_file()]).status_code == 413
    assert client.post('/feedback', headers=h, data={'description': '冒名', 'submitter_id': 'admin'}).status_code in (400, 422)
    assert count_issues() == 0
    assert not list((feedback.UPLOADS_DIR / 'feedback').glob('*'))


def test_database_failure_rolls_back_records_and_only_new_files(client, monkeypatch):
    h = auth_headers(make_user('feedback-user'))
    root = feedback.UPLOADS_DIR / 'feedback'; root.mkdir(parents=True)
    sentinel = root / 'existing.png'; sentinel.write_bytes(b'existing file must survive')
    @contextmanager
    def broken_db():
        with get_db() as conn:
            class Proxy:
                def execute(self, sql, args=()):
                    if sql.startswith('INSERT INTO feedback_attachment'):
                        raise RuntimeError('synthetic storage fault')
                    return conn.execute(sql, args)
            yield Proxy()
    monkeypatch.setattr(feedback, 'get_db', broken_db)
    result = client.post('/feedback', headers=h, data={'description': '故障回放'}, files=[image_file()])
    assert result.status_code == 500 and 'synthetic' not in result.text
    assert count_issues() == 0
    assert list(root.iterdir()) == [sentinel]
