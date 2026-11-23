"""Certification priority, existing PG recall and saved facts; synthetic inputs only."""
import json
from uuid import uuid4
import pytest
from backend.business import matching
from backend.business.development import InvalidOutput
from backend.app import partner_match_context as context, match_understanding, development_model
from backend.app.database import get_db
from backend.app.routers import match
from .conftest import make_partner, make_user, make_task, auth_headers, recommendation
from .test_profile_report import setup, upload


def partner(pid, tags='', identities=None, name=None):
    make_partner(pid, name or pid)
    with get_db() as conn:
        conn.execute('UPDATE partners SET capabilities=?,identities=? WHERE id=?',
                     (tags,json.dumps(identities,ensure_ascii=False) if identities else None,pid))
    return pid


def facts(requirement='需要database迁移', work='database迁移', tag='数据库', conditions=()):
    result,_=matching.parse_understanding(json.dumps({'in_scope':True,'facts':{
        'capabilityTags':[tag] if tag else [],'capabilityEvidence':{tag:work} if tag else {},
        'workEvidence':[work] if work else [],'partnerRequirements':list(conditions)}},ensure_ascii=False),
        requirement,['数据库','容器'])
    return result['facts']


def condition(mode='required', identities=(), tags=(), match='all', quote='必须服务伙伴'):
    return {'mode':mode,'match':match,'identities':list(identities),'capabilityTags':list(tags),'evidenceText':quote}


def test_certified_union_happens_before_cut_and_overflow_uses_only_first_tier():
    # The certified partner has zero literal matches and a late stable ID.
    for i in range(14):partner(f'plain-{i:02}',name='database迁移合成团队'+str(i))
    partner('z-certified','数据库',name='合成专业团队')
    requirement='需要Oracle搬家'
    understood=facts(requirement,'Oracle搬家')
    # Literal distractors precede it under the old SQL-only cut.
    with get_db() as conn:
        conn.execute("UPDATE partners SET name='Oracle搬家' || id WHERE id LIKE 'plain-%'")
        selected=context.recall_candidates(conn,requirement,understood)
        assert selected[0]['partnerId']=='z-certified' and selected[0]['hits']==[]
        assert len(selected)==12
    for i in range(15):partner(f'cert-{i:02}','数据库',name='合成认证团队'+str(i))
    with get_db() as conn:
        # A work hit breaks ties within the certified tier, ahead of stable IDs.
        conn.execute("UPDATE partners SET name='Oracle搬家相关团队' WHERE id='cert-14'")
        selected=context.recall_candidates(conn,requirement,understood,limit=100)
    ids=[x['partnerId'] for x in selected]
    assert len(ids)==16 and ids[0]=='cert-14'
    assert ids[1:12]==[f'cert-{i:02}' for i in range(11)]
    assert ids[12:]==[f'plain-{i:02}' for i in range(4)]


def test_tiers_do_not_double_count_tags_or_fill_irrelevant_partners():
    partner('cert-empty','数据库')
    partner('cert-other','数据库',['云经销商'])
    partner('cert-service','数据库',['服务合作伙伴'])
    partner('service-explicit','',['服务合作伙伴'],name='database迁移')
    partner('service-inferred','容器',name='database迁移')
    partner('unrecorded','',name='database迁移')
    partner('unrelated','容器',name='合成无关')
    partner('region-only','',name='合成区域团队')
    with get_db() as conn:
        before=[dict(r) for r in conn.execute('SELECT id,capabilities,identities FROM partners ORDER BY id')]
        selected=context.recall_candidates(conn,'需要database迁移',facts())
        assert [x['partnerId'] for x in selected]==['cert-empty','cert-other','cert-service','service-explicit','service-inferred','unrecorded']
        assert before==[dict(r) for r in conn.execute('SELECT id,capabilities,identities FROM partners ORDER BY id')]
        assert context.recall_candidates(conn,'广东数据库迁移',facts('广东数据库迁移','数据库迁移',tag=''))==[x for x in context.recall_candidates(conn,'数据库迁移',facts('数据库迁移','数据库迁移',tag=''))]


def test_grounded_standard_mapping_changes_recall_but_free_words_do_not():
    partner('tag-only','数据库',name='合成甲')
    partner('invented','容器',name='Kubernetes')
    with get_db() as conn:
        assert context.recall_candidates(conn,'Oracle搬家',{})==[]
        understood=facts('Oracle搬家','Oracle搬家')
        selected=context.recall_candidates(conn,'Oracle搬家',understood)
        assert [x['partnerId'] for x in selected]==['tag-only']
        polluted={**understood,'technicalNeeds':'Kubernetes','projectKeywords':'Kubernetes','followUpQuestions':['要容器吗？'], 'capabilityTags':['数据库','容器']}
        assert context.recall_candidates(conn,'Oracle搬家',polluted)==selected
        assert [x['partnerId'] for x in context.recall_candidates(conn,'不需要数据库，只找容器部署',facts('不需要数据库，只找容器部署','容器部署','容器'))]==['invented']
    with pytest.raises(InvalidOutput):facts('Oracle搬家','虚构工作')


@pytest.mark.parametrize('change',['bad_quote','unknown_tag','unknown_identity'])
def test_structured_hard_conditions_cannot_silently_weaken(change):
    c=condition(identities=['服务合作伙伴'])
    if change=='bad_quote':c['evidenceText']='用户未提及的条件'
    if change=='unknown_tag':c['capabilityTags']=['虚构认证']
    if change=='unknown_identity':c['identities']=['其他身份']
    with pytest.raises(InvalidOutput):facts('必须服务伙伴','',tag='',conditions=[c])


