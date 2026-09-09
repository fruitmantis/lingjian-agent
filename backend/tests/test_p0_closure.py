"""P0 integration regression; synthetic /tmp databases and mocked model calls only."""
import hashlib
import os
import json
from datetime import datetime, timezone
import httpx
import pytest
from backend.app import database, development_lifecycle as life
from backend.app.database import get_db
from backend.app.development_types import Submit
from backend.app.routers import match, system
from backend.tests.conftest import auth_headers, make_partner, make_user, make_task
from backend.tests.test_development_lifecycle import prepared, start, complete


def test_matching_uses_existing_profile_and_evidence_without_raw_files(client, monkeypatch):
    make_partner()
    make_partner('empty-partner', '资料有限伙伴')
    make_partner('disabled-partner', '不可推荐伙伴')
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("UPDATE partners SET ai_profile=?,industries='银行',service_areas='深圳' WHERE id='partner-1'", ('核心能力：企业数据库迁移与 RAG 数据集成。' + '既有经验' * 1000,))
        conn.execute("UPDATE partners SET ai_profile=NULL,capabilities=NULL,industries=NULL,service_areas=NULL WHERE id='empty-partner'")
        conn.execute("UPDATE partners SET status='disabled',ai_profile='DISABLED_SECRET' WHERE id='disabled-partner'")
        conn.execute('INSERT INTO cases VALUES (?,?,?,?,?)', ('case-p0', 'partner-1', '数据库项目', '实施数据库迁移。' + '案例细节' * 300, now))
        conn.execute('INSERT INTO deliverables VALUES (?,?,?,?,?)', ('file-p0', 'case-p0', '迁移交付说明.pdf', '/private/NEVER_SEND_RAW_FILE', now))
    captured = []
    def fake(messages, **kwargs):
        captured.append(messages)
        assert kwargs['scene'] == 'partner_match'
        return json.dumps([dict(partnerId='partner-1',partnerName='验证伙伴',matchScore=90,matchedCapabilities='AI',matchedIndustries='金融',matchedRegions='广东',recommendationReason='已有迁移经验',evidenceCases=['case-p0'],evidenceDeliverables=['file-p0'],riskNotes='需项目验证')])
    monkeypatch.setattr(match, 'chat_completion', fake)
    result = match._perform_partner_match('数据库迁移')
    assert len(result) == 1
    context = captured[0][-1]['content']
    for text in ('核心能力：企业数据库迁移与 RAG 数据集成。', '金融', '广东', '数据库项目', '实施数据库迁移。', '迁移交付说明.pdf', '暂无画像，依据现有资料判断'):
        assert text in context
    for text in ('DISABLED_SECRET', 'NEVER_SEND_RAW_FILE', 'AI画像: 已生成', '行业经验: 银行', '覆盖区域: 深圳'):
        assert text not in context
    assert len(context) < 6500
    assert 'case-p0' in context and 'file-p0' in context


def test_dashboard_counts_plans_once_including_archives_and_month_boundaries(prepared, client):
    user, _, admin, request = prepared
    a, run = start(prepared)
    complete(prepared, a, run)
    life.archive(a['plan_id'], user)
    b = life.create(Submit(submission_id='p0-second', request=request), user)
    first = make_task(user, 'older matching', archived=True)
    make_task(user, 'current matching')
    with get_db() as conn:
        conn.execute("UPDATE match_records SET created_at='2000-01-01T00:00:00+00:00' WHERE id=?", (first,))
        conn.execute("UPDATE development_plans SET created_at='2000-01-01T00:00:00+00:00' WHERE id=?", (a['plan_id'],))
        # Extra historical run must not count as another task.
        conn.execute("""INSERT INTO development_runs (id,plan_id,owner_user_id,run_type,submission_id,request_hash,status,input_snapshot,created_at)
            VALUES ('extra-run',?,?,'revise','extra-run','hash','failed','{}','2000-01-02')""", (a['plan_id'],user['id']))
    d = client.get('/admin/dashboard', headers=auth_headers(admin)).json()
    assert (d['tasks'], d['partnerMatchTasks'], d['developmentTasks']) == (4,2,2)
    assert (d['monthTasks'], d['monthPartnerMatchTasks'], d['monthDevelopmentTasks']) == (2,1,1)
    assert client.get('/admin/dashboard', headers=auth_headers(user)).status_code == 403


