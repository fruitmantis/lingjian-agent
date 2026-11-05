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
    assert len(ids)==12 and ids[0]=='cert-14'
    assert ids[1:]==[f'cert-{i:02}' for i in range(11)]
    assert not any(pid.startswith('plain-') for pid in ids)


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
            'servicePartnerBasis':'capability_tag','identities':['云经销商']}
        assert context.input_metrics(config,messages,schema)[0]<=25000
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
