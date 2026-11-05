"""Independent whole-demand assessment contracts; isolated PG, synthetic responses."""
import copy
import json
from uuid import uuid4

import pytest
from backend.app import development_model, match_understanding, partner_match_context
from backend.app.ai_client import completion_payload
from backend.app.database import get_db
from backend.app.model_resolver import model_config_from_record
from backend.app.routers import match
from backend.business import matching
from .conftest import auth_headers, make_partner, make_task, make_user, recommendation
from .test_profile_report import setup, upload
from .test_matching_v3 import CONFIG


@pytest.mark.parametrize('cooperation', ['', '请安排两家合作，由数据库伙伴牵头、容器伙伴负责部署，并指定总集和责任分工。'])
def test_full_request_and_independent_contract_reach_both_stages_without_changing_recall(setup, monkeypatch, cooperation):
    requirement = '需要数据库迁移和容器部署。必须本地部署，排除公有云；预算未知。' + cooperation
    pid = setup[3]
    historical = '历史项目中该伙伴作为总集牵头，负责数据库迁移和容器部署，责任范围为该历史项目。当前支持本地部署，不提供公有云；本次预算与工期资料未说明。'
    upload(setup, 'historical-role.txt', historical)
    for key, tag in [('cert-database', '数据库'), ('cert-container', '容器')]:
        make_partner(key, '合成认证伙伴' + tag)
        with get_db() as conn:
            conn.execute('UPDATE partners SET capabilities=? WHERE id=?', (tag, key))
    with get_db() as conn:
        conn.execute("UPDATE partners SET capabilities='',identities=NULL WHERE id=?", (pid,))
        conn.execute("UPDATE model_providers SET api_key_source='db',api_key='synthetic-only'")
    facts = {'technicalNeeds': '数据库迁移和容器部署', 'deliveryNeeds': requirement,
             'onsiteRequirement': '必须本地部署', 'cloudPlatformPreference': '排除公有云',
             'capabilityTags': ['数据库', '容器'],
             'capabilityEvidence': {'数据库': '数据库迁移', '容器': '容器部署'},
             'workEvidence': ['数据库迁移和容器部署']}
    calls = []

    def complete(config, messages, schema):
        calls.append(schema['title'])
        wire = completion_payload(model_config_from_record(CONFIG), messages, schema)
        prompt = wire['messages'][0]['content']
        data = json.loads(wire['messages'][1]['content'])
        assert data['requirement'] == requirement
        assert '逐家针对完整需求独立评估' in prompt
        assert '即使用户主动要求合作，也不生成伙伴间分工、牵头、总集或责任安排' in prompt
        assert '允许伙伴按各自能力分工' not in prompt
        assert '只有用户明确要求单家包办' not in prompt
        assert partner_match_context.input_metrics(config, messages, schema)[0] <= 25000
        if schema['title'] == 'MatchUnderstanding':
            props = schema['$defs']['ProjectFacts']['properties']
            assert '完整需求独立评估' in props['deliveryNeeds']['description']
            return json.dumps({'in_scope': True, 'facts': facts}, ensure_ascii=False)
        assert schema['title'] == 'MatchAnswer'
        assert data['facts']['onsiteRequirement'] == '必须本地部署'
        assert data['facts']['cloudPlatformPreference'] == '排除公有云'
        assert data['facts']['partnerRequirements'] == []  # Ordinary work adds no mandatory certification gate.
        candidates = data['candidates']
        assert {p['partnerId'] for p in candidates[:2]} == {'cert-container', 'cert-database'}
        by_id = {p['partnerId']: p for p in candidates}
        assert by_id['cert-container']['certification']['relatedCapabilityTags'] == ['容器']
        assert by_id['cert-database']['certification']['relatedCapabilityTags'] == ['数据库']
        assert len(candidates) == 3 and candidates[2]['partnerId'] == pid
        selected = by_id[pid]
        passage = next(p for p in selected['profilePassages'] if historical in p['text'])
        assert '不能以待确认、通用能力或其他伙伴代替' in prompt
        assert '资料未说明不等于不具备，不能虚构已满足' in prompt
        assert '不合并多家能力宣称需求已满足' in prompt
        assert '真实历史角色事实保留' in schema['$defs']['Candidate']['properties']['recommendationReason']['description']
        assert schema['properties']['recommendations']['maxItems'] == 5
        # A fixed legal response checks transport and persistence, not real model judgment.
        return json.dumps({'recommendations': [{**recommendation(pid, selected['name']),
            'evidenceType': 'current_capability', 'profileEvidence': [passage['source']],
            'evidenceCases': [], 'evidenceDeliverables': [],
            'recommendationReason': historical,
            'riskNotes': '本次预算与工期资料未说明，不虚构报价或承诺。'}],
            'supplyStatus': 'sufficient', 'gapAnalysis': '该伙伴资料支持完整工作及本地部署，预算与工期尚未说明。',
            'analysisRefs': []}, ensure_ascii=False)

    monkeypatch.setattr(development_model, 'completion', complete)
    owner = make_user('whole-demand-owner')
    accepted = match.create_task(match.TaskCreateRequest(requestId=uuid4(), requirement=requirement), owner)
    match.executor.shutdown(wait=True)
    with get_db() as conn:
        task = dict(conn.execute('SELECT * FROM match_records WHERE id=?', (accepted.recordId,)).fetchone())
        saved = match_understanding.load(conn, accepted.recordId)
    assert task['task_status'] == 'ready', saved
    assert calls == ['MatchUnderstanding', 'MatchAnswer']
    assert task['requirement'] == requirement
    assert saved['outcome']['supplyStatus'] == 'sufficient'
    card = json.loads(task['recommendations_json'])[0]
    assert card['recommendationReason'] == historical
    assert any(source['text'] == historical for source in saved['detail_source_map'][pid].values())
    assert card['certification']['relatedCapabilityTags'] == []


