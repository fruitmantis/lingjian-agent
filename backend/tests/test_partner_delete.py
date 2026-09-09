"""Partner deletion tests use only conftest's disposable /tmp database."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import HTTPException

from backend.app.database import get_db
from backend.app.routers import match, partners
from backend.app import development_lifecycle as life
from .conftest import auth_headers, make_partner, make_task, make_user, recommendation
from .test_development_lifecycle import prepared, start, complete


@pytest.fixture
def admin(client):
    return make_user('delete-admin', role='admin')


def snapshot():
    with get_db() as conn:
        return '\n'.join(conn.iterdump())


def add_case():
    with get_db() as conn:
        conn.execute("INSERT INTO cases VALUES ('case-1','partner-1','Synthetic case','Summary','2026-09-08')")


@pytest.mark.parametrize('state', ['active', 'disabled'])
def test_unused_partner_and_derived_profile_deleted_but_global_tags_preserved(client, admin, state):
    make_partner()
    with get_db() as conn:
        conn.execute("UPDATE partners SET ai_profile='Synthetic profile',status=? WHERE id='partner-1'", (state,))
        tags = [tuple(row) for row in conn.execute('SELECT * FROM capability_tags')]
        fks = [tuple(row) for row in conn.execute('PRAGMA foreign_key_check')]
    response = client.delete('/partners/partner-1', headers=auth_headers(admin))
    assert response.status_code == 204 and response.content == b''
    with get_db() as conn:
        assert conn.execute("SELECT * FROM partners WHERE id='partner-1'").fetchone() is None
        assert [tuple(row) for row in conn.execute('SELECT * FROM capability_tags')] == tags
        assert [tuple(row) for row in conn.execute('PRAGMA foreign_key_check')] == fks
        assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        audit = conn.execute("SELECT * FROM user_audit_logs WHERE action='partner_deleted'").fetchone()
        assert audit['actor_user_id'] == admin['id']
        assert json.loads(audit['summary']) == {'partner_id': 'partner-1'}
    assert client.delete('/partners/partner-1', headers=auth_headers(admin)).status_code == 404


def test_delete_is_admin_only(client, admin):
    make_partner()
    before = snapshot()
    assert client.delete('/partners/partner-1').status_code == 401
    user = make_user('delete-user')
    before = snapshot()
    assert client.delete('/partners/partner-1', headers=auth_headers(user)).status_code == 403
    assert client.delete('/partners/missing', headers=auth_headers(user)).status_code == 403
    assert snapshot() == before


@pytest.mark.parametrize('kind', ['cases', 'deliverables', 'documents'])
def test_business_attachments_block_with_counts_without_changing_any_data(client, admin, kind):
    make_partner()
    if kind != 'documents':
        add_case()
    with get_db() as conn:
        if kind == 'deliverables':
            conn.execute("INSERT INTO deliverables VALUES ('file-1','case-1','Synthetic.txt','/tmp/never-opened','2026-09-08')")
        if kind == 'documents':
            conn.execute("INSERT INTO partner_documents (id,partner_id,filename,file_path,file_type,created_at) VALUES ('doc-1','partner-1','Synthetic.txt','/tmp/never-opened','txt','2026-09-08')")
    before = snapshot()
    response = client.delete('/partners/partner-1', headers=auth_headers(admin))
    assert response.status_code == 409
    assert response.json()['detail']['counts'][kind] == 1
    assert '请停用伙伴' in response.json()['detail']['message']
    assert snapshot() == before
    for state in ['disabled', 'active']:
        assert client.put('/partners/partner-1', headers=auth_headers(admin), json={'status': state}).json()['status'] == state


@pytest.mark.parametrize('state,archived', [('ready',False),('failed',False),('partial',True),('ready',True)])
def test_matching_history_all_owners_states_and_archives_blocks(client, admin, state, archived):
    make_partner()
    owner = make_user('history-owner')
    make_task(owner, 'Synthetic matching', task_status=state, archived=archived,
              recommendations=[recommendation(), recommendation()])
    before = snapshot()
    response = client.delete('/partners/partner-1', headers=auth_headers(admin))
    assert response.status_code == 409
    assert response.json()['detail']['counts']['matching_tasks'] == 1
    assert snapshot() == before


def test_matching_ids_are_exact_not_names_or_substrings(client, admin):
    make_partner(); make_partner('partner-10', name='验证伙伴')
    make_task(admin, 'Synthetic other partner', recommendations=[recommendation('partner-10')])
    assert client.delete('/partners/partner-1', headers=auth_headers(admin)).status_code == 204


@pytest.mark.parametrize('invalid', ['not json', '{}', '[null]', '[{"partnerName":"Unresolved"}]'])
def test_unverifiable_history_fails_closed(client, admin, invalid):
    make_partner(); task = make_task(admin, 'Synthetic damaged history', recommendations=[])
    with get_db() as conn:
        conn.execute('UPDATE match_records SET recommendations_json=? WHERE id=?', (invalid,task))
    response = client.delete('/partners/partner-1', headers=auth_headers(admin))
    assert response.status_code == 409
    assert response.json()['detail']['counts']['unverifiable_matching_tasks'] == 1
    assert '无法核验关联的匹配历史 1 条' in response.json()['detail']['message']


@pytest.mark.parametrize('state', ['running', 'failed', 'confirmed', 'archived'])
def test_development_history_blocks_and_preserves_versions(client, prepared, state):
    accepted, run = start(prepared)
    if state == 'failed':
        life.finish_failure(run['id'], run['execution_token'], 'model')
    elif state in {'confirmed','archived'}:
        version = complete(prepared, accepted, run)
        life.confirm(accepted['plan_id'], version, prepared[0])
        if state == 'archived': life.archive(accepted['plan_id'], prepared[0])
    before = snapshot()
    response = client.delete('/partners/partner-1', headers=auth_headers(prepared[2]))
    assert response.status_code == 409
    assert response.json()['detail']['counts']['development_plans'] == 1
    assert response.json()['detail']['counts']['development_requests'] == 0
    assert snapshot() == before


def test_unattached_development_request_also_blocks(client, admin):
    make_partner()
    with get_db() as conn:
        conn.execute('INSERT INTO development_requests VALUES (?,?,?,?,?,?)',
                     ('request-1',admin['id'],'partner-1','{}','2026-09-08',admin['id']))
    response = client.delete('/partners/partner-1', headers=auth_headers(admin))
    assert response.status_code == 409
    assert response.json()['detail']['counts']['development_requests'] == 1


def test_multiple_categories_return_all_counts(client, admin):
    make_partner(); add_case(); make_task(admin,'Synthetic')
    with get_db() as conn:
        for index in range(2):
            conn.execute("INSERT INTO partner_documents (id,partner_id,filename,file_path,file_type,created_at) VALUES (?,'partner-1','Synthetic','/tmp/never-opened','txt','2026-09-08')",(str(index),))
    detail = client.delete('/partners/partner-1', headers=auth_headers(admin)).json()['detail']
    assert detail['counts']['cases'] == 1 and detail['counts']['documents'] == 2
    assert detail['counts']['matching_tasks'] == 1
    for text in ['案例 1 条','资料 2 条','项目匹配历史 1 条']: assert text in detail['message']


def test_audit_failure_rolls_back_deletion(admin):
    make_partner()
    with get_db() as conn:
        conn.execute("CREATE TRIGGER fail_delete_audit BEFORE INSERT ON user_audit_logs WHEN NEW.action='partner_deleted' BEGIN SELECT RAISE(ABORT,'Synthetic audit failure'); END")
    before = snapshot()
    with pytest.raises(Exception, match='Synthetic audit failure'):
        partners.delete_partner('partner-1', admin)
    assert snapshot() == before


def test_concurrent_matching_save_and_delete_never_leave_dangling_reference(admin):
    make_partner(); task = make_task(admin, 'Synthetic pending', recommendations=[], task_status='matching')
    gate = Barrier(2)
    def delete():
        gate.wait()
        try: partners.delete_partner('partner-1',admin); return 'deleted'
        except HTTPException as exc: assert exc.status_code == 409; return 'blocked'
    def save():
        gate.wait()
        try: match._set_task_state(task,'enriching',recommendations=[match.PartnerRecommendation(**recommendation())]); return 'saved'
        except match.DeletedMatchPartnerError: return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(delete); second = pool.submit(save)
        results = (first.result(),second.result())
    assert results in [('deleted','rejected'),('blocked','saved')]
    with get_db() as conn:
        refs = json.loads(conn.execute('SELECT recommendations_json FROM match_records WHERE id=?',(task,)).fetchone()[0])
        if refs: assert conn.execute("SELECT 1 FROM partners WHERE id='partner-1'").fetchone()
        assert conn.execute('PRAGMA foreign_key_check').fetchall() == []


@pytest.mark.parametrize('retry', [False,True])
def test_late_match_after_deletion_is_retryable_not_stuck(client, admin, monkeypatch, retry):
    make_partner(); task = make_task(admin, 'Synthetic delayed match', recommendations=[],task_status='failed' if retry else 'matching')
    partners.delete_partner('partner-1',admin)
    monkeypatch.setattr(match,'_perform_partner_match',lambda _: [match.PartnerRecommendation(**recommendation())])
    if retry:
        response = client.post(f'/agent/tasks/{task}/retry',headers=auth_headers(admin))
        assert response.status_code == 409
    else:
        with pytest.raises(HTTPException) as caught: match._execute_match(task,'Synthetic','2026-09-08')
        assert caught.value.status_code == 409
    with get_db() as conn:
        row = conn.execute('SELECT task_status,recommendations_json FROM match_records WHERE id=?',(task,)).fetchone()
        assert tuple(row) == ('failed','[]')
