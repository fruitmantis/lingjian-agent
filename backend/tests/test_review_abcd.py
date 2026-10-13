"""Approved A/B/C/D behavior on isolated PG with actual wire/save/read outlets."""
import copy
import json
from uuid import uuid4
import pytest
from backend.app import development_engine as engine, development_lifecycle as life
from backend.app import development_model as model, development_views as views
from backend.app import profile_sources as sources, match_understanding
from backend.app.database import get_db
from backend.app.development_types import AdviceOutput, AdvicePatch, DevelopmentRequest, Submit, Conversation
from backend.business import development, matching
from backend.business.matching_types import MatchUnderstanding
from backend.tests.conftest import make_user, auth_headers
from backend.tests.test_development_lifecycle import prepared
from backend.tests.test_review_rectification import twelve_mixed
from backend.tests.test_profile_report import setup, upload, organize, profile, merge_result


@pytest.mark.parametrize('contract', [AdviceOutput, AdvicePatch])
def test_new_model_contract_ignores_unused_limitations_before_save(contract):
    assert 'limitations' not in contract.model_json_schema()['properties']
    value = {'target_partner_id': None, 'answer': '根据实际条件继续。',
             'used_refs': [], 'used_profile_chapters': [], 'limitations': ['旧独立审查字段不采用']}
    value.update({'stages': []} if contract is AdviceOutput else {'changes': [], 'answer_changes': []})
    parsed = development.parse(json.dumps(value), contract, [])
    assert 'limitations' not in parsed
    assert parsed['answer'] == value['answer']


def test_matching_wire_drops_questionnaire_and_history_column_stays_readable(setup, monkeypatch):
    from backend.app.routers import match
    from backend.tests.support.matching import current_protocol
    client, _, _, partner_id, _ = setup
    upload(setup, 'explicit.txt', '具备ExplicitRetailQuasar系统压测能力。')
    owner = make_user('review-abcd-match-owner')
    requirement = '需要ExplicitRetailQuasar；合作方必须有电商压测与高可用改造交付依据，预算与地区暂未确定。'
    calls = []
    def complete(config, messages, schema):
        calls.append(schema['title'])
        if schema['title'] == 'MatchUnderstanding':
            assert 'followUpQuestions' not in schema['$defs']['ProjectFacts']['properties']
            return json.dumps({'in_scope': True, 'facts': {'technicalNeeds': 'ExplicitRetailQuasar',
                'caseRequirements': '合作方必须有电商压测与高可用改造交付依据',
                'followUpQuestions': ['预算是多少？', '地区在哪里？']}, 'tag_suggestions': []})
        data = json.loads(messages[-1]['content'])
        assert data['requirement'] == requirement and data['candidates']
        assert data['facts']['caseRequirements'] == '合作方必须有电商压测与高可用改造交付依据'
        assert 'followUpQuestions' not in data['facts']
        return json.dumps({'recommendations': [], 'supplyStatus': 'gap',
                          'gapAnalysis': '资料不支持本次明示筛选条件。', 'analysisRefs': []})
    monkeypatch.setenv('LLM_API_KEY', 'synthetic-key')
    monkeypatch.setattr(model, 'completion', current_protocol(complete))
    accepted = match.create_task(match.TaskCreateRequest(requestId=uuid4(), requirement=requirement), owner)
    match.executor.shutdown(wait=True)
    with get_db() as conn:
        snapshot = match_understanding.load(conn, accepted.recordId)
        opportunity = dict(conn.execute('SELECT * FROM project_opportunities WHERE match_record_id=?', (accepted.recordId,)).fetchone())
        assert json.loads(opportunity['follow_up_questions']) == []
        conn.execute('UPDATE project_opportunities SET follow_up_questions=? WHERE id=?',
                     (json.dumps(['历史记录里的原问题']), opportunity['id']))
    assert calls == ['MatchUnderstanding', 'MatchAnswer']
    assert 'followUpQuestions' not in snapshot['understanding']['facts']
    read = client.get('/agent/tasks/' + accepted.recordId, headers=auth_headers(owner))
    assert read.status_code == 200
    assert json.loads(read.json()['opportunity']['followUpQuestions']) == ['历史记录里的原问题']


