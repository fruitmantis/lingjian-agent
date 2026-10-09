"""Business intent stays independent of answer/evidence-handling instructions."""
import pytest
from uuid import uuid4
from backend.app.database import get_db
from backend.app.routers import match
from backend.app import partner_match_context
from backend.business import matching
from .conftest import make_partner, recommendation

# Exact synthetic prompt which produced the captured 1 -> 0 false rejection.
FINAL_AUDIT_REQUIREMENT = (
    '【最终验收20261007匹配】合成项目：需要能提供医药健康、AI药物研发相关专业服务的现有启用伙伴，先做小范围方案沟通。'
    '请推荐最多两家，区分资料自述与已交付案例；药物研发环节、资质、地域、预算和交付时间均待核实，未知项不要编造。'
    '资料不足时保留相关线索并明确风险，不能据此断言没有合适伙伴。'
)
ANSWER_REQUIREMENTS = '请推荐最多两家，区分资料自述与已交付案例。资料不足时保留相关线索并明确风险，不能据此断言没有合适伙伴。'


def outcome(requirement, facts, body, *, kind='current_capability', quote=None):
    partner = make_partner('synthetic-core-'+uuid4().hex)
    with get_db() as conn:
        conn.execute('UPDATE partners SET capabilities=? WHERE id=?', ('', partner['id']))
        partner = dict(conn.execute('SELECT * FROM partners WHERE id=?', (partner['id'],)).fetchone())
    source = f"partner:{partner['id']}:profile:0"
    row = (partner, {
        'profilePassages': [{'source': source, 'text': body}],
        'inputCoverage': {'complete': True, 'omittedCoreGroups': 0, 'sourceState': 'ready'},
    }, [], [])
    item = {**recommendation(), 'partnerId': partner['id'], 'partnerName': partner['name'],
            'evidenceType': kind, 'profileEvidence': [{'source': source, 'quote': quote or body}],
            'evidenceCases': [], 'evidenceDeliverables': []}
    rejected = []
    recs = match._validated_recommendations([item], [partner], {partner['id']: []},
                                          {partner['id']: []}, rejected)
    assert len(recs) == 1 and rejected == []
    return match._validated_outcome(recs, {'recommendations': [item], 'supplyStatus': 'sufficient'},
                                    False, [row], requirement=requirement, facts=facts)


def test_exact_final_audit_prompt_retains_current_business_evidence():
    facts = {
        'businessNeeds': '需要能提供医药健康、AI药物研发相关专业服务的现有启用伙伴，先做小范围方案沟通，推荐最多两家，区分资料自述与已交付案例。',
        'technicalNeeds': 'AI药物研发相关专业服务（具体技术栈待核实）',
        'caseRequirements': '需区分资料自述与已交付案例；资料不足时保留相关线索并明确风险',
    }
    result = outcome(FINAL_AUDIT_REQUIREMENT, facts, '行业专业服务：医药健康：AI药物研发/工艺优化。')
    assert len(result['recommendations']) == 1
    assert result['analysisComplete'] and result['supplyStatus'] == 'sufficient'
    assert result['recommendations'][0]['recommendationReason']==recommendation()['recommendationReason']


@pytest.mark.parametrize('subject', ['药物研发', '数据库迁移', '网络安全', 'ScopeQuasar'])
def test_answer_requirements_do_not_change_business_policy_or_core_passage(subject):
    plain = f'需要{subject}服务伙伴。'
    verbose = plain + ANSWER_REQUIREMENTS
    body = f'具备{subject}能力，相关交付经历待核实。'
    facts = {'technicalNeeds': subject, 'businessNeeds': plain + ANSWER_REQUIREMENTS,
             'followUpQuestions': ['是否需要ScopeOther服务？'], 'caseRequirements': ANSWER_REQUIREMENTS}
    for requirement in [plain, verbose]:
        result = outcome(requirement, facts, body)
        assert len(result['recommendations']) == 1
        assert result['analysisComplete'] and result['supplyStatus'] == 'sufficient'
        groups, coverage = partner_match_context.passage_selection(body, requirement, 20, facts=facts)
        assert coverage['complete'] and any(text == body and core for _, text, core in groups)


