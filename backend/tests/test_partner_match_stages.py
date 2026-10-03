"""Synthetic three-stage matching regressions; no business model requests."""

import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from backend.app import development_model, match_understanding, partner_match_context as context
from backend.app.database import get_db
from backend.app.model_resolver import resolve_model_record
from backend.app.routers import match
from backend.app.routers import profile as profile_router
from .conftest import auth_headers, make_partner
from .test_development_lifecycle import prepared


def now():
    return datetime.now(timezone.utc).isoformat()


def add_profile(partner_id, profile, *, capabilities=''):
    with get_db() as conn:
        conn.execute('UPDATE partners SET ai_profile=?,capabilities=?,profile_updated_at=?,updated_at=?,profile_materials_revision=materials_revision WHERE id=?',
                     (profile, capabilities, now(), now(), partner_id))


def seed_summary(partner_id, text):
    with get_db() as conn:
        stamp = context.sources(conn, partner_id)[3]
        conn.execute('INSERT INTO app_metadata(key,value) VALUES (?,?)',
                     (context.SUMMARY_PREFIX + partner_id,
                      json.dumps({'text': text, 'source_fingerprint': stamp}, ensure_ascii=False)))


def answer(partner_id=None, name='后段能力伙伴', case_ids=None):
    recs = [] if not partner_id else [{
        'partnerId': partner_id, 'partnerName': name, 'matchScore': '86',
        'matchedCapabilities': '', 'matchedIndustries': '', 'matchedRegions': '',
        'recommendationReason': '后段画像提供了待核实的能力线索',
        'evidenceCases': case_ids or [], 'evidenceDeliverables': [],
        'riskNotes': '不支持跨境，交付边界需核实',
    }]
    return json.dumps({'answer': '建议优先核实后段能力伙伴。', 'recommendations': recs,
                       'supplyStatus': 'partial', 'gapAnalysis': '仍需核实实际交付边界'}, ensure_ascii=False)


def test_three_calls_include_unlabelled_partner_and_late_profile_passage(prepared, monkeypatch, caplog):
    import logging
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    user = prepared[0]
    make_partner('partner-2', '后段能力伙伴')
    add_profile('partner-1', '非入选伙伴的完整私有画像标记。' * 900)
    add_profile('partner-2', ('常规项目交付经验。\n' * 1300) +
                '具备稀有冷链回退能力，已完成相关现场验证；但不支持跨境交付。')
    seed_summary('partner-2', '冷链回退现场验证经验；不支持跨境交付，需核实本地交付边界。')
    seen = []

    def complete(config, messages, schema):
        stage = schema['title']
        seen.append((stage, messages[-1]['content']))
        if stage == 'MatchUnderstanding':
            return '{"in_scope":true,"facts":{"technicalNeeds":"稀有冷链回退","region":"未知"}}'
        if stage == 'InitialSelection':
            payload = json.loads(messages[-1]['content'])
            assert {item['partnerId'] for item in payload['partners']} == {'partner-1', 'partner-2'}
            assert '非入选伙伴的完整私有画像标记' not in messages[-1]['content']
            assert any(item['partnerId'] == 'partner-2' and item['capabilities'] == '' for item in payload['partners'])
            return '{"candidates":[{"partnerId":"partner-2","verificationFocus":"稀有冷链回退与跨境限制"}]}'
        detail = json.loads(messages[-1]['content'])['candidates']
        assert len(detail) == 1 and detail[0]['partnerId'] == 'partner-2'
        assert '具备稀有冷链回退能力' in messages[-1]['content']
        assert '不支持跨境交付' in messages[-1]['content']
        assert '非入选伙伴的完整私有画像标记' not in messages[-1]['content']
        return answer('partner-2')

    monkeypatch.setattr(development_model, 'completion', complete)
    result = match.match_partners(match.MatchRequest(requirement='寻找稀有冷链回退伙伴'), user)
    assert [stage for stage, _ in seen] == ['MatchUnderstanding', 'InitialSelection', 'MatchAnswer']
    assert result.recommendations[0].partnerId == 'partner-2'
    assert len(seen[1][1]) < 2000  # No bulk profile transfer to initial selection.
    assert len(seen[2][1]) < 2500
    stages = [record.message for record in caplog.records if record.message.startswith('MATCH_STAGE ')]
    assert {json.loads(line.split(' ', 1)[1])['stage'] for line in stages} == {
        'understanding', 'initial_selection', 'detailed_review'}
    assert all('稀有冷链' not in line and '私有画像' not in line for line in stages)


