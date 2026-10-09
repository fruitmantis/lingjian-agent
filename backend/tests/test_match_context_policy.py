"""Actual request-shape regressions using disposable PG and synthetic sources."""
import json
from uuid import uuid4
import pytest
from backend.app import development_model, match_understanding, partner_match_context
from backend.app.ai_client import completion_payload
from backend.app.model_resolver import model_config_from_record
from backend.app.database import get_db
from backend.app.routers import match
from backend.business import matching
from .conftest import make_user, recommendation
from .test_profile_report import setup, upload


@pytest.mark.parametrize('body,kind,expect_count,complete,requirement', [
    ('行业专业服务\n企业自述，现有能力介绍，交付经历待核实。\n具备药物研发能力，提供研发阶段的数据分析方案。', 'current_capability', 1, True, '有一个制药项目，需要懂药物研发的服务伙伴'),
    ('研发方向\n企业自述，处于规划阶段，尚未交付。\n计划打造药物研发平台。', 'planning_only', 0, True, '有一个制药项目，需要懂药物研发的服务伙伴'),
    ('企业自述\n已交付药物研发数据平台，项目完成验收。', 'delivered_project', 1, True, '有一个制药项目，需要懂药物研发的服务伙伴'),
    ('已为制药企业完成机房部署。', 'unrelated', 0, True, '有一个制药项目，需要懂药物研发的服务伙伴'),
    ('具备药物研发能力，暂无具体交付案例。', 'current_capability', 1, True, '必须有药物研发交付案例的服务伙伴'),
    ('已交付药物研发数据平台，项目完成验收；另一业务尚未实施。', 'delivered_project', 1, True, '必须有药物研发交付案例的服务伙伴'),
])
def test_complete_provider_payload_and_source_checked_policy(setup, monkeypatch, body, kind, expect_count, complete, requirement):
    upload(setup, 'synthetic-policy.txt', body)
    owner = make_user('policy-owner')
    requests=[]
    def completion(config, messages, schema):
        if schema['title'] == 'MatchUnderstanding':
            return json.dumps({'in_scope':True, 'facts':{'technicalNeeds':'药物研发'}, 'tag_suggestions':[]})
        assert schema['title'] == 'MatchAnswer'
        payload=completion_payload(model_config_from_record(config), messages, schema)
        requests.append(payload)
        data=json.loads(next(m['content'] for m in payload['messages'] if m['role']=='user'))
        assert data['requirement'] == requirement
        assert data['facts']['technicalNeeds']=='药物研发'
        assert 'understanding' not in data  # One full requirement plus grounded facts.
        assert partner_match_context.input_metrics(config,messages,schema)[0] <= partner_match_context.DETAIL_CHAR_LIMIT
        c=next(x for x in data['candidates'] if x['partnerId']==setup[3])
        assert 'inputCoverage' not in c and 'evidenceState' not in c
        p=next(p for p in c['profilePassages'] if body in p['text'] or any(word in p['text'] for word in ['药物研发','机房部署']))
        if '企业自述' in body:
            assert any('企业自述' in q['text'] for q in c['profilePassages'])
        if '规划阶段' in body:
            assert any('规划阶段' in q['text'] and '尚未交付' in q['text'] for q in c['profilePassages'])
        item={**recommendation(), 'partnerId':c['partnerId'], 'partnerName':c['name'],
              'recommendationReason':'直接项目证据：模型对所见原文作出语义判断。',
              'evidenceType':kind, 'profileEvidence':[{'source':p['source'],'quote':p['text']}],
              'evidenceCases':[], 'evidenceDeliverables':[]}
        return json.dumps({'recommendations':[item],
                           'supplyStatus':'sufficient','gapAnalysis':'未经校验的供给结论'},ensure_ascii=False)
    monkeypatch.setattr(development_model,'completion',completion)
    task=match.create_task(match.TaskCreateRequest(requestId=uuid4(),requirement=requirement),owner)
    match.executor.shutdown(wait=True)
    with get_db() as conn:
        saved=match_understanding.load(conn,task.recordId)
        record=dict(conn.execute('SELECT * FROM match_records WHERE id=?',(task.recordId,)).fetchone())
    assert record['task_status']=='ready' and len(requests)==1
    outcome=saved['outcome']
    assert len(outcome['recommendations'])==expect_count
    assert outcome['analysisComplete'] is complete
    assert json.loads(record['recommendations_json']) == outcome['recommendations']
    if kind=='current_capability' and expect_count:
        assert outcome['supplyStatus']=='sufficient'
        assert outcome['recommendations'][0]['recommendationReason']=='直接项目证据：模型对所见原文作出语义判断。'
    if kind=='delivered_project' and expect_count:
        assert outcome['supplyStatus']=='sufficient'
    if not complete:
        assert not outcome['analysisComplete'] and '本次分析不完整' not in outcome['answer']
    if kind=='planning_only':
        assert '未来规划线索' in outcome['answer']