@pytest.mark.parametrize('conditions,expected',[
    ([condition(tags=['数据库'],quote='必须数据库认证')],['cert']),
    ([condition(identities=['服务合作伙伴'])],['cert','service']),
    ([condition(identities=['云经销商'],quote='必须云经销商')],['dealer']),
    ([condition(identities=['软件合作伙伴','服务合作伙伴'],match='any',quote='软件伙伴或服务伙伴')],['cert','service','software']),
    ([condition(identities=['软件合作伙伴','服务合作伙伴'],match='all',quote='同时软件伙伴和服务伙伴')],[]),
    ([condition(mode='excluded',tags=['数据库'],quote='排除数据库认证')],['service','dealer','plain','software']),
    ([condition(mode='preferred',identities=['云经销商'],quote='优先云经销商')],['cert','service','dealer','plain','software']),
])
def test_explicit_required_preferred_excluded_and_or_conditions(conditions,expected):
    partner('cert','数据库',name='WorkTopic')
    partner('service','',['服务合作伙伴'],name='WorkTopic')
    partner('dealer','',['云经销商'],name='WorkTopic')
    partner('software','',['软件合作伙伴'],name='WorkTopic')
    partner('plain','',name='WorkTopic')
    requirement='WorkTopic；'+conditions[0]['evidenceText']
    understood=facts(requirement,'WorkTopic',conditions=conditions)
    with get_db() as conn:
        selected=context.recall_candidates(conn,requirement,understood)
    assert [x['partnerId'] for x in selected]==expected


def test_identity_only_uses_actual_field_and_tag_inference_without_topic_claim():
    partner('cert','数据库')
    partner('service','',['服务合作伙伴'])
    partner('plain')
    c=condition(identities=['服务合作伙伴'])
    with get_db() as conn:
        selected=context.recall_candidates(conn,'必须服务伙伴',facts('必须服务伙伴','',tag='',conditions=[c]))
    assert [x['partnerId'] for x in selected]==['cert','service']
    assert all(x['hits']==[] and not x['recallTerms'] for x in selected)


def test_tag_only_detail_and_saved_snapshot_are_program_owned_and_legacy_is_not_backfilled(client,monkeypatch):
    partner('cert','数据库',['云经销商'])
    owner=make_user('cert-snapshot-owner')
    calls=[]
    def complete(config,messages,schema):
        calls.append(schema['title'])
        if schema['title']=='MatchUnderstanding':
            return json.dumps({'in_scope':True,'facts':facts('需要Oracle搬家','Oracle搬家')})
        data=json.loads(messages[-1]['content']);candidate=data['candidates'][0]
        assert len(data['candidates'])==1 and candidate['partnerId']=='cert'
        assert candidate['profilePassages']==[] and candidate['certification']=={
            'capabilityTags':['数据库'],'relatedCapabilityTags':['数据库'],
            'subCapabilityTags':[],'relatedSubCapabilityTags':[],
            'servicePartnerBasis':'capability_tag','identities':['云经销商']}
        assert context.input_metrics(config,messages,schema)[0]<=context.DETAIL_CHAR_LIMIT
        assert not any(k.startswith('_') for k in candidate)
        return json.dumps({'recommendations':[{**recommendation('cert','cert'),
            'evidenceCases':[],'evidenceDeliverables':[],'profileEvidence':[],
            'recommendationReason':'正式数据库认证支持接洽，未提供同类迁移项目资料。',
            'certification':{'capabilityTags':['虚构认证']}}],
            'analysisRefs':[],'gapAnalysis':'按专项认证接洽。','supplyStatus':'partial'},ensure_ascii=False)
    with get_db() as conn:
        conn.execute("UPDATE model_providers SET api_key_source='db',api_key='synthetic-only'")
    monkeypatch.setattr(development_model,'completion',complete)
    accepted=match.create_task(match.TaskCreateRequest(requestId=uuid4(),requirement='需要Oracle搬家'),owner)
    match.executor.shutdown(wait=True)
    with get_db() as conn:
        row=dict(conn.execute('SELECT * FROM match_records WHERE id=?',(accepted.recordId,)).fetchone())
        saved=match_understanding.load(conn,accepted.recordId)
        assert row['task_status']=='ready',saved
        snapshot=json.loads(row['recommendations_json'])[0]['certification']
        assert snapshot['relatedCapabilityTags']==['数据库'] and '虚构' not in str(snapshot)
        assert saved['detail_rows'][0][0]['identities']==json.dumps(['云经销商'],ensure_ascii=False)
        conn.execute("UPDATE partners SET capabilities='容器',identities=NULL WHERE id='cert'")
    assert calls==['MatchUnderstanding','MatchAnswer']
    response=client.get('/agent/tasks/'+accepted.recordId,headers=auth_headers(owner))
    assert response.status_code==200 and response.json()['recommendations'][0]['certification']==snapshot
    legacy=make_task(owner,'旧任务',recommendations=[recommendation('cert','cert')])
    assert client.get('/agent/tasks/'+legacy,headers=auth_headers(owner)).json()['recommendations'][0]['certification'] is None
    other=make_user('other-owner')
    assert client.get('/agent/tasks/'+accepted.recordId,headers=auth_headers(other)).status_code==404


@pytest.mark.parametrize('field,value',[('capabilities','容器'),('identities','["云经销商"]')])
def test_certification_and_identity_changes_invalidate_existing_dependency_check(field,value):
    partner('cert','数据库')
    with get_db() as conn:
        row=context.detailed_candidate(conn,'cert','相关认证','需要Oracle搬家',facts=facts('需要Oracle搬家','Oracle搬家'),hits=[])
        raw={'partnerId':'cert','profileEvidence':[],'evidenceCases':[],'evidenceDeliverables':[]}
        stamp=match._candidate_stamp(conn)
        assert match._current_reference_valid(conn,raw,row)
        conn.execute('UPDATE partners SET '+field+'=? WHERE id=?',(value,'cert'))
        assert stamp!=match._candidate_stamp(conn)
        assert not match._current_reference_valid(conn,raw,row)