@pytest.mark.parametrize('change', [None, 'candidate', 'model'])
def test_initial_selection_snapshot_reused_only_when_inputs_unchanged(prepared, monkeypatch, change):
    user = prepared[0]
    seen = []

    def complete(config, messages, schema):
        stage = schema['title']
        seen.append(stage)
        if stage == 'MatchUnderstanding':
            return '{"in_scope":true,"facts":{"technicalNeeds":"数据库迁移"}}'
        if stage == 'InitialSelection':
            return '{"candidates":[{"partnerId":"partner-1","verificationFocus":"数据库迁移经验"}]}'
        if seen.count('MatchAnswer') == 1:
            raise TimeoutError('synthetic detailed timeout')
        return answer()

    monkeypatch.setattr(development_model, 'completion', complete)
    with pytest.raises(HTTPException):
        match.match_partners(match.MatchRequest(requirement='需要数据库迁移伙伴'), user)
    with get_db() as conn:
        task = conn.execute('SELECT id,task_status FROM match_records').fetchone()
        snapshot = match_understanding.load(conn, task['id'])
    assert task['task_status'] == 'failed'
    assert snapshot['initial_selection']['candidates'][0]['partnerId'] == 'partner-1'
    if change == 'candidate':
        with get_db() as conn:
            conn.execute('UPDATE partners SET intro=?,updated_at=? WHERE id=?', ('新资料', now(), 'partner-1'))
    if change == 'model':
        with get_db() as conn:
            conn.execute('UPDATE model_configs SET temperature=0.61 WHERE enabled=1')
    result = match.retry_match_record(task['id'], user)
    assert result.taskStatus == 'ready'
    assert seen.count('InitialSelection') == (1 if change is None else 2)
    assert seen.count('MatchUnderstanding') == (2 if change == 'model' else 1)
    with get_db() as conn:
        assert conn.execute('SELECT COUNT(*) FROM match_records').fetchone()[0] == 1


def test_summary_fingerprint_and_concurrent_change(prepared, monkeypatch):
    add_profile('partner-1', '真实能力是数据库迁移，限制是缺少跨境交付记录。')
    seed_summary('partner-1', '有数据库迁移经验，跨境交付需核实。')
    with get_db() as conn:
        stamp = context.sources(conn, 'partner-1')[3]
        assert context.current_summary(conn, 'partner-1', stamp)
        conn.execute('UPDATE partners SET intro=?,updated_at=? WHERE id=?', ('新增资料', now(), 'partner-1'))
        changed = context.sources(conn, 'partner-1')[3]
        assert not context.current_summary(conn, 'partner-1', changed)
        assert context.compact_candidates(conn)[0]['evidenceState'] == '资料有限，待核实'

    def concurrent_change(config, messages, schema):
        assert schema['title'] == 'MatchingSummary'
        with get_db() as conn:
            conn.execute('UPDATE partners SET intro=?,updated_at=? WHERE id=?', ('并发新资料', now(), 'partner-1'))
        return '{"text":"旧资料不能写入"}'

    monkeypatch.setattr(development_model, 'completion', concurrent_change)
    assert context.generate_summary('partner-1') is False
    with get_db() as conn:
        value = json.loads(conn.execute('SELECT value FROM app_metadata WHERE key=?',
                                        (context.SUMMARY_PREFIX + 'partner-1',)).fetchone()[0])
        assert value['text'] == '有数据库迁移经验，跨境交付需核实。'


def test_successful_summary_and_independent_profile_failure(prepared, monkeypatch):
    from backend.app.profile_report import empty_report
    add_profile('partner-1', empty_report().text+'具备数据库迁移经验；跨境交付暂无证据。')
    monkeypatch.setattr(development_model, 'completion', lambda *_: '{"text":"数据库迁移经验有明确资料；跨境交付暂无证据，需单独核实。"}')
    assert context.generate_summary('partner-1')
    with get_db() as conn:
        stamp = context.sources(conn, 'partner-1')[3]
        assert '跨境交付' in context.current_summary(conn, 'partner-1', stamp)

    from .support.profile_report_fixture import patch_all
    monkeypatch.setattr(profile_router, 'chat_completion', lambda *a,**k:'{}')
    monkeypatch.setattr(development_model, 'completion', lambda *a,**k:patch_all())
    def unavailable(_scene):
        raise RuntimeError('synthetic summary model unavailable')
    monkeypatch.setattr(context, 'resolve_model_record', unavailable)
    from .conftest import SyncASGIClient
    response = SyncASGIClient().post('/partners/partner-1/profile', headers=auth_headers(prepared[2]))
    assert response.status_code == 200
    with get_db() as conn:
        row = conn.execute('SELECT ai_profile FROM partners WHERE id=?', ('partner-1',)).fetchone()
        assert row['ai_profile'] and '公司概况' in row['ai_profile']
        assert context.current_summary(conn, 'partner-1', context.sources(conn, 'partner-1')[3]) is None