@pytest.mark.parametrize('body', ['已为制药企业完成机房部署。', '具备ScopeOther办公自动化能力。'])
def test_answer_instructions_cannot_make_an_unrelated_business_relevant(body):
    result = outcome(FINAL_AUDIT_REQUIREMENT, {'technicalNeeds': 'AI药物研发'}, body, kind='unrelated')
    assert result['recommendations'] == []
    assert result['analysisComplete']


@pytest.mark.parametrize('body', [
    '该能力处于规划阶段，尚未交付。\n具备数据库迁移能力。',
    '具备数据库迁移能力。\n这项能力处于规划阶段，尚未交付。',
])
def test_business_fact_reuse_keeps_own_planning_qualifiers(body):
    result = outcome('需要数据库迁移伙伴。' + ANSWER_REQUIREMENTS,
                     {'technicalNeeds': '数据库迁移'}, body, kind='planning_only', quote='具备数据库迁移能力。')
    assert result['recommendations'] == [] and result['analysisComplete']
    assert '未来规划线索' in result['answer']


@pytest.mark.parametrize('body,kind,count', [
    ('具备数据库迁移能力，相关交付经历待核实。', 'current_capability', 1),
    ('具备数据库迁移能力。', 'delivered_project', 1),
    ('计划开发数据库迁移方案，尚未交付。', 'planning_only', 0),
    ('已交付数据库迁移平台，项目完成验收。', 'delivered_project', 1),
])
def test_explicit_delivery_history_condition_remains_on_full_original(body, kind, count):
    facts = {'technicalNeeds': '数据库迁移'}
    for requirement in ['必须有数据库迁移交付案例的服务伙伴。',
                        '必须有数据库迁移交付案例的服务伙伴。' + ANSWER_REQUIREMENTS]:
        result = outcome(requirement, facts, body, kind=kind)
        assert len(result['recommendations']) == count
        assert result['analysisComplete']
        if count:
            assert result['supplyStatus'] == 'sufficient'
        else:
            assert result['supplyStatus'] == 'unknown'


def test_ungrounded_fact_or_followup_question_cannot_broaden_original_subject():
    requirement = '需要ScopeQuasar服务伙伴。' + ANSWER_REQUIREMENTS
    facts = {'technicalNeeds': 'ScopeOther',
             'followUpQuestions': ['是否需要ScopeOther服务？'], 'projectKeywords': 'ScopeOther',
             'industry': 'ScopeOther', 'region': 'ScopeOther'}
    result = outcome(requirement, facts, '具备ScopeOther能力。', kind='unrelated')
    assert result['recommendations'] == [] and result['analysisComplete']


def test_no_extracted_business_fact_still_excludes_answer_directives():
    requirement = '需要ScopeQuasar服务伙伴。' + ANSWER_REQUIREMENTS
    result = outcome(requirement, {}, '具备ScopeQuasar能力。')
    assert len(result['recommendations']) == 1 and result['analysisComplete']


@pytest.mark.parametrize('requirement,subject', [
    ('请推荐最多两家数据库迁移服务伙伴。', '数据库迁移'),
    ('需要推荐算法服务伙伴。', '推荐算法'),
    ('需要区分恶意流量的服务伙伴。', '恶意流量'),
])
def test_business_subject_inside_a_request_is_grounded_before_directive_filtering(requirement, subject):
    result = outcome(requirement + ANSWER_REQUIREMENTS, {'technicalNeeds': subject},
                     f'具备{subject}能力，相关交付经历待核实。')
    assert len(result['recommendations']) == 1
    assert result['analysisComplete'] and result['supplyStatus'] == 'sufficient'