def test_final_scores_can_reorder_tiers_but_delivered_claim_needs_sent_reference():
    partner('cert','数据库')
    partner('service','',['服务合作伙伴'],name='database迁移')
    with get_db() as conn:
        rows=[context.detailed_candidate(conn,pid,'项目适配','需要database迁移',facts=facts()) for pid in ['cert','service']]
    raw=[{**recommendation(r[0]['id'],r[0]['name']),'matchScore':score,'evidenceCases':[],'evidenceDeliverables':[],'profileEvidence':[]} for r,score in zip(rows,['80','95'])]
    recs=match._validated_recommendations(raw,[r[0] for r in rows],{}, {},certifications={r[0]['id']:r[1]['certification'] for r in rows})
    assert [r.partnerId for r in recs]==['service','cert']
    assert match._source_assessment({**raw[0],'evidenceType':'delivered_project'},rows[0]) is None
    assert match._source_assessment({**raw[0],'evidenceType':'current_capability'},rows[0])=='current_capability'


def test_no_candidates_skips_detail_and_does_not_pad(monkeypatch):
    owner=make_user('empty-certified-owner')
    calls=[]
    def complete(config,messages,schema):
        calls.append(schema['title']);assert schema['title']=='MatchUnderstanding'
        return json.dumps({'in_scope':True,'facts':facts('需要Oracle搬家','Oracle搬家')})
    with get_db() as conn:conn.execute("UPDATE model_providers SET api_key_source='db',api_key='synthetic-only'")
    monkeypatch.setattr(development_model,'completion',complete)
    accepted=match.create_task(match.TaskCreateRequest(requestId=uuid4(),requirement='需要Oracle搬家'),owner)
    match.executor.shutdown(wait=True)
    with get_db() as conn:
        row=dict(conn.execute('SELECT * FROM match_records WHERE id=?',(accepted.recordId,)).fetchone())
    assert calls==['MatchUnderstanding'] and row['task_status']=='ready'
    assert json.loads(row['recommendations_json'])==[]


def test_change_between_recall_and_detail_stops_before_second_call(monkeypatch):
    partner('cert','数据库')
    owner=make_user('changed-recall-owner')
    task=make_task(owner,'需要Oracle搬家',task_status='matching',recommendations=[])
    snapshot={'_task_id':task,'understanding':{'facts':facts('需要Oracle搬家','Oracle搬家')}}
    original=context.recall_candidates
    def changed(conn,*args,**kwargs):
        selected=original(conn,*args,**kwargs)
        with get_db() as writer:writer.execute("UPDATE partners SET capabilities='容器' WHERE id='cert'")
        return selected
    monkeypatch.setattr(context,'recall_candidates',changed)
    def unexpected(*args):pytest.fail('Changed certification must stop before model detail')
    monkeypatch.setattr(development_model,'completion',unexpected)
    from backend.app.task_failures import PublicTaskError
    with pytest.raises(PublicTaskError):match._perform_partner_match('需要Oracle搬家',snapshot)


def test_api_accepted_ideographic_comma_tags_recall_each_certification(client):
    admin=auth_headers(make_user('p2-tag-admin',role='admin'))
    response=client.post('/partners',headers=admin,json={'name':'合成多认证伙伴','capabilities':'数据库、容器'})
    assert response.status_code==201 and response.json()['capabilities']=='数据库、容器'
    pid=response.json()['id']
    partner('p2-unqualified','容器',name='数据库工作')
    requirement='数据库工作，必须数据库认证'
    understood=facts(requirement,'数据库工作',conditions=[condition(tags=['数据库'],quote='必须数据库认证')])
    with get_db() as conn:
        selected=context.recall_candidates(conn,requirement,understood)
        assert [item['partnerId'] for item in selected]==[pid]
        row=context.detailed_candidate(conn,pid,'数据库认证',requirement,facts=understood,hits=selected[0]['hits'])
        assert row[1]['certification']==selected[0]['certification']
        assert row[1]['certification']['capabilityTags']==['数据库','容器']
        assert row[1]['certification']['relatedCapabilityTags']==['数据库']
        assert conn.execute('SELECT capabilities FROM partners WHERE id=?',(pid,)).fetchone()[0]=='数据库、容器'


