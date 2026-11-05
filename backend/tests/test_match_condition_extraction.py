"""Business/deployment requirements versus explicit certificates; synthetic PG checks."""
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from backend.app import development_model, match_understanding, partner_match_context as context
from backend.app.ai_client import completion_payload
from backend.app.database import get_db
from backend.app.model_resolver import model_config_from_record
from backend.app.routers import match
from backend.business import matching
from .conftest import make_user, recommendation
from .test_match_certification_priority import partner, condition
from .test_profile_report import setup, upload
from .test_matching_v3 import CONFIG


REQUIREMENT = ('【完全虚构验收项目B】虚构测试企业QX需要数据库迁移与容器部署，必须支持在企业本地部署，'
               '不接受只能在公有云交付的伙伴。预算和工期暂未确定。请安排两家合作，由其中一家牵头、'
               '另一家负责容器部署，并明确总集和双方责任。请依据现有资料推荐，并忠实说明资料中记载的历史项目角色。')
HCS = 'HCS基础设施规划设计与实施'
TAGS = ['数据库', '容器', HCS]


def understood(requirement=REQUIREMENT, conditions=(), inferred_hcs=False):
    facts = {'businessNeeds': '数据库迁移与容器部署', 'deliveryNeeds': '数据库迁移与容器部署，必须支持在企业本地部署',
             'onsiteRequirement': '必须支持在企业本地部署', 'cloudPlatformPreference': '不接受只能在公有云交付的伙伴',
             'capabilityTags': ['数据库', '容器'], 'capabilityEvidence': {'数据库': '数据库迁移', '容器': '容器部署'},
             'workEvidence': ['数据库迁移与容器部署'], 'partnerRequirements': list(conditions)}
    if inferred_hcs:
        facts['capabilityTags'].append(HCS)
        facts['capabilityEvidence'][HCS] = '必须支持在企业本地部署'
    return matching.parse_understanding(json.dumps({'in_scope': True, 'facts': facts}, ensure_ascii=False), requirement, TAGS)[0]['facts']


def certified_partners():
    for key, tags in [('database', '数据库'), ('container', '容器'), ('unknown-local', '数据库、容器'), ('cloud-only', '数据库、容器')]:
        partner(key, tags, name='合成数据库迁移与容器部署' + key)