def test_twelve_item_history_user_plan_separation_and_legacy_limits_inheritance(twelve_mixed, monkeypatch):
    prepared, captures = twelve_mixed
    user = prepared[0]
    original = model.completion
    plan = '模型本轮计划选择RAG方向替代，但这不是用户点名。'
    wire = []
    def complete(config, messages, schema):
        data = json.loads(messages[-1]['content'])
        wire.append((schema['title'], copy.deepcopy(data)))
        result = json.loads(original(config, messages, schema))
        if schema['title'] == 'Understanding':
            result['effective_direction'] = plan
            result['effective_baseline'] = data['request'].get('known_baseline', '')
            result['effective_constraints'] = data['constraints']
        elif schema['title'] in ('AdviceOutput', 'AdvicePatch'):
            assert 'limitations' not in schema['properties']
            result['limitations'] = ['不得保存的新独立审查段']
        return json.dumps(result)
    monkeypatch.setattr(model, 'completion', complete)
    goal = '数据库与AI Agent开发实践'
    request = DevelopmentRequest(target_partner_id='partner-1', development_direction=goal,
                                 known_baseline='用户会Python和API。', constraints={'方式': '远程'},
                                 model_input_allowed=True, partner_goal_allowed=True)
    accepted = life.create(Submit(submission_id='abcd-twelve-create', request=request), user)
    engine.execute(accepted['run_id'])
    before = views.detail(accepted['plan_id'], user)
    base = before['plan']['current_version_id']
    assert base and before['payload']['limitations'] == []
    # Simulate a pre-change payload before the normal immutable Version INSERT;
    # never update a saved Version or disable its database trigger.
    assemble = engine.assemble
    def seed_historical(output, request, analysis, pool, actor):
        payload = assemble(output, request, analysis, pool, actor)
        payload['limitations'] = ['历史版本原限制，继续保留读取。']
        payload['effective_request']['development_direction'] = '旧模型计划误写成的用户方向'
        payload['effective_request']['development_goal'] = '旧模型计划误写成的用户方向'
        return payload
    monkeypatch.setattr(engine, 'assemble', seed_historical)
    accepted = life.create(Submit(submission_id='abcd-twelve-historical', request=request), user)
    engine.execute(accepted['run_id'])
    monkeypatch.setattr(engine, 'assemble', assemble)
    before = views.detail(accepted['plan_id'], user)
    base = before['plan']['current_version_id']
    assert base
    old = copy.deepcopy(before['payload'])
    messages = ['保留全部12项资源。', '需要继续保留Python和API基础。', '第二个实验换成更容易的。',
                '保留其余内容。', '继续按远程方式安排。']
    answers = ['旧答复一。', '旧答复二。', '第二个实验是Prompt。', old['answer'], '旧答复三。']
    history = [{'submission_id': 'abcd-old-' + str(index), 'version_id': base, 'message': message,
                'answer': answer, 'created_at': '2020-01-0' + str(index + 1) + 'T00:00:00+00:00',
                'fingerprint': 'historical', 'dependencies': [], 'used_refs': [], 'format_version': 2}
               for index, (message, answer) in enumerate(zip(messages, answers))]
    with get_db() as conn:
        stored = json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',
                                       (before['plan']['request_id'],)).fetchone()[0])
        stored.update(_conversation=history, _effective_version_id=base,
                      _effective_request={**old['effective_request'], 'known_baseline': '用户会Python和API。'})
        conn.execute('UPDATE development_requests SET payload_json=? WHERE id=?',
                     (json.dumps(stored), before['plan']['request_id']))
    explain_message = '解释第二个实验。'
    run = views.converse(accepted['plan_id'], Conversation(submission_id='abcd-twelve-explain',
                         based_on_version_id=base, message=explain_message), user)
    engine.execute(run['run_id'])
    frame = wire[-1][1]
    assert frame['request']['development_direction'] == goal and frame['message'] == explain_message
    assert frame['request']['known_baseline'] == '用户会Python和API。' and frame['constraints'] == {'方式': '远程'}
    assert 'earlier_user_messages' not in frame
    assert frame['recent_exchanges'] == [{'message': messages[-1], 'answer_role': 'past_assistant', 'answer': answers[-1]}]
    assert all(answer not in json.dumps(frame,ensure_ascii=False) for answer in (answers[0],answers[1],answers[2]))
    assert 'limitations' not in frame['current']['presentation']
    resources = frame['current']['resources']
    assert len(resources) == 12 and resources[1]['reference_label'] == '实验1｜Agent实践2'
    assert resources[3]['reference_label'] == '实验2｜Agent实践4'
    explained = views.detail(accepted['plan_id'], user)
    assert explained['plan']['current_version_id'] == base and len(explained['versions']) == 1
    assert explained['payload']['limitations'] == old['limitations']
    with get_db() as conn:
        saved = json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',
                                      (before['plan']['request_id'],)).fetchone()[0])
        assert saved['_conversation'][:5] == history
        assert saved['_effective_request']['development_direction'] == goal
    patch_message = '第二个实验换一个更进阶的，其他不变。'
    run = views.converse(accepted['plan_id'], Conversation(submission_id='abcd-twelve-patch',
                         based_on_version_id=base, message=patch_message), user)
    engine.execute(run['run_id'])
    patch_input = wire[-1][1]
    assert wire[-1][0] == 'AdvicePatch'
    assert patch_input['request']['development_direction'] == goal
    assert patch_input['message'] == patch_message and patch_input['understanding']['effective_direction'] == plan
    after = views.detail(accepted['plan_id'], user)
    new = after['payload']['stages'][0]['items']
    previous = old['stages'][0]['items']
    assert len(new) == 12 and len(after['versions']) == 2
    assert new[3]['source_id'] == 'mixed-13'
    for index, item in enumerate(previous):
        assert new[index]['item_id'] == item['item_id']
        if index != 3: assert new[index] == item
    assert after['payload']['limitations'] == old['limitations']
    assert after['payload']['effective_request']['development_direction'] == goal
    assert after['payload']['answer'] == '第一段保持。\n使用进阶实验验证Agent部署。\n末段保持。'
    with get_db() as conn:
        old_deps = json.loads(conn.execute('SELECT dependency_json FROM development_versions WHERE id=?', (base,)).fetchone()[0])
        new_deps = json.loads(conn.execute('SELECT dependency_json FROM development_versions WHERE id=?',
                                        (after['plan']['current_version_id'],)).fetchone()[0])
    assert all(ref in new_deps for ref in old_deps if ref['source_id'] != 'mixed-4')