def test_required_certification_without_work_or_mapping_reaches_detail_and_saves(monkeypatch):
    partner('p2-db-certified','数据库')
    partner('p2-other-certified','容器')
    partner('p2-service-only','',['服务合作伙伴'])
    requirement='必须具备数据库认证'
    understood=facts(requirement,'',tag='',conditions=[condition(tags=['数据库'],quote=requirement)])
    assert understood['workEvidence']==[] and understood['capabilityTags']==[] and understood['capabilityEvidence']=={}
    owner=make_user('p2-required-cert-owner');calls=[]
    def complete(config,messages,schema):
        calls.append(schema['title'])
        if schema['title']=='MatchUnderstanding':return json.dumps({'in_scope':True,'facts':understood})
        data=json.loads(messages[-1]['content'])
        assert [c['partnerId'] for c in data['candidates']]==['p2-db-certified']
        assert data['candidates'][0]['certification']['relatedCapabilityTags']==['数据库']
        return json.dumps({'recommendations':[{**recommendation('p2-db-certified','p2-db-certified'),
            'recommendationReason':'已记录正式数据库认证，符合本次明确认证要求。',
            'profileEvidence':[],'evidenceCases':[],'evidenceDeliverables':[]}],
            'supplyStatus':'partial','gapAnalysis':'依据已维护的正式认证接洽。','analysisRefs':[]},ensure_ascii=False)
    with get_db() as conn:conn.execute("UPDATE model_providers SET api_key_source='db',api_key='synthetic-only'")
    monkeypatch.setattr(development_model,'completion',complete)
    accepted=match.create_task(match.TaskCreateRequest(requestId=uuid4(),requirement=requirement),owner)
    match.executor.shutdown(wait=True)
    assert calls==['MatchUnderstanding','MatchAnswer']
    with get_db() as conn:
        record=dict(conn.execute('SELECT * FROM match_records WHERE id=?',(accepted.recordId,)).fetchone())
        saved=match_understanding.load(conn,accepted.recordId)
    assert record['task_status']=='ready'
    recs=json.loads(record['recommendations_json'])
    assert [r['partnerId'] for r in recs]==['p2-db-certified']
    assert recs[0]['certification']['relatedCapabilityTags']==['数据库']
    assert saved['initial_selection']['candidates'][0]['hits']==[]


@pytest.mark.parametrize('operator,cert_count',[('any',1),('all',1),('any',13)])
def test_no_work_certification_or_identity_preserves_both_branches_and_priority(operator,cert_count):
    # Service ID sorts first, so certification order must come from the tier.
    partner('00-service-only','',['服务合作伙伴'])
    partner('unqualified','')
    certified=[f'z-cert-{i:02}' for i in range(cert_count)]
    for pid in certified:partner(pid,'数据库')
    requirement='必须具备数据库认证'+('或' if operator=='any' else '并且具备')+'服务伙伴身份'
    understood=facts(requirement,'',tag='',conditions=[condition(tags=['数据库'],identities=['服务合作伙伴'],match=operator,quote=requirement)])
    with get_db() as conn:
        before=[dict(r) for r in conn.execute('SELECT id,capabilities,identities FROM partners ORDER BY id')]
        selected=context.recall_candidates(conn,requirement,understood)
        expected=certified[:12]+(['00-service-only'] if operator=='any' and cert_count<12 else [])
        assert [item['partnerId'] for item in selected]==expected
        assert all(not item['recallTerms'] and not item['hits'] for item in selected)
        for item in selected:
            row=context.detailed_candidate(conn,item['partnerId'],'明确认证或身份要求',requirement,facts=understood,hits=item['hits'])
            assert row[1]['certification']==item['certification']
        assert before==[dict(r) for r in conn.execute('SELECT id,capabilities,identities FROM partners ORDER BY id')]


@pytest.mark.parametrize('joined',[False,True])
def test_condition_quote_stays_contiguous_without_business_content_retry(monkeypatch,joined):
    requirement='需要数据库和容器工作。允许分工。优先相关认证。'
    quote='优先相关认证；允许分工。' if joined else '优先相关认证'
    raw=json.dumps({'in_scope':True,'facts':{'capabilityTags':['数据库','容器'],
        'capabilityEvidence':{'数据库':'数据库','容器':'容器'},'workEvidence':['数据库和容器工作'],
        'partnerRequirements':[condition(mode='preferred',match='any',tags=['数据库','容器'],quote=quote)]}},ensure_ascii=False)
    calls=[]
    def complete(config,messages,schema):
        calls.append(1)
        assert json.loads(messages[-1]['content'])['requirement']==requirement
        return raw
    monkeypatch.setattr(development_model,'completion',complete)
    from backend.business.matching_types import MatchUnderstanding
    parse=lambda value:matching.parse_understanding(value,requirement,['数据库','容器'])
    def run():return development_model.validated_completion({'_match_request':True},matching.understanding_messages(requirement,['数据库','容器'],''),MatchUnderstanding.model_json_schema(),parse)
    if joined:
        with pytest.raises(InvalidOutput):run()
    else:
        result,_=run();assert result['facts']['partnerRequirements'][0]['evidenceText']==quote
    assert calls==[1]


@pytest.mark.parametrize('mode,evidence_variant',[('preferred','missing'),('preferred','invalid'),('excluded','missing')])
def test_grounded_preferred_or_tags_recall_all_alternatives_without_becoming_mandatory(mode,evidence_variant):
    partner('pref-a','数据库')
    partner('pref-b','容器')
    partner('pref-c','',['服务合作伙伴'],name='WorkTopic')
    phrase='优先数据库或容器认证' if mode=='preferred' else '排除同时具备数据库和容器认证'
    requirement='WorkTopic，'+phrase+'。'
    mapped=['数据库'] if mode=='preferred' else []
    quotes={'数据库':'数据库'} if mapped else {}
    if evidence_variant=='invalid':quotes['容器']='容器和数据库'
    raw={'in_scope':True,'facts':{'capabilityTags':['数据库','容器'] if mapped else [],
        'capabilityEvidence':quotes,'workEvidence':['WorkTopic'],
        'partnerRequirements':[condition(mode=mode,match='any' if mode=='preferred' else 'all',tags=['数据库','容器'],quote=phrase)]}}
    understood,_=matching.parse_understanding(json.dumps(raw,ensure_ascii=False),requirement,['数据库','容器'])
    facts=understood['facts']
    assert '容器' not in facts['capabilityEvidence']
    with get_db() as conn:
        selected=context.recall_candidates(conn,requirement,facts)
        assert [item['partnerId'] for item in selected]==(['pref-a','pref-b','pref-c'] if mode=='preferred' else ['pref-c'])
        if mode=='preferred':
            item=selected[1]
            assert item['certification']['relatedCapabilityTags']==['容器']
            row=context.detailed_candidate(conn,item['partnerId'],'明确优先认证',requirement,facts=facts,hits=item['hits'])
            assert row[1]['certification']==item['certification']