def test_only_visible_cases_and_complete_passages_enter_detailed_input(prepared):
    add_profile('partner-1', '隐藏案例涉及机密交付。\n公开经验是数据库迁移；不支持跨境。')
    with get_db() as conn:
        conn.execute("INSERT INTO cases(id,partner_id,title,description,visible,created_at,updated_at) VALUES ('hidden','partner-1','隐藏案例','机密交付不可外发',0,?,?)", (now(), now()))
        conn.execute("INSERT INTO cases(id,partner_id,title,description,visible,created_at,updated_at) VALUES ('visible','partner-1','公开案例','数据库迁移验证',1,?,?)", (now(), now()))
        _, detail, cases, _ = context.detailed_candidate(conn, 'partner-1', '数据库迁移', '寻找数据库迁移伙伴')
    serialized = json.dumps(detail, ensure_ascii=False)
    assert [case['id'] for case in cases] == ['visible']
    assert '机密交付' not in serialized and 'hidden' not in serialized
    assert '数据库迁移验证' in serialized


def test_relevant_passage_keeps_adjacent_negation():
    passages = context.select_passages('普通说明。\n具备稀有冷链回退能力。\n但不支持跨境交付。\n其他无关描述。',
                                       '稀有冷链回退', 35)
    assert passages.index('但不支持跨境交付。') == passages.index('具备稀有冷链回退能力。') + 1


def test_unprofiled_long_intro_remains_available_in_both_stages(prepared):
    make_partner('partner-2', '仅有简介伙伴')
    intro = '普通介绍' * 70 + '具备稀有冷链回退经验；但不支持跨境交付。'
    with get_db() as conn:
        conn.execute('UPDATE partners SET intro=?,capabilities=?,updated_at=? WHERE id=?',
                     (intro, '', now(), 'partner-2'))
        compact = context.compact_candidates(conn)
        _, detail, _, _ = context.detailed_candidate(conn, 'partner-2', '冷链回退', '寻找冷链回退伙伴')
    item = next(item for item in compact if item['partnerId'] == 'partner-2')
    assert item['evidenceState'] == '资料有限，待核实'
    assert item['intro'] == intro and '稀有冷链回退' in detail['intro']


def test_budget_counts_schema_and_reserves_output(prepared):
    config = resolve_model_record('partner_match')
    schema = match_understanding.InitialSelection.model_json_schema()
    with pytest.raises(ValueError, match='字符'):
        context.checked_config(config, [{'role': 'system', 'content': '甲' * 61_000}], schema,
                               context.INITIAL_CHAR_LIMIT, None)
    _, chars, estimate = context.checked_config(config, [{'role': 'system', 'content': '短输入'}], schema,
                                                context.INITIAL_CHAR_LIMIT, None)
    assert chars > len('短输入') and estimate > 0


def test_oversized_initial_bundle_fails_with_task_and_no_tail_truncation(prepared, monkeypatch):
    calls = []
    def complete(config, messages, schema):
        calls.append(schema['title'])
        if schema['title'] != 'MatchUnderstanding':
            pytest.fail('Over-budget initial input must not be sent to a model')
        return '{"in_scope":true,"facts":{"technicalNeeds":"数据库迁移"}}'
    monkeypatch.setattr(development_model, 'completion', complete)
    with get_db() as conn:
        for index in range(100):
            conn.execute('INSERT INTO partners(id,name,status,created_at,updated_at) VALUES (?,?,?,?,?)',
                         (f'large-{index:03}', '合成名称' * 180, 'active', now(), now()))
    with pytest.raises(HTTPException, match='输入预算'):
        match.match_partners(match.MatchRequest(requirement='数据库迁移'), prepared[0])
    assert calls == ['MatchUnderstanding']
    with get_db() as conn:
        assert len(context.compact_candidates(conn)) == 101
        row = conn.execute('SELECT task_status,recommendations_json FROM match_records').fetchone()
        assert row['task_status'] == 'failed' and row['recommendations_json'] == '[]'