def test_long_atomic_core_and_subject_survive_soft_partner_budget_stably(setup):
    body='药物研发交付情况\n集团口径，企业自述，待核实。\n已交付药物研发平台：'+'甲'*1100+'。'
    upload(setup,'synthetic-long-atomic.txt',body)
    with get_db() as conn:
        a=partner_match_context.detailed_candidate(conn,setup[3],'药物研发','需要药物研发伙伴',800)[1]
        b=partner_match_context.detailed_candidate(conn,setup[3],'药物研发','需要药物研发伙伴',800)[1]
    assert a==b and a['inputCoverage']['complete']
    assert body == ''.join(p['text'] for p in a['profilePassages'])
    assert sum(len(p['text']) for p in a['profilePassages'])>800


@pytest.mark.parametrize('failure',['failed','pending'])
def test_unused_unprocessed_sources_do_not_mark_input_incomplete(setup,failure):
    fid=upload(setup,'synthetic-incomplete.txt','完全无关的普通办公资料。')
    with get_db() as conn:
        conn.execute('UPDATE partner_profile_sources SET state=? WHERE partner_id=? AND source_id=?',(failure,setup[3],fid))
        assert partner_match_context.recall_candidates(conn,'需要药物研发伙伴',{})==[]
    result=match._validated_outcome([],{},False,[],requirement='需要药物研发伙伴',catalog_incomplete=True)
    assert result['analysisComplete'] and '本次分析不完整' not in result['answer']


def test_foreign_source_or_invented_quote_cannot_establish_current_capability(setup):
    upload(setup,'synthetic-owned.txt','具备药物研发能力。')
    with get_db() as conn:
        row=partner_match_context.detailed_candidate(conn,setup[3],'药物研发','需要药物研发伙伴')
    for ref in [{'source':'partner:foreign:profile:1','quote':'具备药物研发能力。'},
                {'source':row[1]['profilePassages'][0]['source'],'quote':'已交付药物研发项目且全部验收。'}]:
        item={**recommendation(),'partnerId':row[0]['id'],'partnerName':row[0]['name'],
              'evidenceType':'delivered_project','evidenceCases':[],'evidenceDeliverables':[],'profileEvidence':[ref]}
        recs=match._validated_recommendations([item],[row[0]],{row[0]['id']:[]},{row[0]['id']:[]})
        result=match._validated_outcome(recs,{'recommendations':[item],'supplyStatus':'sufficient'},False,[row],requirement='需要药物研发伙伴')
        assert result['recommendations']==[] and not result['analysisComplete']

def test_actual_payload_records_core_omission_when_global_budget_cannot_fit(setup,monkeypatch):
    body='集团口径，企业自述，待核实。\\n具备药物研发能力：'+'甲'*24000+'。'
    upload(setup,'synthetic-over-global.txt',body)
    owner=make_user('over-global-owner')
    seen=[]
    def complete(config,messages,schema):
        if schema['title']=='MatchUnderstanding':
            return json.dumps({'in_scope':True,'facts':{'technicalNeeds':'药物研发'}})
        payload=completion_payload(model_config_from_record(config),messages,schema)
        data=json.loads(next(m['content'] for m in payload['messages'] if m['role']=='user'))
        seen.append(data)
        assert partner_match_context.input_metrics(config,messages,schema)[0]<=partner_match_context.DETAIL_CHAR_LIMIT
        candidate=next(c for c in data['candidates'] if c['partnerId']==setup[3])
        assert 'inputCoverage' not in candidate and 'evidenceState' not in candidate
        assert not candidate['profilePassages']
        assert body not in json.dumps(payload,ensure_ascii=False)
        return json.dumps({'recommendations':[],'supplyStatus':'unknown','gapAnalysis':'上下文未覆盖'})
    monkeypatch.setattr(development_model,'completion',complete)
    task=match.create_task(match.TaskCreateRequest(requestId=uuid4(),requirement='需要药物研发伙伴'),owner)
    match.executor.shutdown(wait=True)
    with get_db() as conn:saved=match_understanding.load(conn,task.recordId)
    assert len(seen)==1 and not saved['outcome']['analysisComplete']
    coverage=saved['detail_input_coverage'][setup[3]]
    assert not coverage['complete'] and coverage['omittedHitGroups']>0
    assert '本次分析不完整' not in saved['outcome']['answer']
    assert saved['outcome']['gapAnalysis']=='上下文未覆盖'