def test_required_service_can_use_formal_certification_without_manual_identity(monkeypatch):
    partner('service-from-cert','数据库')
    requirement='需要服务合作伙伴，优先数据库认证。'
    understood=facts(requirement,'',conditions=[condition(identities=['服务合作伙伴'],quote='需要服务合作伙伴'),condition(mode='preferred',tags=['数据库'],quote='优先数据库认证')])
    owner=make_user('derived-service-owner');calls=[]
    def complete(config,messages,schema):
        calls.append(schema['title'])
        if schema['title']=='MatchUnderstanding':return json.dumps({'in_scope':True,'facts':understood})
        data=json.loads(messages[-1]['content']);assert data['requirement']==requirement
        assert [c['partnerId'] for c in data['candidates']]==['service-from-cert']
        certification=data['candidates'][0]['certification']
        assert certification['identities']==[] and certification['servicePartnerBasis']=='capability_tag'
        assert certification['relatedCapabilityTags']==['数据库']
        return json.dumps({'recommendations':[{**recommendation('service-from-cert','service-from-cert'),
            'recommendationReason':'正式能力标签确认其为服务伙伴，可接洽数据库工作；手工身份字段尚未维护。',
            'profileEvidence':[],'evidenceCases':[],'evidenceDeliverables':[]}],
            'analysisRefs':[],'supplyStatus':'partial','gapAnalysis':'依据正式认证接洽，未认定已有同类交付项目。'},ensure_ascii=False)
    with get_db() as conn:conn.execute("UPDATE model_providers SET api_key_source='db',api_key='synthetic-only'")
    monkeypatch.setattr(development_model,'completion',complete)
    accepted=match.create_task(match.TaskCreateRequest(requestId=uuid4(),requirement=requirement),owner)
    match.executor.shutdown(wait=True)
    assert calls==['MatchUnderstanding','MatchAnswer']
    with get_db() as conn:
        record=conn.execute('SELECT * FROM match_records WHERE id=?',(accepted.recordId,)).fetchone()
        assert record['task_status']=='ready'
        rec=json.loads(record['recommendations_json'])[0]
        assert rec['certification']['identities']==[] and rec['certification']['servicePartnerBasis']=='capability_tag'
        assert conn.execute("SELECT identities FROM partners WHERE id='service-from-cert'").fetchone()[0] is None


def test_elastic_recall_adds_four_lexical_candidates_only_when_no_required_gate_and_tier0_exceeds_8():
    from backend.business.matching_types import MatchAnswer
    from backend.app.capability_hierarchy import l1_l2_hierarchy_map

    for i in range(8):
        partner(f'tier0-{i:02}', '数据库', name=f'持证伙伴{i:02}')
    partner('zero-hit-plain', '', name='无关公司')
    partner('tier1-low', '', ['服务合作伙伴'], name='Oracle伙伴')
    for i in range(4):
        partner(f'tier2-high-{i:02}', '', name='Oracle搬家微服务改造部署交付专家')

    requirement = '需要Oracle搬家与微服务改造部署交付'
    understood = facts(requirement, 'Oracle搬家与微服务改造部署交付')

    # len(tier0) == 8 -> standard 12 cap (8 tier0 + 4 highest-score non-tier0).
    with get_db() as conn:
        selected8 = context.recall_candidates(conn, requirement, understood)
    assert len(selected8) == 12

    # len(tier0) == 9 (> 8, no required gate) -> 9 tier0 + 4 highest-score non-tier0 = 13, and high-score Tier 2 beats lower-score Tier 1.
    partner('tier0-08', '数据库', name='持证伙伴08')
    with get_db() as conn:
        selected9 = context.recall_candidates(conn, requirement, understood)
    ids9 = [item['partnerId'] for item in selected9]
    assert len(ids9) == 13
    assert ids9[:9] == [f'tier0-{i:02}' for i in range(9)]
    assert ids9[9:] == [f'tier2-high-{i:02}' for i in range(4)]
    assert 'zero-hit-plain' not in ids9 and 'tier1-low' not in ids9

    # Preferred non-tier0 partner with lower lexical hit ranks first inside the 4 extra slots.
    partner('tier2-pref-dealer', '', ['云经销商'], name='Oracle伙伴')
    pref_req = requirement + '，优先云经销商'
    pref_facts = facts(
        pref_req,
        'Oracle搬家与微服务改造部署交付',
        conditions=[condition(mode='preferred', identities=['云经销商'], quote='优先云经销商')],
    )
    with get_db() as conn:
        selected_pref = context.recall_candidates(conn, pref_req, pref_facts)
        ids_pref = [item['partnerId'] for item in selected_pref]
        assert len(ids_pref) == 13
        assert ids_pref[9] == 'tier2-pref-dealer'
        assert ids_pref[10:] == [f'tier2-high-{i:02}' for i in range(3)]
        conn.execute("DELETE FROM partners WHERE id='tier2-pref-dealer'")

    # Add 5 more certified partners (total tier0 == 14):
    # Without required gate -> 12 tier0 + 4 non-tier0 = 16, and Stage 2 production _detail_content trims excess case payload <= 50,000 chars while giving every extra candidate case evidence.
    for i in range(9, 14):
        partner(f'tier0-{i:02}', '数据库', name=f'持证伙伴{i:02}')
    with get_db() as conn:
        selected14 = context.recall_candidates(conn, requirement, understood)
        assert len(selected14) == 16
        for item in selected14:
            pid = item['partnerId']
            conn.execute(
                "INSERT INTO cases (id, partner_id, category_id, visible, title, description, created_at) VALUES (?, ?, 'technical-1', 1, ?, ?, '2026-11-22T00:00:00Z')",
                (f'c1-{pid}', pid, f'{pid}主案例', 'Oracle搬家微服务交付实例。' + '案例正文' * 25),
            )
            conn.execute(
                "INSERT INTO cases (id, partner_id, category_id, visible, title, description, created_at) VALUES (?, ?, 'technical-1', 1, ?, ?, '2026-11-22T00:00:00Z')",
                (f'c2-{pid}', pid, f'{pid}扩展超长案例', '扩展补充说明：' + '详尽项目细节与验收记录。' * 280),
            )
        rows = [
            context.detailed_candidate(conn, item['partnerId'], item['verificationFocus'], requirement, facts=understood, hits=item['hits'])
            for item in selected14
        ]
        cfg = {'api_key': 'offline-only', 'base_url': 'http://127.0.0.1:1/v1', 'model_name': 'synthetic',
               'max_tokens': 4096, 'context_window_tokens': 1048576, 'temperature': 0.2, 'top_p': 1}
        schema = MatchAnswer.model_json_schema()
        snapshot_stub = {'understanding': {'facts': understood}}
        build = lambda items: match._detail_content(requirement, snapshot_stub, items)
        context.assemble_details(rows, cfg, build, schema)
        chars, _ = context.input_metrics(cfg, matching.detail_messages(build(rows)), schema)
        assert chars <= context.DETAIL_CHAR_LIMIT
        assert all(len(r[1]['visibleCases']) >= 1 for r in rows[12:])
        assert any(len(r[1]['visibleCases']) < 2 for r in rows)

        # With explicit required gate -> strictly 12 certified partners only.
        req_with_gate = requirement + '，必须具备数据库认证'
        gated = facts(req_with_gate, 'Oracle搬家与微服务改造部署交付', conditions=[condition(tags=['数据库'], quote='必须具备数据库认证')])
        selected_gated = context.recall_candidates(conn, req_with_gate, gated)
        assert len(selected_gated) == 12
        assert all(item['partnerId'].startswith('tier0-') for item in selected_gated)

        # When tier0 > 8 but zero non-tier0 partners match lexical terms -> do NOT pad zero-hit partners.
        conn.execute("UPDATE partners SET name='无关联文本' WHERE id='tier1-low' OR id LIKE 'tier2-high-%'")
        selected_no_lex = context.recall_candidates(conn, requirement, understood)
        assert len(selected_no_lex) == 12
        assert 'zero-hit-plain' not in [item['partnerId'] for item in selected_no_lex]