def test_empty_dashboard(client):
    admin = make_user('empty-admin', role='admin')
    d = client.get('/admin/dashboard', headers=auth_headers(admin)).json()
    assert all(d[k] == 0 for k in ('tasks','monthTasks','partnerMatchTasks','developmentTasks','monthPartnerMatchTasks','monthDevelopmentTasks'))


@pytest.fixture
def safe_status(client, monkeypatch):
    def no_call(*args, **kwargs):
        pytest.fail('system status must not call any model')
    monkeypatch.setattr(httpx.Client, 'post', no_call)
    monkeypatch.setattr(httpx.AsyncClient, 'post', no_call)
    with get_db() as conn:
        conn.execute("UPDATE model_configs SET base_url='http://127.0.0.1:18180/v1',api_key='synthetic-only',api_key_source='db',enabled=1,is_default=1")
        conn.execute('UPDATE model_usage_configs SET model_config_id=NULL')
    return make_user('p0-status-admin', role='admin')


def status_data(client, admin):
    def current_fingerprint():
        if os.environ['DATABASE_URL'].startswith('postgresql'):
            from backend.tests.support.database_fingerprint import fingerprint
            return fingerprint(os.environ['DATABASE_URL'])
        return hashlib.sha256(database.DATABASE_PATH.read_bytes()).hexdigest()
    before = current_fingerprint()
    response = client.get('/admin/system/status', headers=auth_headers(admin))
    assert response.status_code == 200
    assert current_fingerprint() == before
    assert 'synthetic-only' not in response.text
    return next(i for i in response.json()['businessCapabilities'] if i['name'] == '能力发展')


def test_development_status_no_runs_and_invalid_explicit_binding(client, safe_status):
    d = status_data(client, safe_status)
    assert d['detail'] == '暂无运行记录'
    assert '配置可用' in d['message']
    with get_db() as conn:
        conn.execute("UPDATE model_usage_configs SET model_config_id='missing' WHERE scene_key='partner_development'")
    assert status_data(client, safe_status)['status'] == 'error'


@pytest.mark.parametrize('state,label', [('pending','等待执行'),('running','执行中'),('ready','已完成'),('partial','部分完成'),('failed','失败'),('interrupted','已中断')])
def test_development_latest_run_state_duration_and_sanitization(prepared, client, safe_status, state, label):
    a, _ = start(prepared)
    with get_db() as conn:
        conn.execute("UPDATE development_runs SET status='failed',created_at='2000-01-01' WHERE id=?", (a['run_id'],))
        conn.execute("""INSERT INTO development_runs (id,plan_id,owner_user_id,run_type,submission_id,request_hash,status,input_snapshot,created_at,started_at,ended_at,safe_error_message)
            VALUES ('latest-p0',?,?,'revise','latest-p0','hash',?,'{}','2026-09-08','2026-09-08T01:00:00+00:00',?,'INTERNAL_SECRET_PHASE_B_DO_NOT_SHARE')""", (a['plan_id'],prepared[0]['id'],state,None if state in ('pending','running') else '2026-09-08T01:00:12.500+00:00'))
    d = status_data(client, safe_status)
    assert f'最近运行：调整 · {label}' in d['detail']
    assert ('耗时 12.5 秒' in d['detail']) == (state not in ('pending','running'))
    assert 'INTERNAL_SECRET' not in str(d)


@pytest.mark.parametrize('started,ended', [('bad','bad'),('2026-09-08T02:00:00','2026-09-08T01:00:00'),('2026-09-08T01:00:00','2026-09-08T01:01:00+00:00')])
def test_invalid_run_timestamps_never_invent_duration(prepared, client, safe_status, started, ended):
    a, _ = start(prepared)
    with get_db() as conn:
        conn.execute("UPDATE development_runs SET status='failed',started_at=?,ended_at=? WHERE id=?", (started,ended,a['run_id']))
    assert '耗时' not in status_data(client, safe_status)['detail']


def test_status_accepts_configured_external_model_without_probing(client, safe_status):
    with get_db() as conn:
        conn.execute("UPDATE model_configs SET base_url='https://model.invalid/v1'")
    d = status_data(client,safe_status)
    assert d['status'] != 'error' and '模型配置可用' in d['message']