def test_native_business_body_projection_preserves_negation_and_unknown_layout():
    text = ('资料存档\n原始URL：https://example.invalid/article\n证据边界：采集者撤销覆盖。\n导航\n'
            '实际项目标题\n2026-06-04\n集团自述内部演示，尚未对外交付。\n'
            '01 技术产品\n产品连接会员系统；本项目撤销旧接口并计划升级。\n'
            '推荐阅读\n2026-06-05\n另一篇文章。')
    source = {'kind': 'document', 'id': 'synthetic', 'text': text}
    blocks, mapping = sources.source_blocks(source)
    delivered = '\n'.join(block['text'] for block in blocks)
    assert all(word in delivered for word in ('实际项目标题', '2026-06-04', '内部演示', '尚未对外交付', '撤销旧接口', '计划升级'))
    assert all(word not in delivered for word in ('原始URL', '证据边界', '采集者', '另一篇文章'))
    assert source['text'] == text
    for block in blocks:
        row = mapping[block['id']]
        assert block['text'] == text[row['start']:row['end']]
    unknown = {'kind': 'document', 'id': 'unknown', 'text': '未知版式，采集字样也可能是业务内容。'}
    assert sources.source_blocks(unknown)[0] == [{'id': 'B1', 'text': unknown['text']}]


def test_normal_retry_reextracts_only_selected_complete_cache_and_merge_repeat_is_zero(setup, monkeypatch):
    client, admin, _, partner_id, _ = setup
    original = ('资料存档\n原始URL：https://example.invalid/article\n证据边界：采集者撤销交付覆盖。\n导航\n'
                '实际会员项目\n2026-06-04\n集团自述内部演示，尚未对外交付。\n'
                '01 技术与产品\n平台连接会员系统，并计划升级；项目撤销旧接口。')
    calls = []
    def complete(config, messages, schema):
        data = json.loads(messages[-1]['content'])
        calls.append(copy.deepcopy(data))
        if 'blocks' not in data: return json.dumps(merge_result(data))
        text = '\n'.join(block['text'] for block in data['blocks'])
        assert '证据边界' not in text and '采集者' not in text
        assert all(word in text for word in ('内部演示', '尚未对外交付', '会员系统', '撤销旧接口'))
        ids = [block['id'] for block in data['blocks']]
        return json.dumps({'sections': [
            {'chapter': 5, 'summary': '平台连接会员系统，版本' + str(len(calls)), 'block_ids': ids},
            {'chapter': 6, 'summary': '集团内部会员项目演示，尚未对外交付。', 'block_ids': ids}]})
    monkeypatch.setattr(model, 'completion', complete)
    file_id = upload(setup, 'archive.txt', original)
    with get_db() as conn:
        source = sources.source(conn, partner_id, 'document', file_id)
        assert source['text'] == original
        row = dict(conn.execute('SELECT * FROM partner_profile_sources WHERE source_id=?', (file_id,)).fetchone())
        legacy = json.loads(row['sections_json'])
        legacy[0]['summary'] = '旧采集评价仍作为历史失败对照。'
        legacy_json = json.dumps(legacy)
        conn.execute('UPDATE partner_profile_sources SET sections_json=? WHERE source_id=?', (legacy_json, file_id))
        stamp = sources.stamp(source)
    sources.process_source(partner_id, 'document', file_id, stamp)
    profile(setup, True)
    with get_db() as conn:
        assert conn.execute('SELECT sections_json FROM partner_profile_sources WHERE source_id=?', (file_id,)).fetchone()[0] == legacy_json
    assert len(calls) == 1
    response = client.post(f'/partners/{partner_id}/documents/{file_id}/retry', headers=admin)
    assert response.status_code == 200 and len(calls) == 2
    with get_db() as conn:
        current = sources.source(conn, partner_id, 'document', file_id)
        assert current['text'] == original and sources.stamp(current) == stamp
        row = dict(conn.execute('SELECT * FROM partner_profile_sources WHERE source_id=?', (file_id,)).fetchone())
    assert row['state'] == 'ready' and '旧采集评价' not in row['sections_json']
    for unit in json.loads(row['sections_json']):
        assert all('证据边界' not in quote for quote in unit['quotes'])
        assert all(quote in original for quote in unit['quotes'])
    organize(setup)
    assert len(calls) == 3 and 'blocks' not in calls[-1]
    saved = profile(setup)['ai_profile']
    organize(setup)
    assert len(calls) == 3 and profile(setup)['ai_profile'] == saved