def test_synonymous_l1_tags_expand_symmetrically_only_for_generic_queries():
    from backend.app.capability_hierarchy import l1_l2_hierarchy_map

    partner('p-bd', '大数据', name='大数据专精伙伴')
    partner('p-dm', '数据管理分析与流通', name='数据治理专精伙伴')
    partner('p-unrelated', '安全', name='安全伙伴')

    generic_req = '希望寻找具备学习分析和数据分析能力的合作伙伴'
    tags = ['大数据', '数据管理分析与流通']
    with get_db() as conn:
        _, hierarchy = l1_l2_hierarchy_map(conn)

    u_bd, _ = matching.parse_understanding(
        json.dumps({'in_scope': True, 'facts': {
            'capabilityTags': ['大数据'], 'capabilityEvidence': {'大数据': '学习分析和数据分析'},
            'workEvidence': ['学习分析和数据分析'], 'partnerRequirements': [],
        }}, ensure_ascii=False),
        generic_req, tags, hierarchy=hierarchy,
    )
    u_dm, _ = matching.parse_understanding(
        json.dumps({'in_scope': True, 'facts': {
            'capabilityTags': ['数据管理分析与流通'], 'capabilityEvidence': {'数据管理分析与流通': '学习分析和数据分析'},
            'workEvidence': ['学习分析和数据分析'], 'partnerRequirements': [],
        }}, ensure_ascii=False),
        generic_req, tags, hierarchy=hierarchy,
    )
    with get_db() as conn:
        rec_bd = context.recall_candidates(conn, generic_req, u_bd['facts'])
        rec_dm = context.recall_candidates(conn, generic_req, u_dm['facts'])

    assert [item['partnerId'] for item in rec_bd] == ['p-dm', 'p-bd']
    assert rec_bd == rec_dm
    assert {item['partnerId']: item['certification']['relatedCapabilityTags'] for item in rec_bd} == {
        'p-dm': ['数据管理分析与流通'],
        'p-bd': ['大数据'],
    }

    # Literal L1 name, explicit L2 child, or partnerRequirements constraint must NOT expand to the sibling.
    literal_req = '需要大数据平台能力'
    u_lit, _ = matching.parse_understanding(
        json.dumps({'in_scope': True, 'facts': {
            'capabilityTags': ['大数据'], 'capabilityEvidence': {'大数据': '大数据平台能力'},
            'workEvidence': ['大数据平台能力'], 'partnerRequirements': [],
        }}, ensure_ascii=False),
        literal_req, tags, hierarchy=hierarchy,
    )
    l2_req = '需要分布式批量计算能力'
    u_l2, _ = matching.parse_understanding(
        json.dumps({'in_scope': True, 'facts': {
            'capabilityTags': ['大数据'], 'capabilityEvidence': {'大数据': '分布式批量计算能力'},
            'subCapabilityTags': [{'parent': '大数据', 'name': '大数据开发支持能力'}],
            'subCapabilityEvidence': {'大数据/大数据开发支持能力': '分布式批量计算能力'},
            'workEvidence': ['分布式批量计算能力'], 'partnerRequirements': [],
        }}, ensure_ascii=False),
        l2_req, tags, hierarchy=hierarchy,
    )
    cond_req = '希望具备数据分析能力，必须具备正式大数据认证'
    u_cond, _ = matching.parse_understanding(
        json.dumps({'in_scope': True, 'facts': {
            'capabilityTags': ['大数据'], 'capabilityEvidence': {'大数据': '数据分析能力'},
            'workEvidence': ['数据分析能力'],
            'partnerRequirements': [{'mode': 'required', 'match': 'all', 'capabilityTags': ['大数据'], 'evidenceText': '必须具备正式大数据认证'}],
        }}, ensure_ascii=False),
        cond_req, tags, hierarchy=hierarchy,
    )
    with get_db() as conn:
        lit_res = context.recall_candidates(conn, literal_req, u_lit['facts'])
        assert lit_res[0]['partnerId'] == 'p-bd'
        assert lit_res[0]['certification']['relatedCapabilityTags'] == ['大数据']
        assert all(i['certification']['relatedCapabilityTags'] == [] for i in lit_res if i['partnerId'] == 'p-dm')
        assert [i['partnerId'] for i in context.recall_candidates(conn, l2_req, u_l2['facts'])] == ['p-bd']
        assert [i['partnerId'] for i in context.recall_candidates(conn, cond_req, u_cond['facts'])] == ['p-bd']


