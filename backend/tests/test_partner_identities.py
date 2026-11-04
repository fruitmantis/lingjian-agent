"""Manually maintained identities; isolated PostgreSQL only, no model requests."""
from io import BytesIO
import json
import os

import pytest
from openpyxl import load_workbook
from sqlalchemy import inspect

from backend.app import development_engine, development_model, partner_transfer
from backend.app.database import get_db
from backend.app.partner_identities import IDENTITIES
from backend.app.partner_identity_schema import migrate
from backend.app.postgres_storage import verify_schema
from .conftest import auth_headers, make_partner, make_task, make_user
from .postgres_support import snapshot
from .test_partner_transfer import save, set_cell, upload


def test_identity_create_edit_clear_permissions_and_unchanged_profile(client, monkeypatch):
    admin = auth_headers(make_user('identity_admin', role='admin'))
    reader = auth_headers(make_user('identity_reader'))
    monkeypatch.setattr(development_model, 'completion', lambda *args: pytest.fail('Identity maintenance must not call a model'))
    result = client.post('/partners', headers=admin, json={'name': '身份伙伴', 'identities': IDENTITIES + IDENTITIES[:1]})
    assert result.status_code == 201
    partner = result.json()
    assert partner['identities'] == IDENTITIES
    pid = partner['id']
    with get_db() as conn:
        conn.execute("UPDATE partners SET ai_profile='保留画像正文',intro='原简介',profile_chapter_meta='{}',materials_revision=3,profile_materials_revision=2 WHERE id=?", (pid,))
        before = dict(conn.execute('SELECT * FROM partners WHERE id=?', (pid,)).fetchone())
        model_before = development_engine.profile_context(conn, {'target_partner_id': pid, 'model_input_allowed': True})
    selected = [IDENTITIES[0], IDENTITIES[1]]
    response = client.put(f'/partners/{pid}', headers=admin, json={'identities': selected})
    assert response.status_code == 200 and response.json()['identities'] == selected
    assert client.get(f'/partners/{pid}', headers=reader).json()['identities'] == selected
    assert next(p for p in client.get('/partners/profiles', headers=reader).json() if p['id'] == pid)['identities'] == selected
    assert next(p for p in client.get('/partners', headers=reader).json() if p['id'] == pid)['identities'] == selected
    with get_db() as conn:
        after = dict(conn.execute('SELECT * FROM partners WHERE id=?', (pid,)).fetchone())
        assert {k: v for k, v in after.items() if k not in ('identities', 'updated_at')} == {k: v for k, v in before.items() if k not in ('identities', 'updated_at')}
        assert development_engine.profile_context(conn, {'target_partner_id': pid, 'model_input_allowed': True}) == model_before
    assert client.put(f'/partners/{pid}', headers=admin, json={'name': '身份伙伴改名'}).json()['identities'] == selected
    for headers, code in [({}, 401), (reader, 403)]:
        assert client.post('/partners', headers=headers, json={'name': '越权', 'identities': selected}).status_code == code
        assert client.put(f'/partners/{pid}', headers=headers, json={'identities': []}).status_code == code
    assert client.put(f'/partners/{pid}', headers=admin, json={'identities': []}).json()['identities'] == []


@pytest.mark.parametrize('value', [['其他身份'], '软件合作伙伴', [123], [None]])
def test_identity_rejects_invalid_selection_without_changes(client, value):
    headers = auth_headers(make_user('invalid_identity_admin', role='admin'))
    make_partner()
    with get_db() as conn: before = snapshot(conn)
    assert client.post('/partners', headers=headers, json={'name': '非法身份', 'identities': value}).status_code == 422
    assert client.put('/partners/partner-1', headers=headers, json={'identities': value}).status_code == 422
    with get_db() as conn: assert snapshot(conn) == before


def test_identity_legacy_null_is_empty_without_inference(client):
    user = make_user('legacy_identity_reader')
    make_partner()
    with get_db() as conn:
        conn.execute('UPDATE partners SET intro=?,capabilities=?', (IDENTITIES[0], IDENTITIES[1]))
    headers = auth_headers(user)
    assert client.get('/partners/partner-1', headers=headers).json()['identities'] == []
    assert client.get('/partners/profiles', headers=headers).json()[0]['identities'] == []
    with get_db() as conn: assert conn.execute('SELECT identities FROM partners').fetchone()[0] is None