def test_rule_change_invalidates_understanding_and_candidate_stamps_without_mutating_old_snapshot(monkeypatch):
    with get_db() as conn:
        conn.execute("UPDATE model_providers SET api_key_source='db',api_key='synthetic-only'")
    calls = []
    def complete(config, messages, schema):
        calls.append(schema['title'])
        return json.dumps({'in_scope': True, 'facts': {'technicalNeeds': '数据库迁移'}})
    monkeypatch.setattr(development_model, 'completion', complete)
    version = matching.MATCHING_RULES_VERSION
    assert version != '20261104-certification-priority-v5'
    with monkeypatch.context() as previous:
        previous.setattr(matching, 'MATCHING_RULES_VERSION', '20261104-certification-priority-v5')
        old = match_understanding.prepare('需要数据库迁移。')
        old_stamp = match._candidate_stamp()
    original = copy.deepcopy(old)
    current = match_understanding.prepare('需要数据库迁移。', cached=old)
    assert current['stamp'] != old['stamp'] and match._candidate_stamp() != old_stamp
    assert match_understanding.prepare('需要数据库迁移。', cached=current) is current
    assert old == original and calls == ['MatchUnderstanding', 'MatchUnderstanding']


def test_existing_division_result_remains_readable_without_rewrite_or_model_call(client, monkeypatch):
    partner = make_partner('historical-partner', '历史伙伴')
    owner = make_user('historical-division-owner')
    other = make_user('unrelated-reader')
    card = {**recommendation(partner['id'], partner['name']),
            'recommendationReason': '旧结果建议该伙伴牵头，与另一伙伴分工协作。'}
    task = make_task(owner, '旧需求：安排合作分工。', recommendations=[card])
    def forbidden(*args, **kwargs):
        pytest.fail('Reading an old result must not invoke a model')
    monkeypatch.setattr(development_model, 'completion', forbidden)
    with get_db() as conn:
        before = conn.execute('SELECT recommendations_json FROM match_records WHERE id=?', (task,)).fetchone()[0]
    response = client.get('/agent/tasks/' + task, headers=auth_headers(owner))
    assert response.status_code == 200
    assert response.json()['recommendations'][0]['recommendationReason'] == card['recommendationReason']
    assert client.get('/agent/tasks/' + task, headers=auth_headers(other)).status_code == 404
    with get_db() as conn:
        assert conn.execute('SELECT recommendations_json FROM match_records WHERE id=?', (task,)).fetchone()[0] == before