def test_recall_query_merges_grounded_capability_evidence_without_polluting_empty_work():
    requirement = '需要在线教学、学习分析与容器云运维，不要硬件采购。'
    facts_partial = {
        'workEvidence': ['在线教学'],
        'capabilityTags': ['大数据', '容器'],
        'capabilityEvidence': {'大数据': '学习分析', '安全': '硬件采购', '未选': '虚构片段'},
        'subCapabilityTags': [{'parent': '容器', 'name': '容器（云原生）运维'}],
        'subCapabilityEvidence': {'容器/容器（云原生）运维': '容器云运维'},
    }
    terms_partial, _ = matching.recall_query(requirement, facts_partial)
    assert {'教学', '学习', '分析', '运维'} <= set(terms_partial)
    assert '硬件' not in terms_partial and '采购' not in terms_partial and '虚构' not in terms_partial

    assert matching.recall_query(requirement, {
        'workEvidence': [],
        'capabilityTags': ['大数据'],
        'capabilityEvidence': {'大数据': '学习分析'},
    }) == ([], [])


def test_per_candidate_soft_cap_limits_extra_passages_without_dropping_primary_fact():
    from backend.tests.test_matching_v3 import raw_row, assemble

    # 1. Small candidate set (2 partners, 10x1000-char passages each = 20,000 total < 50,000):
    # each partner is capped at <= 4,000 chars rather than consuming ~20,000 chars.
    rows2 = [
        raw_row({'id': f'p-{i}', 'name': f'长文伙伴{i}'}, [f'片段{k}-' + ('实' * 996) for k in range(10)])
        for i in range(2)
    ]
    _, chars2, _ = assemble(rows2)
    assert chars2 <= context.DETAIL_CHAR_LIMIT
    for r in rows2:
        total_len = sum(len(p['text']) for p in r[1]['profilePassages'])
        assert total_len == 4000
        assert any(o['reason'] == 'selection_budget' for o in r[1]['inputCoverage']['omissions'])

    # 2. A candidate whose first primary passage exceeds 4,000 chars STILL receives it (never empty),
    # and rejects any additional passage past the soft cap.
    row_big = raw_row({'id': 'big-primary', 'name': '超长首段伙伴'}, ['主依据：' + ('首' * 5000), '次依据：' + ('次' * 500)])
    _, chars_big, _ = assemble([row_big])
    assert chars_big <= context.DETAIL_CHAR_LIMIT
    assert len(row_big[1]['profilePassages']) == 1
    assert row_big[1]['profilePassages'][0]['text'].startswith('主依据：')
    assert any(o['reason'] == 'selection_budget' for o in row_big[1]['inputCoverage']['omissions'])

    # 3. 16 candidates each with 3x600-char passages (28,800 chars + fixed shell <= 50,000):
    # all 16 candidates (including the 4 extra non-tier0 slots) receive their ~1,800-char evidence cleanly.
    rows16 = [
        raw_row({'id': f's16-{i:02}', 'name': f'伙伴{i:02}'}, [f'正文{k}-' + ('案' * 595) for k in range(3)])
        for i in range(16)
    ]
    _, chars16, _ = assemble(rows16)
    assert 25000 < chars16 <= context.DETAIL_CHAR_LIMIT
    assert all(len(r[1]['profilePassages']) == 3 for r in rows16)