def test_identity_excel_roundtrip_clear_and_legacy_column_omission(client):
    headers = auth_headers(make_user('identity_excel_admin', role='admin'))
    make_partner()
    selected = [IDENTITIES[0], IDENTITIES[3], IDENTITIES[5]]
    assert client.put('/partners/partner-1', headers=headers, json={'identities': selected}).status_code == 200
    book = load_workbook(BytesIO(client.get('/partners/export', headers=headers).content))
    index = list(partner_transfer.COLUMNS).index('identities') + 1
    assert book['伙伴信息'].cell(2, index).value == ','.join(selected)
    assert upload(client, headers, book).json() == {'created': 0, 'updated': 0, 'unchanged': 1}
    # An exact old template has no identity column; it must not erase maintained data.
    book['伙伴信息'].delete_cols(index)
    set_cell(book, 'intro', '旧模板更新简介')
    assert upload(client, headers, book).json()['updated'] == 1
    assert client.get('/partners/partner-1', headers=headers).json()['identities'] == selected
    set_cell(book, 'id', 'legacy-new')
    set_cell(book, 'name', '旧模板新增伙伴')
    assert upload(client, headers, book).json()['created'] == 1
    assert client.get('/partners/legacy-new', headers=headers).json()['identities'] == []
    current = load_workbook(BytesIO(client.get('/partners/export', headers=headers).content))
    set_cell(current, 'identities', None)
    assert upload(client, headers, current).status_code == 200
    assert client.get('/partners/partner-1', headers=headers).json()['identities'] == []


def test_identity_excel_valid_multi_select_and_invalid_row_rolls_back(client):
    headers = auth_headers(make_user('identity_excel_validation_admin', role='admin'))
    book = load_workbook(BytesIO(client.get('/partners/template', headers=headers).content))
    set_cell(book, 'name', '身份表格伙伴')
    set_cell(book, 'identities', '，'.join(IDENTITIES))
    set_cell(book, 'name', '错误行', row=3)
    set_cell(book, 'identities', '未知身份', row=3)
    response = upload(client, headers, book)
    assert response.status_code == 422 and '第3行' in response.json()['detail']
    with get_db() as conn: assert conn.execute('SELECT count(*) FROM partners').fetchone()[0] == 0
    book['伙伴信息'].delete_rows(3)
    assert upload(client, headers, book).json()['created'] == 1
    assert client.get('/partners', headers=headers).json()[0]['identities'] == IDENTITIES


def schema24(conn):
    conn.execute('ALTER TABLE partners DROP COLUMN identities')
    conn.execute("UPDATE app_metadata SET value='24' WHERE key='schema_version'")


def test_identity_schema24_to25_is_additive_atomic_and_idempotent(client):
    owner = make_user('identity_migration_owner')
    make_partner()
    task = make_task(owner, '原附件任务')
    with get_db() as conn:
        conn.execute('UPDATE match_records SET attachment_name=?,attachment_text=? WHERE id=?', ('需求.txt', '必须保留的附件正文', task))
        schema24(conn)
        before = snapshot(conn)
    with pytest.raises(RuntimeError, match='synthetic abort'):
        with get_db() as conn:
            migrate(conn)
            raise RuntimeError('synthetic abort')
    with get_db() as conn:
        assert snapshot(conn) == before
        assert migrate(conn) == {'schema_version': 25, 'added_column': 'partners.identities'}
        after = snapshot(conn, {'partners': ['identities']})
        assert {k: v for k, v in after.items() if k != 'app_metadata'} == {k: v for k, v in before.items() if k != 'app_metadata'}
        assert conn.execute('SELECT identities FROM partners').fetchone()[0] is None
        conn.execute('UPDATE partners SET identities=?', (json.dumps(IDENTITIES),))
        saved = snapshot(conn)
        assert migrate(conn) == {'schema_version': 25, 'already_current': True}
        assert snapshot(conn) == saved
    verify_schema(os.environ['DATABASE_URL'])


@pytest.mark.parametrize('version', ['23', '26'])
def test_identity_migration_refuses_wrong_version_without_writes(client, version):
    with get_db() as conn:
        schema24(conn)
        conn.execute("UPDATE app_metadata SET value=? WHERE key='schema_version'", (version,))
        before = snapshot(conn)
    with pytest.raises(RuntimeError, match='requires schema 24'):
        with get_db() as conn: migrate(conn)
    with get_db() as conn: assert snapshot(conn) == before


@pytest.mark.parametrize('old_stamp', [True, False])
def test_identity_startup_never_migrates_old_or_incomplete_schema(client, old_stamp):
    with get_db() as conn:
        schema24(conn)
        if not old_stamp: conn.execute("UPDATE app_metadata SET value='25' WHERE key='schema_version'")
        before = snapshot(conn)
    expected = 'version is not 25' if old_stamp else 'explicit schema-25 migration'
    with pytest.raises(RuntimeError, match=expected): verify_schema(os.environ['DATABASE_URL'])
    with get_db() as conn: assert snapshot(conn) == before