def test_deliverable_only_reference_is_tied_to_owned_visible_case(setup):
    with get_db() as conn:partner=dict(conn.execute('SELECT * FROM partners WHERE id=?',(setup[3],)).fetchone())
    case={'id':'case-synthetic','partner_id':partner['id'],'title':'药物研发项目','description':'已交付药物研发数据平台，完成项目验收。'}
    file={'id':'file-synthetic','case_id':case['id'],'filename':'交付说明.txt','case_title':case['title']}
    item={**recommendation(),'partnerId':partner['id'],'partnerName':partner['name'],
          'evidenceType':'delivered_project','evidenceCases':[],'evidenceDeliverables':[file['id']]}
    recs=match._validated_recommendations([item],[partner],{partner['id']:[case]},{partner['id']:[file]})
    result=match._validated_outcome(recs,{'recommendations':[item],'supplyStatus':'sufficient'},False,
                                   [(partner,{},[case],[file])],requirement='需要药物研发伙伴')
    assert len(result['recommendations'])==1 and result['supplyStatus']=='sufficient'

@pytest.mark.parametrize('prefix,expected', [
    ('企业自述，处于规划阶段，尚未交付。\n', 'planning_only'),
    ('另一业务计划开发ScopeOther办公平台；', 'current_capability'),
    ('另一业务计划开发ScopeOther办公平台\n', 'current_capability'),
])
def test_quoted_fact_keeps_its_own_qualifier_but_not_another_fact_plan(setup,prefix,expected):
    requirement='需要ScopeQuasar能力'
    claim='具备ScopeQuasar能力。'
    body=prefix+claim
    upload(setup,'synthetic-qualifier-scope.txt',body)
    with get_db() as conn:
        row=partner_match_context.detailed_candidate(conn,setup[3],requirement,requirement)
    passage=next(p for p in row[1]['profilePassages'] if claim in p['text'])
    item={**recommendation(),'partnerId':setup[3],'partnerName':row[0]['name'],
          'evidenceType':expected,'profileEvidence':[{'source':passage['source'],'quote':claim}],
          'evidenceCases':[],'evidenceDeliverables':[]}
    assert match._source_assessment(item,row,requirement)==expected
    assert body == ''.join(p['text'] for p in row[1]['profilePassages'])

def test_other_fact_plan_after_comma_does_not_govern_quoted_current_fact(setup):
    requirement='需要ScopeQuasar能力'
    claim='具备ScopeQuasar能力'
    body=claim+'，另一业务计划开发ScopeOther办公平台。'
    upload(setup,'synthetic-comma-scope.txt',body)
    with get_db() as conn:row=partner_match_context.detailed_candidate(conn,setup[3],requirement,requirement)
    passage=next(p for p in row[1]['profilePassages'] if claim in p['text'])
    item={**recommendation(),'partnerId':setup[3],'partnerName':row[0]['name'],
          'evidenceType':'current_capability','profileEvidence':[{'source':passage['source'],'quote':claim}],
          'evidenceCases':[],'evidenceDeliverables':[]}
    assert match._source_assessment(item,row,requirement)=='current_capability'
    assert body == ''.join(p['text'] for p in row[1]['profilePassages'])


@pytest.mark.parametrize('body,expected,retained', [
    ('该能力处于规划阶段，尚未交付。\n具备ScopeQuasar能力。', 'planning_only', '该能力'),
    ('服务团队的这一项能力仍处于规划阶段，尚未交付。\n具备ScopeQuasar能力。', 'planning_only', '服务团队'),
    ('具备ScopeQuasar能力。\n这项能力处于规划阶段，尚未交付。', 'planning_only', '这项能力'),
    ('另一业务处于规划阶段，尚未交付。\n具备ScopeQuasar能力。', 'current_capability', None),
    ('具备ScopeQuasar能力。另一业务处于规划阶段，尚未交付。', 'current_capability', None),
    ('具备ScopeQuasar能力， 另一业务处于规划阶段，尚未交付。', 'current_capability', None),
    ('处于规划阶段，尚未交付。\n此外具备ScopeQuasar能力。', 'current_capability', None),
    ('处于规划阶段，尚未交付。\n\n具备ScopeQuasar能力。', 'current_capability', None),
])
def test_adjacent_qualifier_retention_respects_source_group_boundaries(body, expected, retained):
    claim = '具备ScopeQuasar能力'
    requirement = '需要ScopeQuasar能力'
    source = 'partner:scope-fixture:profile:0'
    partner = {'id': 'scope-fixture', 'name': '合成伙伴', 'capabilities': ''}
    row = (partner, {'profilePassages': [{'source': source, 'text': body}]}, [], [])
    item = {'evidenceType': expected,
            'profileEvidence': [{'source': source, 'quote': claim}],
            'evidenceCases': [], 'evidenceDeliverables': []}
    assert match._source_assessment(item, row, requirement) == expected
    # The legal layer preserves the model category and all supplied source text.
    assert not hasattr(match, '_fact_contexts')
    assert row[1]['profilePassages'][0]['text'] == body