@pytest.mark.parametrize('mandatory,body,certified,admitted', [
    (True, '【合成资料】已维护数据库与容器正式能力标签；现有资料未说明是否支持企业本地部署，没有已交付项目记录，不能据此认定支持本地部署。', True, False),
    (True, '【合成资料】当前提供数据库迁移与容器平台部署，但明确只支持公有云交付，不提供企业本地部署。', True, False),
    (False, '【合成资料】已维护数据库与容器正式能力标签；现有资料未说明是否支持企业本地部署，没有已交付项目记录。', True, True),
    (False, None, True, True),
    (True, '【合成资料】支持企业本地数据库迁移与容器平台部署。历史磐石项目中作为总集并牵头，独立完成迁移和部署，责任仅描述该历史项目；预算与工期未说明。', True, True),
    (False, '【合成资料】提供数据库迁移与容器平台部署，支持企业本地部署。历史澄川项目中作为总集并牵头完成迁移与部署，已上线；预算与工期未说明。', False, True),
], ids=['mandatory-unknown', 'mandatory-conflict', 'ordinary-unknown', 'certification-only', 'mandatory-supported-history', 'no-identity-condition'])
def test_explicit_business_conditions_and_ordinary_unknowns_keep_distinct_admission(setup, monkeypatch, mandatory, body, certified, admitted):
    pid = setup[3]
    if body is not None:
        upload(setup, 'synthetic-admission.txt', body)
    with get_db() as conn:
        conn.execute('UPDATE partners SET capabilities=?,identities=NULL WHERE id=?', ('数据库、容器' if certified else '', pid))
        conn.execute("UPDATE model_providers SET api_key_source='db',api_key='synthetic-only'")
    local = '必须支持在企业本地部署，不接受只能在公有云交付的伙伴。' if mandatory else '希望支持企业本地部署，可在接洽时确认。'
    requirement = '需要数据库迁移与容器平台部署。' + local + '预算与工期尚未确定。'
    facts = {'technicalNeeds': '数据库迁移与容器平台部署', 'cloudPlatformPreference': local,
             'capabilityTags': ['数据库', '容器'],
             'capabilityEvidence': {'数据库': '数据库迁移', '容器': '容器平台部署'},
             'workEvidence': ['数据库迁移与容器平台部署']}
    calls = []
    reason = body or '正式数据库、容器认证支持相关当前能力，未提供已交付项目资料。'
    risk = '本次部署环境资料未说明，可在接洽时确认。' if not mandatory and (body is None or '未说明是否' in body) else ''
    if admitted:
        gap = '现有依据支持该伙伴接洽，预算与工期尚未确定。'
        supply = 'sufficient' if mandatory else 'partial'
    elif '只支持公有云' in body:
        gap = '资料明确只支持公有云交付，与本次必须本地部署冲突，因此未推荐。'
        supply = 'gap'
    else:
        gap = '现有资料未说明是否支持企业本地部署，这项明确必备条件未被证实，因此本次未推荐。'
        supply = 'unknown'

    def complete(config, messages, schema):
        calls.append(schema['title'])
        data = json.loads(messages[-1]['content'])
        assert data['requirement'] == requirement
        assert partner_match_context.input_metrics(config, messages, schema)[0] <= 25000
        if schema['title'] == 'MatchUnderstanding':
            return json.dumps({'in_scope': True, 'facts': facts}, ensure_ascii=False)
        assert schema['title'] == 'MatchAnswer'
        assert data['facts']['cloudPlatformPreference'] == local
        assert data['facts']['partnerRequirements'] == []
        prompt = messages[0]['content']
        assert '不得列入recommendations，只在gapAnalysis说明本次未推荐' in prompt
        assert '降低分数或在riskNotes写待确认不能代替入选条件' in prompt
        assert '未被用户设为必备条件的未知信息可作为必要接洽事项' in prompt
        assert '用户未要求的身份不因未维护而添加身份核验、风险或接洽前提' in prompt
        assert '实现字段或枚举不得写入这些正文' in prompt
        assert '明确必备条件未证实或冲突时不列入' in schema['properties']['recommendations']['description']
        assert '资料未知不等于实际不具备' in schema['properties']['gapAnalysis']['description']
        assert '业务语言' in schema['$defs']['Candidate']['properties']['recommendationReason']['description']
        assert '用户未要求的身份' in schema['$defs']['Candidate']['properties']['riskNotes']['description']
        assert len(data['candidates']) == 1
        candidate = data['candidates'][0]
        assert candidate['certification']['servicePartnerBasis'] == ('capability_tag' if certified else None)
        assert candidate['certification']['identities'] == []
        refs = [p['source'] for p in candidate['profilePassages'] if body is not None and body in p['text']]
        assert bool(refs) is (body is not None)
        reference = {'partnerId': pid, 'profileEvidence': refs, 'evidenceCases': [], 'evidenceDeliverables': []}
        # These fixed results exercise admission persistence and references; real model adherence is tested separately.
        cards = [{**recommendation(pid, candidate['name']), **reference, 'evidenceType': 'current_capability',
                  'recommendationReason': reason, 'riskNotes': risk}] if admitted else []
        return json.dumps({'recommendations': cards, 'supplyStatus': supply, 'gapAnalysis': gap,
                           'analysisRefs': [reference] if not admitted else []}, ensure_ascii=False)

    monkeypatch.setattr(development_model, 'completion', complete)
    owner = make_user('explicit-business-admission-owner')
    accepted = match.create_task(match.TaskCreateRequest(requestId=uuid4(), requirement=requirement), owner)
    match.executor.shutdown(wait=True)
    with get_db() as conn:
        row = dict(conn.execute('SELECT * FROM match_records WHERE id=?', (accepted.recordId,)).fetchone())
        saved = match_understanding.load(conn, accepted.recordId)
    assert row['task_status'] == 'ready', saved
    assert calls == ['MatchUnderstanding', 'MatchAnswer']
    assert saved['outcome']['supplyStatus'] == supply
    assert saved['outcome']['gapAnalysis'] == gap
    cards = json.loads(row['recommendations_json'])
    assert len(cards) == int(admitted)
    response = setup[0].get('/agent/tasks/' + accepted.recordId, headers=auth_headers(owner))
    assert response.status_code == 200
    public = response.json()
    prose = public.get('answer', '') + ''.join(card['recommendationReason'] + card['riskNotes'] for card in public['recommendations'])
    assert not any(token in prose for token in ('relatedCapabilityTags', 'servicePartnerBasis', 'capability_tag'))
    if admitted:
        assert cards[0]['recommendationReason'] == reason and cards[0]['riskNotes'] == risk
        assert cards[0]['certification']['servicePartnerBasis'] == ('capability_tag' if certified else None)
        assert '核验身份' not in prose and '确认服务伙伴身份' not in prose
    else:
        assert public['recommendations'] == []
        assert saved['outcome']['analysisComplete']