def test_assemble_details_case_soft_cap_primary_completeness_and_deliverable_rotation(monkeypatch):
    from backend.tests.test_matching_v3 import raw_row, assemble

    # 1. Pure same-source matched case (case:c1) keeps complete=True and clears evidenceState.
    primary_row = raw_row({'id': 'primary-case-p', 'name': '主案例伙伴'}, ['主片段' + ('甲' * 1997)])
    first_key = primary_row[1]['_groups'][0]['sources'][0]
    primary_row[1]['_sourceMap'][first_key]['sourceRef'] = 'case:c1'
    primary_row[2].append({'id': 'c1', 'title': '主案例', 'description': '主' * 2497})
    assemble([primary_row])
    assert [c['id'] for c in primary_row[1]['visibleCases']] == ['c1']
    assert primary_row[1]['profilePassages'] == []
    assert primary_row[1]['inputCoverage']['complete'] is True
    assert primary_row[1]['evidenceState'] == ''
    assert not any(
        o['reason'] == 'primary_evidence_budget'
        for o in primary_row[1]['inputCoverage']['omissions']
    )

    # 1b. Rank-0 independent document wins Turn-1 over lower-priority matched case (c-low).
    doc_first_row = raw_row(
        {'id': 'doc-first-p', 'name': '文档优先伙伴'},
        ['支持本地部署' + ('文' * 1994), '容器部署案例' + ('案' * 2495)],
    )
    second_key = doc_first_row[1]['_groups'][1]['sources'][0]
    doc_first_row[1]['_sourceMap'][second_key]['sourceRef'] = 'case:c-low'
    doc_first_row[2].append({'id': 'c-low', 'title': '容器部署案例', 'description': '案' * 2495})
    assemble([doc_first_row])
    assert len(doc_first_row[1]['profilePassages']) == 1
    assert doc_first_row[1]['profilePassages'][0]['text'].startswith('支持本地部署')
    assert doc_first_row[1]['visibleCases'] == []
    assert doc_first_row[1]['inputCoverage']['complete'] is True
    assert doc_first_row[1]['evidenceState'] == ''

    # 1c. Rank-0 matched case sent on Turn-1 does NOT mask omitted independent document hit groups.
    case_first_row = raw_row(
        {'id': 'case-first-p', 'name': '案例优先伙伴'},
        ['主案例摘录' + ('案' * 2495), '独立文档依据' + ('文' * 1994)],
    )
    top_case_key = case_first_row[1]['_groups'][0]['sources'][0]
    case_first_row[1]['_sourceMap'][top_case_key]['sourceRef'] = 'case:c-top'
    case_first_row[2].append({'id': 'c-top', 'title': '主案例', 'description': '案' * 2497})
    assemble([case_first_row])
    assert [c['id'] for c in case_first_row[1]['visibleCases']] == ['c-top']
    assert case_first_row[1]['profilePassages'] == []
    assert case_first_row[1]['inputCoverage']['complete'] is False
    assert any(
        o['reason'] == 'primary_evidence_budget' and o['hitIndexes'] == [1]
        for o in case_first_row[1]['inputCoverage']['omissions']
    )
    assert case_first_row[1]['evidenceState'] == '主要命中原文因本次额度未能送达。'

    # 2. Unmatched secondary visibleCase without prior passages still obeys CANDIDATE_EVIDENCE_CHAR_LIMIT.
    unmatched_row = raw_row({'id': 'sec-only-p', 'name': '纯超限案例伙伴'}, [])
    unmatched_row[2].append({'id': 'sec-oversized', 'title': '纯超限案例', 'description': '案' * 4500})
    assemble([unmatched_row])
    assert unmatched_row[1]['visibleCases'] == []
    assert any(
        o['reason'] == 'case_selection_budget' and o['caseId'] == 'sec-oversized'
        for o in unmatched_row[1]['inputCoverage']['omissions']
    )

    # 3. Skipped cases' deliverables do not consume rotation turns before peer candidates.
    def _fair_rows(files_pa, files_pb):
        row_a = raw_row({'id': 'pa', 'name': '甲伙伴'}, ['甲主段落' + ('甲' * 496)])
        row_a[2].extend([
            {'id': 'ca1', 'title': '甲超限案例', 'description': '长' * 3600},
            {'id': 'ca2', 'title': '甲入选案例', 'description': '短' * 190},
        ])
        row_a[3].extend(files_pa)
        row_b = raw_row({'id': 'pb', 'name': '乙伙伴'}, ['乙主段落' + ('乙' * 496)])
        row_b[2].append({'id': 'cb1', 'title': '乙入选案例', 'description': '短' * 190})
        row_b[3].extend(files_pb)
        return [row_a, row_b]

    fa1_1 = {'id': 'fa1-1', 'case_id': 'ca1', 'filename': '甲跳过附件一.pdf', 'case_title': '甲超限案例'}
    fa1_2 = {'id': 'fa1-2', 'case_id': 'ca1', 'filename': '甲跳过附件二.pdf', 'case_title': '甲超限案例'}
    fa2_1 = {'id': 'fa2-1', 'case_id': 'ca2', 'filename': '甲有效附件详细版.pdf', 'case_title': '甲入选案例'}
    fb1_1 = {'id': 'fb1-1', 'case_id': 'cb1', 'filename': '乙有效附件一.pdf', 'case_title': '乙入选案例'}
    fb1_2 = {'id': 'fb1-2', 'case_id': 'cb1', 'filename': '乙附件二.pdf', 'case_title': '乙入选案例'}

    _, two_files_chars, _ = assemble(_fair_rows([fa2_1], [fb1_1]))
    monkeypatch.setattr(context, 'DETAIL_CHAR_LIMIT', two_files_chars)
    fair_rows = _fair_rows([fa1_1, fa1_2, fa2_1], [fb1_1, fb1_2])
    assemble(fair_rows)
    assert [c['id'] for c in fair_rows[0][1]['visibleCases']] == ['ca2']
    assert [d['id'] for d in fair_rows[0][1]['deliverables']] == ['fa2-1']
    assert [d['id'] for d in fair_rows[1][1]['deliverables']] == ['fb1-1']
    assert any(
        o['reason'] == 'file_selection_budget' and o['fileId'] == 'fb1-2'
        for o in fair_rows[1][1]['inputCoverage']['omissions']
    )