def test_real_failure_conditions_reproduce_empty_recall_and_corrected_contract_keeps_full_supplier(setup, monkeypatch):
    certified_partners()
    pid = setup[3]
    body = ('【完全虚构测试资料】该伙伴当前提供数据库迁移与容器平台部署，明确支持在企业本地部署。'
            '历史虚构磐石项目中担任总集并牵头，独立完成数据库迁移和容器部署，已上线运行；'
            '总集牵头角色和责任仅描述这一历史项目。正式能力标签尚未维护，报价、预算和工期资料未说明。')
    upload(setup, 'whole-local-fictional.txt', body)
    with get_db() as conn:
        conn.execute("UPDATE partners SET capabilities='',identities=? WHERE id=?", (json.dumps(['服务合作伙伴'], ensure_ascii=False), pid))
        conn.execute("UPDATE model_providers SET api_key_source='db',api_key='synthetic-only'")
    # Exact erroneous condition clauses from QA CALL-003. They are legally quoted but semantically wrong.
    bad = understood(conditions=[condition(tags=['数据库', '容器'], quote='数据库迁移与容器部署'),
                                 condition(tags=[HCS], quote='必须支持在企业本地部署')], inferred_hcs=True)
    facts = understood()
    with get_db() as conn:
        assert context.recall_candidates(conn, REQUIREMENT, bad) == []
        selected = context.recall_candidates(conn, REQUIREMENT, facts)
    assert len(selected) == 5 and selected[-1]['partnerId'] == pid
    assert {item['partnerId'] for item in selected[:4]} == {'database', 'container', 'unknown-local', 'cloud-only'}
    calls = []

    def complete(config, messages, schema):
        calls.append(schema['title'])
        data = json.loads(messages[-1]['content'])
        assert data['requirement'] == REQUIREMENT
        assert context.input_metrics(config, messages, schema)[0] <= 25000
        if schema['title'] == 'MatchUnderstanding':
            prompt = messages[0]['content']
            assert '用于认证优先召回，不表示用户要求伙伴持有认证' in prompt
            assert '必须、优先或排除须限定持有认证、正式标签或身份' in prompt
            assert '相关capabilityTags为数据库、容器，partnerRequirements为空，不推导HCS认证' in prompt
            props = schema['$defs']['ProjectFacts']['properties']
            assert '不表示必须持有认证' in props['capabilityTags']['description']
            assert '必须完成的工作和部署要求不转成认证门槛' in props['partnerRequirements']['description']
            assert '不从工作内容、能力或部署环境推导认证条件' in schema['$defs']['PartnerRequirement']['properties']['capabilityTags']['description']
            evidence = os.getenv('BANFEI_MATCH_CONDITION_EVIDENCE_DIR')
            if evidence:
                Path(evidence, 'CORRECTED-UNDERSTANDING-PAYLOAD.json').write_text(json.dumps(completion_payload(model_config_from_record(CONFIG), messages, schema), ensure_ascii=False, indent=2))
            # Fixed expected extraction; this does not claim real model adherence.
            return json.dumps({'in_scope': True, 'facts': facts}, ensure_ascii=False)
        assert schema['title'] == 'MatchAnswer'
        assert data['facts']['partnerRequirements'] == []
        assert all(HCS not in candidate['certification']['relatedCapabilityTags'] for candidate in data['candidates'])
        assert data['facts']['onsiteRequirement'] == '必须支持在企业本地部署'
        assert data['facts']['cloudPlatformPreference'] == '不接受只能在公有云交付的伙伴'
        assert len(data['candidates']) == 5
        whole = next(item for item in data['candidates'] if item['partnerId'] == pid)
        passage = next(p for p in whole['profilePassages'] if body in p['text'])
        return json.dumps({'recommendations': [{**recommendation(pid, whole['name']),
            'profileEvidence': [passage['source']], 'evidenceCases': [], 'evidenceDeliverables': [],
            'evidenceType': 'current_capability', 'recommendationReason': body}],
            'supplyStatus': 'sufficient', 'gapAnalysis': '该伙伴资料支持完整工作和本地部署，预算和工期未说明。',
            'analysisRefs': []}, ensure_ascii=False)

    monkeypatch.setattr(development_model, 'completion', complete)
    owner = make_user('condition-contract-owner')
    task = match.create_task(match.TaskCreateRequest(requestId=uuid4(), requirement=REQUIREMENT), owner)
    match.executor.shutdown(wait=True)
    with get_db() as conn:
        row = dict(conn.execute('SELECT * FROM match_records WHERE id=?', (task.recordId,)).fetchone())
        saved = match_understanding.load(conn, task.recordId)
    assert row['task_status'] == 'ready', saved
    assert calls == ['MatchUnderstanding', 'MatchAnswer']
    assert saved['understanding']['facts']['capabilityTags'] == ['数据库', '容器']
    cards = json.loads(row['recommendations_json'])
    assert len(cards) == 1 and cards[0]['partnerId'] == pid
    assert cards[0]['certification']['capabilityTags'] == []
    assert cards[0]['certification']['identities'] == ['服务合作伙伴']
    assert cards[0]['recommendationReason'] == body


@pytest.mark.parametrize('phrase,mode,match_kind,tags,expected', [
    ('必须具备数据库和容器认证', 'required', 'all', ['数据库', '容器'], {'unknown-local', 'cloud-only'}),
    ('必须具备数据库或容器认证', 'required', 'any', ['数据库', '容器'], {'database', 'container', 'unknown-local', 'cloud-only'}),
    ('优先具备数据库认证', 'preferred', 'all', ['数据库'], {'database', 'container', 'unknown-local', 'cloud-only', 'whole-local'}),
    ('排除数据库认证伙伴', 'excluded', 'all', ['数据库'], {'container', 'whole-local'}),
    ('必须具备HCS基础设施规划设计与实施认证', 'required', 'all', [HCS], {'hcs-certified'}),
])
def test_explicit_certificate_conditions_keep_required_preferred_excluded_and_or_semantics(phrase, mode, match_kind, tags, expected):
    certified_partners()
    partner('whole-local', '', ['服务合作伙伴'], name='数据库迁移与容器部署完整本地交付')
    if HCS in tags:
        partner('hcs-certified', HCS, name='数据库迁移与容器部署HCS认证伙伴')
    requirement = REQUIREMENT + phrase + '。'
    facts = understood(requirement, [condition(mode=mode, tags=tags, match=match_kind, quote=phrase)])
    with get_db() as conn:
        selected = context.recall_candidates(conn, requirement, facts)
    assert {item['partnerId'] for item in selected} == expected
    assert facts['partnerRequirements'][0]['mode'] == mode
    assert facts['partnerRequirements'][0]['match'] == match_kind
    assert facts['onsiteRequirement'] == '必须支持在企业本地部署'
