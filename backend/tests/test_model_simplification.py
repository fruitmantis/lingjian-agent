"""Approved simplification: real persistence, synthetic material, no provider calls."""
import copy
import json
from types import SimpleNamespace
import uuid
import httpx
import pytest
from pydantic import ValidationError
from backend.business import matching
from backend.business.development import parse, InvalidOutput
from backend.app import ai_client, development_model as model, development_engine as engine
from backend.app import development_lifecycle as life, development_views as views
from backend.app import profile_sources as sources
from backend.app.database import get_db
from backend.app.development_types import Understanding, AdviceOutput, AdvicePatch, Conversation, DevelopmentRequest
from backend.app.task_failures import MatchInputBudgetError
from backend.tests.test_unified_flow import unified, generated, prepared
from backend.tests.test_optional_development_partner import replay, create
from backend.tests.test_profile_report import setup,upload,organize,profile
from backend.tests.support.profile_report_fixture import document
from backend.app import profile_report

CONFIG={'api_key':'synthetic-only','base_url':'http://127.0.0.1:1/v1','model_name':'synthetic','max_tokens':4096,'temperature':.3,'top_p':1.0}

@pytest.mark.parametrize('contract',[Understanding,AdviceOutput,AdvicePatch,sources.Contribution,sources.ChapterMerge])
def test_full_wire_meter_counts_schema_parameters_and_unicode(contract):
    messages=[{'role':'system','content':'系统规则'},{'role':'user','content':'合成需求'*120}]
    body,metrics=ai_client.prepared_completion(CONFIG,messages,contract.model_json_schema())
    assert metrics['characters']==len(body)
    assert metrics['utf8_bytes']==len(body.encode())>len(body)
    assert metrics['estimated_tokens']>0
    assert json.loads(body)['max_tokens']==4096
    assert 'response_format' in json.loads(body)
    assert json.dumps(contract.model_json_schema(),ensure_ascii=False) in json.loads(body)['messages'][0]['content']
    exact={**CONFIG,'_input_char_limit':len(body)}
    assert ai_client.prepared_completion(exact,messages,contract.model_json_schema())[0]==body
    with pytest.raises(MatchInputBudgetError):ai_client.prepared_completion({**exact,'_input_char_limit':len(body)-1},messages,contract.model_json_schema())

def test_transport_and_timeout_retry_send_the_identical_metered_bytes(monkeypatch,caplog):
    import logging
    caplog.set_level(logging.INFO,logger='uvicorn.error')
    messages=[{'role':'system','content':'合成规则'},{'role':'user','content':'用户需求'}]
    schema=AdviceOutput.model_json_schema()
    config={**CONFIG,'_match_output_tokens':321,'_input_char_limit':60000}
    body,_=ai_client.prepared_completion(config,messages,schema)
    sent=[]
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,**kwargs):
            sent.append(kwargs['content'])
            if len(sent)==1:raise httpx.ReadTimeout('synthetic timeout')
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"ok":true}'}}]},request=httpx.Request('POST',url))
    monkeypatch.setattr(model.httpx,'AsyncClient',Client)
    monkeypatch.setattr(model,'get_settings',lambda **kwargs:SimpleNamespace(timeoutSeconds=5,timeoutRetries=1))
    monkeypatch.setattr(model,'validate_model_retry',lambda _:None)
    assert model.completion(config,messages,schema)=='{"ok":true}'
    assert sent==[body.encode(),body.encode()]
    assert json.loads(sent[0])['max_tokens']==321
    records=[r.getMessage() for r in caplog.records if r.getMessage().startswith('MODEL_REQUEST_METRICS ')]
    assert len(records)==1
    measured=json.loads(records[0].split(' ',1)[1])
    assert measured['characters']==len(body) and measured['utf8_bytes']==len(body.encode())
    assert '用户需求' not in records[0] and CONFIG['api_key'] not in records[0]

@pytest.mark.parametrize('extra',[{'unused':'https://unused.invalid'},{'internal_debug':'DO_NOT_USE'},{'extra':{'anything':True}}])
def test_model_unknown_fields_project_before_guard_but_http_stays_strict(extra):
    data={'target_partner_id':None,'answer':'有用建议','stages':[],'used_refs':[],'used_profile_chapters':[],**extra}
    value=parse(json.dumps(data),AdviceOutput,['DO_NOT_USE'])
    assert set(value).isdisjoint(extra)
    with pytest.raises(ValidationError):Conversation.model_validate({'submission_id':'strict-http-test','based_on_version_id':'v1','message':'解释',**extra})
    with pytest.raises(ValidationError):DevelopmentRequest.model_validate({'development_direction':'需求',**extra})

@pytest.mark.parametrize('field',['answer','note','reason'])
def test_adopted_url_is_still_rejected(field):
    data={'target_partner_id':None,'answer':'建议','used_refs':[],'used_profile_chapters':[],'stages':[]}
    if field=='answer':data['answer']='见 https://invented.invalid'
    else:data['stages']=[{'title':'资源','items':[{'source_type':'lab','source_id':'l1','source_version':1,'reason':'有用',field:'见 https://invented.invalid'}]}]
    with pytest.raises(InvalidOutput):parse(json.dumps(data),AdviceOutput,[])

def test_nested_unknown_field_and_absent_hours_do_not_invent_presentation():
    value=parse(json.dumps({'target_partner_id':None,'used_refs':[],'used_profile_chapters':[],'stages':[{'title':'实践','unused':'https://unused.invalid','items':[{'source_type':'lab','source_id':'l1','source_version':1,'reason':'适合目标','unused':'https://unused.invalid'}]}]}),AdviceOutput,[])
    assert 'unused' not in value['stages'][0] and 'unused' not in value['stages'][0]['items'][0]
    assert value['stages'][0]['items'][0]['estimated_hours'] is None

def test_optional_patch_presentation_omitted_retains_and_empty_clears():
    old={'format_version':2,'target_partner_id':None,'answer':'  原段落  ','stages':[{'title':'组','items':[{'item_id':'one','focus':'原方向'}]}],'limitations':['原限制'],'resource_gaps':['原缺口'],'next_steps':['原下一步'],'used_refs':[],'used_profile_chapters':[]}
    patch={'target_partner_id':None,'changes':[],'answer_changes':[{'before':'  原段落  ','after':'新段落'}],'answer':'已更新','used_refs':[],'used_profile_chapters':[]}
    analysis={'edit_item_ids':[],'edit_answer_spans':['  原段落  '],'priorities':[]}
    request={'target_partner_id':None,'development_direction':'合成方向'}
    projected=parse(json.dumps(patch),AdvicePatch,[])
    assert projected['answer_changes'][0]['before']=='  原段落  '
    merged=engine.merge_patch(old,projected,analysis,request,[],None)
    assert merged['limitations']==old['limitations'] and merged['answer']=='新段落'
    assert old['answer']=='  原段落  '
    projected=parse(json.dumps({**patch,'limitations':[]}),AdvicePatch,[])
    assert 'limitations' not in projected
    assert engine.merge_patch(old,projected,analysis,request,[],None)['limitations']==old['limitations']
    assert 'limitations' not in parse(json.dumps({**patch,'limitations':None}),AdvicePatch,[])
    projected=parse(json.dumps({**patch,'resource_gaps':[]}),AdvicePatch,[])
    assert engine.merge_patch(old,projected,analysis,request,[],None)['resource_gaps']==[]
    with pytest.raises(InvalidOutput):parse(json.dumps({**patch,'resource_gaps':None}),AdvicePatch,[])

def test_understanding_retains_exact_answer_span_whitespace(replay):
    _,detail=create(replay)
    data=json.loads(replay[2](CONFIG,[{'role':'system','content':'partner_development:analyze'},{'role':'user','content':json.dumps(replay[1][0])}],Understanding.model_json_schema()))
    data['edit_answer_spans']=['  唯一原段落  ']
    assert parse(json.dumps(data),Understanding,[])['edit_answer_spans']==['  唯一原段落  ']

def test_malformed_card_does_not_erase_independent_analysis_or_supply():
    data={'recommendations':[{'partnerId':'bad','profileEvidence':['B1']}],'analysisRefs':[],'supplyStatus':'sufficient','gapAnalysis':'具体供给判断','unused':'https://unused.invalid'}
    value,rejected=matching.parse_answer(json.dumps(data))
    assert value['recommendations']==[] and value['_analysis_shape_valid']
    assert value['gapAnalysis']=='具体供给判断' and value['supplyStatus']=='sufficient'
    assert rejected==['recommendation:0']

@pytest.mark.parametrize('target',['card','analysis'])
def test_matching_adopted_leak_isolated_to_its_result_unit(target):
    card={'partnerId':'p1','matchScore':'80','recommendationReason':'具体价值','profileEvidence':[],'evidenceCases':[],'evidenceDeliverables':[],'unused':'https://unused.invalid'}
    data={'recommendations':[card],'analysisRefs':[],'supplyStatus':'partial','gapAnalysis':'具体整体分析','unused':'https://unused.invalid'}
    if target=='card':card['recommendationReason']='https://invented.invalid'
    else:data['gapAnalysis']='https://invented.invalid'
    value,rejected=matching.parse_answer(json.dumps(data))
    if target=='card':assert not value['recommendations'] and value['gapAnalysis']=='具体整体分析' and value['_analysis_shape_valid']
    else:assert len(value['recommendations'])==1 and not value['_analysis_shape_valid'] and value['gapAnalysis']==''
    assert rejected

def test_matching_core_and_auxiliary_are_independent():
    value,rejected=matching.parse_understanding(json.dumps({'in_scope':True,'facts':{'businessNeeds':'Quasar','capabilityTags':['allowed','unknown']},'tag_suggestions':[{'suggestedName':'新能力','description':'合成','evidenceText':'Quasar'},{'suggestedName':1}]}),'需要Quasar',{'allowed'})
    assert value['facts']['capabilityTags']==['allowed'] and len(value['tag_suggestions'])==1
    assert rejected

def test_auxiliary_formal_tag_overflow_does_not_discard_main_fact():
    tags=['tag'+str(n) for n in range(40)]
    value,rejected=matching.parse_understanding(json.dumps({'in_scope':True,'facts':{'businessNeeds':'完整主事实','capabilityTags':tags}}),'完整主事实',set(tags))
    assert value['facts']['businessNeeds']=='完整主事实' and len(value['facts']['capabilityTags'])==30
    assert rejected==['capability_tag_overflow']

def test_copy_uses_effective_request_without_synthetic_overview(replay):
    accepted,detail=create(replay)
    assert 'overview' not in detail['payload']
    text=views.transferable(accepted['plan_id'],replay[0][0])['text']
    assert '伙伴能力发展安排' in text

def test_source_blocks_include_irrelevant_paragraphs_and_literal_qualifiers():
    text='# 本公司产品\n\n仅本公司支持 Quasar；截至2026年为企业自述。\n\n# 集团研发\n\n集团规划支持 Falcon，未交付。\n\n# 日常信息\n\n与能力无关的日常信息。'
    source={'kind':'document','id':'doc1','partner_id':'partner1','text':text}
    blocks,mapping=sources.source_blocks(source)
    combined='\n'.join(block['text'] for block in blocks)
    assert all(fragment in combined for fragment in ('仅本公司','企业自述','集团规划','未交付','日常信息'))
    assert all(block['text']==text[mapping[block['id']]['start']:mapping[block['id']]['end']] for block in blocks)
    assert all(set(block)=={'id','text'} for block in blocks)

def test_source_chapters_reject_bad_units_and_restore_full_raw_block():
    source={'kind':'document','id':'d1','partner_id':'p1','text':'仅本公司支持Quasar。\n但不支持跨境交付；企业自述。'}
    blocks,mapping=sources.source_blocks(source)
    raw={'sections':[{'chapter':5,'summary':'支持Quasar但不支持跨境','block_ids':[blocks[0]['id']],'unused':'https://unused.invalid'},{'chapter':8,'summary':'无效','block_ids':['invented']},{'chapter':4,'summary':'错类型','block_ids':3}]}
    accepted,rejected=sources.numbered_sections(source,json.dumps(raw),mapping)
    assert [row['chapter'] for row in accepted]==[5] and set(rejected)=={4,8}
    assert '不支持跨境交付' in accepted[0]['quotes'][0]
    assert sources.numbered_sections(source,'{"sections":[]}',mapping)==([],[])
    with pytest.raises(ValueError):sources.numbered_sections(source,json.dumps({'sections':[raw['sections'][1]]}),mapping)

def test_duplicate_chapter_conflicts_reject_only_that_chapter():
    source={'kind':'document','id':'d1','text':'合成事实'};blocks,mapping=sources.source_blocks(source)
    unit={'chapter':5,'summary':'事实','block_ids':[blocks[0]['id']]}
    accepted,rejected=sources.numbered_sections(source,json.dumps({'sections':[unit,unit,{**unit,'chapter':6}]}),mapping)
    assert [row['chapter'] for row in accepted]==[6] and 5 in rejected

@pytest.mark.parametrize('text',['https://invented.invalid','INTERNAL_SECRET_MUST_NOT_LEAK'])
def test_source_adopted_leak_rejects_its_unit_while_unknown_extra_is_ignored(text):
    source={'kind':'document','id':'d1','text':'具体合成事实'};blocks,mapping=sources.source_blocks(source)
    raw={'sections':[{'chapter':5,'summary':'具体事实','block_ids':[blocks[0]['id']],'unused':text},{'chapter':6,'summary':text,'block_ids':[blocks[0]['id']]}]}
    accepted,rejected=sources.numbered_sections(source,json.dumps(raw),mapping)
    assert [unit['chapter'] for unit in accepted]==[5] and rejected==[6]

def test_complete_budget_failure_does_not_call_profile_provider(monkeypatch):
    calls=[];monkeypatch.setenv('BANFEI_PROFILE_INPUT_MAX_CHARS','1000')
    monkeypatch.setattr(sources,'resolve_model_record',lambda _:CONFIG)
    monkeypatch.setattr(model,'completion',lambda *args:calls.append(args))
    with pytest.raises(MatchInputBudgetError):sources._profile_completion([{'role':'system','content':sources.PROMPT},{'role':'user','content':json.dumps({'chapters':[{'chapter':n,'title':title} for n,title in enumerate(profile_report.CHAPTERS[:9],1)],'blocks':[{'id':'B1','text':'合成'*1000}]},ensure_ascii=False)}],sources.Contribution)
    assert calls==[]

@pytest.mark.parametrize('changed',['unadopted','adopted'])
def test_save_checks_adopted_resource_epoch_not_entire_catalog(unified,monkeypatch,changed):
    original=unified[2]
    def complete(config,messages,schema):
        result=original(config,messages,schema)
        if schema['title']=='AdviceOutput':
            selected=json.loads(result)['stages'][0]['items']
            assert [row['source_id'] for row in selected]==['unified-lab-1','unified-lab-2']
            identity='unified-lab-3' if changed=='unadopted' else 'unified-lab-1'
            with get_db() as conn:conn.execute('UPDATE enablement_resources SET authorization_epoch=authorization_epoch+1 WHERE id=?',(identity,))
        return result
    monkeypatch.setattr(model,'completion',complete)
    accepted=life.create(__import__('backend.app.development_types',fromlist=['Submit']).Submit(submission_id='dependency-epoch-'+changed,request=unified[0][3]),unified[0][0])
    engine.execute(accepted['run_id']);detail=views.detail(accepted['plan_id'],unified[0][0])
    assert detail['runs'][0]['status']==('ready' if changed=='unadopted' else 'failed')
    assert bool(detail['payload'])==(changed=='unadopted')
    if detail['payload']:
        with get_db() as conn:deps=json.loads(conn.execute('SELECT dependency_json FROM development_versions WHERE plan_id=?',(accepted['plan_id'],)).fetchone()[0])
        assert {ref['source_id'] for ref in deps}=={'unified-lab-1','unified-lab-2'}

def test_explanation_saves_own_dependencies_without_new_version(unified):
    accepted,before=generated(unified);base=before['plan']['current_version_id'];user=unified[0][0]
    run=views.converse(accepted['plan_id'],Conversation(submission_id='explain-own-dependencies',based_on_version_id=base,message='为什么推荐这些资源？'),user)
    engine.execute(run['run_id']);after=views.detail(accepted['plan_id'],user)
    assert after['plan']['current_version_id']==base and len(after['versions'])==1
    assert after['conversation'][-1]['format_version']==2 and 'dependencies' not in after['conversation'][-1]
    with get_db() as conn:stored=json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',(after['plan']['request_id'],)).fetchone()[0])
    assert stored['_conversation'][-1]['dependencies']

def test_patch_inherits_untouched_resource_dependencies(unified,monkeypatch):
    original=unified[2]
    def complete(config,messages,schema):
        result=json.loads(original(config,messages,schema))
        if result.get('action')=='patch':result['used_refs']=[]
        return json.dumps(result)
    monkeypatch.setattr(model,'completion',complete)
    accepted,before=generated(unified);user=unified[0][0];base=before['plan']['current_version_id']
    run=views.converse(accepted['plan_id'],Conversation(submission_id='patch-inherit-dependencies',based_on_version_id=base,message='只换第二个实验'),user)
    engine.execute(run['run_id']);after=views.detail(accepted['plan_id'],user)
    assert after['runs'][0]['status']=='ready',after['failureDetails']
    assert after['payload']['stages'][0]['items'][0]==before['payload']['stages'][0]['items'][0]
    with get_db() as conn:deps=json.loads(conn.execute('SELECT dependency_json FROM development_versions WHERE id=?',(after['plan']['current_version_id'],)).fetchone()[0])
    assert {ref['source_id'] for ref in deps}=={'unified-lab-1','unified-lab-3'}

def test_new_payload_has_no_synthetic_diagnosis_or_repeated_request(replay):
    accepted,detail=create(replay)
    payload=detail['payload'];generation=replay[1][1]
    assert 'diagnoses' not in payload and 'overview' not in payload and 'accepted_assumptions' not in payload
    assert payload['format_version']==2 and 'understanding' in payload
    assert 'analysis' not in generation and generation['understanding']['effective_direction']==payload['understanding']['effective_direction']
    assert generation['request']['development_direction']==replay[1][0]['request']['development_direction']
    assert 'effective_baseline' not in generation['understanding'] and 'profile_basis' not in generation['understanding']
    assert generation['message']=='' and generation['profile']['chapters']==[]

def test_empty_source_contribution_is_legal_without_fake_completed_image(setup,monkeypatch):
    monkeypatch.setattr(model,'completion',lambda *args:'{"sections":[]}')
    fid=upload(setup,'empty-contribution.txt','合成无关信息')
    with get_db() as conn:
        row=conn.execute('SELECT state,sections_json FROM partner_profile_sources WHERE source_id=?',(fid,)).fetchone()
        assert row['state']=='ready' and json.loads(row['sections_json'])==[]
    assert profile(setup)['profile_status']=='missing'

def test_valid_word_image_survives_unrelated_failed_source(setup,monkeypatch):
    upload(setup,'baseline.docx',document(),True)
    before=profile(setup)['ai_profile']
    monkeypatch.setattr(model,'completion',lambda *args:json.dumps({'sections':[{'chapter':5,'summary':'非法编号','block_ids':['invented']}]}))
    fid=upload(setup,'bad-source.txt','合成Quasar')
    after=profile(setup,True)
    assert after['profile_status']=='ready' and after['ai_profile'].split(profile_report.heading(10))[0]==before.split(profile_report.heading(10))[0]
    assert any(row['source_id']==fid and row['state']=='failed' for row in after['profile_sources'])

def test_merge_adopts_one_valid_chapter_keeps_invalid_old_chapter_dirty(setup,monkeypatch):
    upload(setup,'baseline.docx',document(),True)
    before=profile_report.parse(profile(setup)['ai_profile']).chapters
    def complete(config,messages,schema):
        data=json.loads(messages[-1]['content'])
        if schema['title']=='Contribution':
            return json.dumps({'sections':[{'chapter':n,'summary':'NewOnlyQuasar','block_ids':[b['id'] for b in data['blocks']]} for n in (5,8)]})
        result=[]
        for chapter in data['chapters']:
            source=next(row['source'] for row in chapter['sources'] if row.get('summary')=='NewOnlyQuasar')
            result.append({'chapter':chapter['chapter'],'body':'具体Quasar产品实践','used_sources':[source if chapter['chapter']==5 else 'invented']})
        return json.dumps({'sections':result})
    monkeypatch.setattr(model,'completion',complete)
    upload(setup,'two-chapters.txt','NewOnlyQuasar')
    organize(setup);after=profile(setup)
    chapters=profile_report.parse(after['ai_profile']).chapters
    assert '具体Quasar产品实践' in chapters[4] and chapters[7]==before[7]
    assert after['profile_needs_update'] and after['profile_status']=='ready'

@pytest.mark.parametrize('changed',['unused','used'])
def test_merge_checks_used_sources_and_records_call_time_stamp(setup,monkeypatch,changed):
    upload(setup,'baseline.docx',document(),True)
    used=upload(setup,'core.txt','CoreQuasar')
    unused=upload(setup,'extra.txt','ExtraFalcon')
    pid=setup[3];before=profile_report.parse(profile(setup)['ai_profile']).chapters[4]
    def complete(config,messages,schema):
        data=json.loads(messages[-1]['content']);chapter=data['chapters'][0]
        token=next(row['source'] for row in chapter['sources'] if row.get('summary')=='CoreQuasar')
        identity=unused if changed=='unused' else used
        with get_db() as conn:
            conn.execute('UPDATE partner_documents SET extracted_text=? WHERE id=?',('ChangedSynthetic',identity))
            fresh=sources.source(conn,pid,'document',identity)
            sources.put(conn,fresh,'ready',[{'chapter':5,'summary':'ChangedSynthetic','quotes':['ChangedSynthetic']}])
        return json.dumps({'sections':[{'chapter':5,'body':'仅采用CoreQuasar具体事实','used_sources':[token]}]})
    monkeypatch.setattr(model,'completion',complete)
    organize(setup);after=profile(setup)
    chapter=profile_report.parse(after['ai_profile']).chapters[4]
    if changed=='unused':
        assert '仅采用CoreQuasar' in chapter
        with get_db() as conn:
            partner=dict(conn.execute('SELECT * FROM partners WHERE id=?',(pid,)).fetchone());meta=sources.chapter_meta(partner)
            assert [ref['id'] for ref in meta['5']['used_sources']]==[used]
            assert meta['5']['input_stamp']!=sources._input_stamp(sources.chapter_inputs(conn,pid)['5'])
    else:assert chapter==before
    assert after['profile_needs_update']


def test_historical_projection_preserves_unrelated_text_exactly():
    from backend.business.common import historical_match_answer,historical_development_payload,MATCH_LEGACY_TEMPLATE
    text='  原业务说明\n\n\n原始日期 2024-01-01\n \n原始限制  '
    assert historical_match_answer(text,None)==text
    assert historical_match_answer(text+'\n\n'+MATCH_LEGACY_TEMPLATE,None)==text
    assert historical_match_answer(MATCH_LEGACY_TEMPLATE,2)==MATCH_LEGACY_TEMPLATE
    embedded='原文说：'+MATCH_LEGACY_TEMPLATE+'业务事实继续。'
    assert historical_match_answer(embedded,None)==embedded
    old={'answer':text};assert historical_development_payload(old)=={'answer':text}

def test_understanding_preserves_answer_span_whitespace():
    value=Understanding.model_validate({'in_scope':True,'action':'generate','effective_direction':'合成方向','effective_baseline':'','intent':'development','interpretation':'合成理解','target_partner_id':None,'used_refs':[],'used_profile_chapters':[], 'edit_answer_spans':['  精确原段落  ']})
    assert value.edit_answer_spans==['  精确原段落  ']

def test_historical_matching_cards_read_without_new_execution_revalidation():
    from backend.tests.conftest import make_user,make_task,recommendation
    from backend.app.routers import match
    from backend.app import match_understanding
    from backend.business.common import MATCH_LEGACY_TEMPLATE
    owner=make_user('historical-projection-owner')
    old=recommendation();task=make_task(owner,'历史需求',recommendations=[old],task_status='ready')
    original='  已有事实\n\n\n原始业务限制'
    with get_db() as conn:match_understanding.save(conn,task,{'visible_answer':original+'\n\n'+MATCH_LEGACY_TEMPLATE})
    detail=match.get_match_record(task,owner)
    assert detail.answer==original and len(detail.recommendations)==1
    with get_db() as conn:assert match_understanding.load(conn,task)['visible_answer'].endswith(MATCH_LEGACY_TEMPLATE)


def test_model_history_rechecks_its_own_authorization_epoch(unified):
    from backend.app.development_context import _model_readable
    with get_db() as conn:
        refs=engine.dependencies(conn,[{'source_type':'lab','source_id':'unified-lab-3','source_version':1}])
        history={'dependency_json':json.dumps(refs)}
        assert _model_readable(conn,history)
        conn.execute('UPDATE enablement_resources SET authorization_epoch=authorization_epoch+1 WHERE id=?',('unified-lab-3',))
        assert not _model_readable(conn,history)

@pytest.mark.parametrize('value,success',[
    ({'ok':True,'unused':'https://unused.invalid'},True),
    ({'ok':True,'unused':'INTERNAL_SECRET_UNUSED'},True),
    ({'ok':'true'},False),
    ({'ok':1},False),
    ({'ok':False},False),
])
def test_probe_projects_extras_but_requires_strict_true(monkeypatch,value,success):
    from backend.app.routers.model_config import test_connection
    with get_db() as conn:
        config_id=conn.execute('SELECT id FROM model_configs ORDER BY id LIMIT 1').fetchone()[0]
        conn.execute("UPDATE model_configs SET api_key='synthetic-only',api_key_source='db' WHERE id=?",(config_id,))
    monkeypatch.setattr(model,'completion',lambda *args:json.dumps(value))
    result=test_connection(config_id)
    assert result.success is success
    if not success:assert result.message=='连接成功，但返回内容未通过校验'


@pytest.mark.parametrize('malformed_card',[False,True])
def test_zero_cards_retain_independently_adopted_supply(malformed_card):
    from backend.app.routers import match
    raw={'recommendations':[], 'analysisRefs':[], 'supplyStatus':'gap',
         'gapAnalysis':'本次需求所要求的交付环节未得到候选材料支撑。'}
    if malformed_card:raw['recommendations']=[{'partnerId':'invented','profileEvidence':['unknown']}]
    output,rejected=matching.parse_answer(json.dumps(raw))
    with get_db() as conn:result=match._validated_outcome([],output,rejected,[],connection=conn)
    assert result['recommendations']==[] and result['analysis_adopted'] is True
    assert result['supplyStatus']=='gap' and result['gapAnalysis']==raw['gapAnalysis']


@pytest.mark.parametrize('malformed_card',[False,True])
def test_zero_cards_do_not_adopt_invalid_overall_references(malformed_card):
    from backend.app.routers import match
    raw={'recommendations':[], 'analysisRefs':[{'partnerId':'invented','profileEvidence':[],
         'evidenceCases':[],'evidenceDeliverables':[]}], 'supplyStatus':'gap','gapAnalysis':'非法资料不能进入正文。'}
    if malformed_card:raw['recommendations']=[{'partnerId':'invented','profileEvidence':['unknown']}]
    output,rejected=matching.parse_answer(json.dumps(raw))
    with get_db() as conn:result=match._validated_outcome([],output,rejected,[],connection=conn)
    assert result['analysis_adopted'] is False
    assert result['supplyStatus']=='unknown' and result['gapAnalysis']==''


@pytest.mark.parametrize('malformed_card',[False,True])
def test_zero_cards_supply_survives_writer_recheck_pg_and_public_api(setup,monkeypatch,malformed_card):
    from backend.app import match_understanding
    from backend.app.routers import match
    from backend.tests.conftest import make_user,auth_headers
    upload(setup,'synthetic-supply-gap.txt','该伙伴提供药物研发数据平台交付。')
    owner=make_user('supply-gap-'+uuid.uuid4().hex[:8]);calls=[]
    gap='候选资料没有覆盖本次要求的完整交付环节。'
    def complete(config,messages,schema):
        calls.append(schema['title'])
        if schema['title']=='MatchUnderstanding':
            return json.dumps({'in_scope':True,'facts':{'technicalNeeds':'药物研发'},'tag_suggestions':[]})
        data=json.loads(messages[-1]['content'])
        candidate=next(row for row in data['candidates'] if row['partnerId']==setup[3])
        response={'recommendations':[],'supplyStatus':'gap','gapAnalysis':gap,
                  'analysisRefs':[{'partnerId':candidate['partnerId'],
                  'profileEvidence':[candidate['profilePassages'][0]['source']],
                  'evidenceCases':[],'evidenceDeliverables':[]}]}
        if malformed_card:response['recommendations']=[{'partnerId':candidate['partnerId'],'profileEvidence':['unknown']}]
        return json.dumps(response)
    monkeypatch.setattr(model,'completion',complete)
    accepted=match.create_task(match.TaskCreateRequest(requestId=uuid.uuid4(),requirement='需要药物研发平台伙伴，交付环节必须完整覆盖'),owner)
    match.executor.shutdown(wait=True)
    with get_db() as conn:
        snapshot=match_understanding.load(conn,accepted.recordId)
        record=conn.execute('SELECT task_status,recommendations_json FROM match_records WHERE id=?',(accepted.recordId,)).fetchone()
        demand=conn.execute('SELECT supply_status,gap_analysis,matched_partner_count FROM demand_profiles WHERE match_record_id=?',(accepted.recordId,)).fetchone()
    assert calls==['MatchUnderstanding','MatchAnswer']
    assert record['task_status']=='ready' and json.loads(record['recommendations_json'])==[]
    assert snapshot['outcome']['analysis_adopted'] is True and snapshot['outcome']['supplyStatus']=='gap'
    assert tuple(demand)==('gap',gap,0)
    response=setup[0].get('/agent/tasks/'+accepted.recordId,headers=auth_headers(owner))
    assert response.status_code==200
    public=response.json()
    assert public['recommendations']==[] and public['demandProfile']['supplyStatus']=='gap'
    assert public['demandProfile']['gapAnalysis']==gap


@pytest.mark.parametrize('reuse_current',[False,True])
def test_patch_sends_current_catalog_once_and_retains_item_references(unified,monkeypatch,reuse_current):
    original=unified[2];wires=[]
    def capture(config,messages,schema):
        body,metrics=ai_client.prepared_completion(config,messages,schema)
        result=json.loads(original(config,messages,schema))
        if schema['title']=='AdvicePatch':
            wires.append((json.loads(body),metrics))
            if reuse_current:
                result['changes'][0]['items'][0]['source_id']='unified-lab-2'
                result['used_refs']=[{'source_type':'lab','source_id':'unified-lab-1','source_version':1}]
        return json.dumps(result)
    monkeypatch.setattr(model,'completion',capture)
    accepted,before=generated(unified);user=unified[0][0];base=before['plan']['current_version_id']
    run=views.converse(accepted['plan_id'],Conversation(submission_id='patch-catalog-once-'+str(reuse_current),based_on_version_id=base,message='只换第二个实验'),user)
    engine.execute(run['run_id']);after=views.detail(accepted['plan_id'],user)
    assert after['runs'][0]['status']=='ready' and len(after['versions'])==2
    assert after['payload']['answer']==before['payload']['answer']
    old_items=[item for stage in before['payload']['stages'] for item in stage['items']]
    new_items=[item for stage in after['payload']['stages'] for item in stage['items']]
    assert new_items[0]==old_items[0] and new_items[1]['item_id']==old_items[1]['item_id']
    assert new_items[1]['source_id']==('unified-lab-2' if reuse_current else 'unified-lab-3')
    wire,metrics=wires[0];data=json.loads(wire['messages'][-1]['content'])
    identify=lambda ref:(ref['source_type'],ref['source_id'],ref['source_version'])
    current=data['current']['resources'];candidates=data['candidates']
    assert not {identify(ref) for ref in current}&{identify(ref) for ref in candidates}
    assert [ref['item_id'] for ref in current]==[item['item_id'] for item in old_items]
    assert [ref['position'] for ref in current]==[1,2]
    assert all(ref['title'] and ref['summary'] and 'lab_requirements' in ref for ref in current+candidates)
    assert metrics['characters']<=60000 and metrics['utf8_bytes']>metrics['characters']
    with get_db() as conn:
        deps=json.loads(conn.execute('SELECT dependency_json FROM development_versions WHERE id=?',(after['plan']['current_version_id'],)).fetchone()[0])
    # This fixture's understanding also adopts both currently shown resources.
    assert {ref['source_id'] for ref in deps}==({'unified-lab-1','unified-lab-2'} if reuse_current else {'unified-lab-1','unified-lab-2','unified-lab-3'})


@pytest.mark.parametrize('selected',[[],['  Python经验待确认。\n','若Python未确认，先补基础再进入实验。']])
def test_patch_wire_declares_exact_selected_answer_scope(selected):
    from backend.business.development import request
    payload={'understanding':{'edit_item_ids':['one'],'edit_answer_spans':selected},
             'current':{'answer':'前言\n'+''.join(selected),'resources':[]}}
    messages,schema=request('patch',payload,AdvicePatch)
    wire,_=ai_client.prepared_completion(CONFIG,messages,schema)
    sent=json.loads(wire)
    assert json.loads(sent['messages'][-1]['content'])==payload
    if selected:
        assert schema['$defs']['AnswerChange']['properties']['before']['enum']==selected
    else:
        assert schema['properties']['answer_changes']['maxItems']==0
        assert 'enum' not in schema['$defs']['AnswerChange']['properties']['before']


@pytest.mark.parametrize('expanded',[False,True])
def test_python_correction_preserves_all_other_body_resources_and_order(expanded):
    first='Python经验待确认，进入实验前需先确认或补Python/LLM API/向量库基础。'
    second='若Python未确认，先补基础再进入实验。'
    body='建议按“前提确认→方法框架→实验一→实验二→交付化验证”推进。'+first+'\n\n实验一：检索。实验二：评测。\n先做实验一，再做实验二；'+second+'两个实验完成后再考虑上线验证。'
    pool=[{'source_type':'course' if n==0 else 'lab','source_id':'synthetic-'+str(n),'source_version':1,
           'title':'合成RAG资源'+str(n),'capability_tag_ids':[],'lab_requirements':'已有Python经验'} for n in range(4)]
    items=[{**{k:ref[k] for k in ('source_type','source_id','source_version')},'item_id':'item-'+str(n),
            'focus':'RAG交付','reason':'RAG实践','note':'Python基础待确认。'} for n,ref in enumerate(pool)]
    request={'target_partner_id':None,'development_direction':'RAG交付','known_baseline':'团队已熟练掌握Python'}
    analysis={'edit_item_ids':[item['item_id'] for item in items],'edit_answer_spans':[first,second]}
    old=engine.assemble({'target_partner_id':None,'answer':body,'stages':[{'title':'RAG交付','items':items}],
                        'used_refs':[],'used_profile_chapters':[]},request,analysis,pool,None)
    changes=[{'item_id':item['item_id'],'action':'replace','items':[{**{k:item[k] for k in ('source_type','source_id','source_version','focus','reason')},'note':'Python基础已具备；准备隔离环境。'}]} for item in items]
    replacements=[{'before':first,'after':'团队已熟练掌握Python，实验前准备LLM API与向量库环境。'},
                  {'before':second,'after':''}]
    if expanded:replacements[1]['before']='先做实验一，再做实验二；'+second
    patch=parse(json.dumps({'target_partner_id':None,'changes':changes,'answer_changes':replacements,
                           'answer':'已纠正Python基础。','used_refs':[],'used_profile_chapters':[]}),AdvicePatch,[])
    untouched=copy.deepcopy(old)
    if expanded:
        with pytest.raises(InvalidOutput,match='Patch outside requested answer'):
            engine.merge_patch(old,patch,analysis,request,pool,None)
    else:
        merged=engine.merge_patch(old,patch,analysis,request,pool,None)
        assert merged['answer']==body.replace(first,replacements[0]['after']).replace(second,'')
        after=merged['stages'][0]['items']
        assert [item['item_id'] for item in after]==[item['item_id'] for item in items]
        assert [engine.key(item) for item in after]==[engine.key(item) for item in items]
        assert all(item['note']=='Python基础已具备；准备隔离环境。' for item in after)
        assert all(item['reason']=='RAG实践' and item['focus']=='RAG交付' for item in after)
    assert old==untouched


def test_saved_source_aliases_project_public_labels_and_keep_snapshot_and_facts(setup):
    from backend.tests.conftest import make_user,make_task,recommendation,auth_headers
    from backend.app import match_understanding
    from backend.app.routers import match
    pid=setup[3];fid=upload(setup,'PRIVATE_SYNTHETIC_FILENAME.txt','私有产品事实')
    case_id='synthetic-public-case'
    with get_db() as conn:
        conn.execute('INSERT INTO cases(id,partner_id,title,description,visible,created_at) VALUES (?,?,?,?,1,?)',
                     (case_id,pid,'公开压测案例','公开交付事实','2026-10-11'))
        name=conn.execute('SELECT name FROM partners WHERE id=?',(pid,)).fetchone()[0]
    aliases={'P1-S42':('case:'+case_id,'公开交付事实'),
             'P1-S43':('document:'+fid,'私有产品事实')}
    context={'profilePassages':[{'source':alias,'text':value[1]} for alias,value in aliases.items()],
             '_sourceMap':{alias:{'partnerId':pid,'sourceRef':value[0],'text':value[1]} for alias,value in aliases.items()}}
    with get_db() as conn:
        versions={(source['kind']+':'+source['id']):sources.stamp(source) for source in sources.sources(conn,pid)}
    for entry in context['_sourceMap'].values():entry['source_version']=versions[entry['sourceRef']]
    reason='P1-S42提供公开依据；产品代号XP1-S42和P1-S420保留，未知P9-S6保留。'
    risk='P1-S43仅说明资料事实，不代表已交付；性能为500 TPS。'
    rec={**recommendation(pid,name),'recommendationReason':reason,'riskNotes':risk}
    owner=make_user('alias-display-owner');task=make_task(owner,'合成需求',recommendations=[rec])
    snapshot={'format_version':2,'visible_answer':reason+'\n'+risk,
              'detail_rows':[[{'id':pid,'name':name},context,[{'id':case_id,'partner_id':pid,'title':'公开压测案例'}],[]]]}
    with get_db() as conn:match_understanding.save(conn,task,snapshot)
    for user in (owner,make_user('alias-display-admin',role='admin')):
        response=setup[0].get('/agent/tasks/'+task,headers=auth_headers(user))
        assert response.status_code==200
        public=response.json();card=public['recommendations'][0]
        assert card['recommendationReason']=='公开压测案例提供公开依据；产品代号XP1-S42和P1-S420保留，未知P9-S6保留。'
        assert card['riskNotes']=='[未展示资料]仅说明资料事实，不代表已交付；性能为500 TPS。'
        assert public['answer']==card['recommendationReason']+'\n'+card['riskNotes']
        assert fid not in response.text and 'PRIVATE_SYNTHETIC_FILENAME' not in response.text
    with get_db() as conn:
        assert match_understanding.load(conn,task)==snapshot
        assert json.loads(conn.execute('SELECT recommendations_json FROM match_records WHERE id=?',(task,)).fetchone()[0])==[rec]
        conn.execute('UPDATE cases SET description=? WHERE id=?',('新版不同交付事实',case_id))
    assert match.get_match_record(task,owner).recommendations[0].recommendationReason.startswith('[未展示资料]提供公开依据')
    with get_db() as conn:
        conn.execute('UPDATE cases SET description=? WHERE id=?',('公开交付事实',case_id))
        conn.execute('UPDATE cases SET title=? WHERE id=?',('新公开标题',case_id))
    assert match.get_match_record(task,owner).recommendations[0].recommendationReason.startswith('[未展示资料]提供公开依据')
    with get_db() as conn:
        conn.execute('UPDATE cases SET title=? WHERE id=?',('公开压测案例',case_id))
        conn.execute('UPDATE cases SET visible=0 WHERE id=?',(case_id,))
    detail=match.get_match_record(task,owner)
    assert detail.recommendations[0].recommendationReason.startswith('[未展示资料]提供公开依据')


def test_source_alias_projection_retains_card_identity_for_writer_recheck():
    from backend.tests.conftest import make_partner
    from backend.app.routers import match
    partner=make_partner('alias-writer','合成伙伴');text='AI,数据治理'
    context={'profilePassages':[{'source':'P1-S42','text':text}],
             '_sourceMap':{'P1-S42':{'partnerId':partner['id'],'sourceRef':'partner:'+partner['id'],
                                   'path':'/capabilities','text':text,'start':0,'end':len(text)}}}
    rows=[(partner,context,[],[])]
    raw={'recommendations':[{'partnerId':partner['id'],'matchScore':'80','recommendationReason':'P1-S42说明数据治理。',
                             'riskNotes':'P1-S42未提供电商交付事实。','profileEvidence':['P1-S42'],
                             'evidenceCases':[],'evidenceDeliverables':[]}],
         'supplyStatus':'gap','gapAnalysis':'P1-S42的资料未覆盖完整要求。',
         'analysisRefs':[{'partnerId':partner['id'],'profileEvidence':['P1-S42'],'evidenceCases':[],'evidenceDeliverables':[]}]}
    output,rejected=matching.parse_answer(json.dumps(raw))
    recs=match._validated_recommendations(output['recommendations'],[partner],{partner['id']:[]},{partner['id']:[]})
    with get_db() as conn:
        first=match._validated_outcome(recs,output,rejected,rows,connection=conn)
        second=match._validated_outcome(recs,output,rejected,rows,connection=conn)
    assert len(recs)==1 and first==second
    assert recs[0].recommendationReason=='合成伙伴伙伴信息说明数据治理。'
    assert 'P1-S42' not in first['answer'] and first['supplyStatus']=='gap'
    assert output['recommendations'][0]['recommendationReason']==raw['recommendations'][0]['recommendationReason']


def test_profile_merge_sends_existing_dimension_names_and_only_dirty_chapters(setup,monkeypatch):
    upload(setup,'baseline.docx',document(),True)
    before=profile_report.parse(profile(setup)['ai_profile']).chapters
    def complete(config,messages,schema):
        data=json.loads(messages[-1]['content'])
        if schema['title']=='Contribution':
            assert data['chapters']==[{'chapter':n,'title':title} for n,title in enumerate(profile_report.CHAPTERS[:9],1)]
            return json.dumps({'sections':[{'chapter':n,'summary':'合成产品，集团自述。','block_ids':[b['id'] for b in data['blocks']]} for n in (5,6)]})
        assert [chapter['chapter'] for chapter in data['chapters']]==[5,6]
        assert [chapter['title'] for chapter in data['chapters']]==list(profile_report.CHAPTERS[4:6])
        assert all(set(chapter)=={'chapter','title','sources'} for chapter in data['chapters'])
        assert 'PRIVATE_REPAIR' not in json.dumps(data)
        return json.dumps({'sections':[{'chapter':chapter['chapter'],'body':'合成产品实践，集团自述。',
                                        'used_sources':[entry['source'] for entry in chapter['sources']]} for chapter in data['chapters']]})
    monkeypatch.setattr(model,'completion',complete)
    upload(setup,'PRIVATE_REPAIR.txt','合成产品，集团自述。')
    organize(setup);after=profile_report.parse(profile(setup)['ai_profile']).chapters
    assert all(before[n]==after[n] for n in range(9) if n not in (4,5))
    assert all('集团自述' in after[n] for n in (4,5))


@pytest.mark.parametrize('ids',[['B1'],['B1','B2','B3'],[]])
def test_contribution_final_wire_requires_actual_block_ids_and_fixed_dimensions(monkeypatch,ids):
    original_prepare=ai_client.prepared_completion;metered=[];sent=[]
    payload={'chapters':[{'chapter':n,'title':title} for n,title in enumerate(profile_report.CHAPTERS[:9],1)],
             'blocks':[{'id':token,'text':'本公司产品事实；集团规划不作为本公司交付。\n  保留原文空白。'} for token in ids]}
    messages=[{'role':'system','content':sources.PROMPT},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
    monkeypatch.setattr(sources,'resolve_model_record',lambda _:CONFIG)
    def prepare(config,actual_messages,schema):
        wire,metrics=original_prepare(config,actual_messages,schema);metered.append(wire)
        return wire,metrics
    def complete(config,actual_messages,schema):
        wire,metrics=original_prepare(config,actual_messages,schema);sent.append(wire)
        data=json.loads(wire)
        final_schema=json.loads(data['messages'][0]['content'].split('Return only a JSON object matching this JSON schema: ',1)[1])
        section=final_schema['$defs']['Section']
        assert section['required']==['chapter','summary','block_ids']
        assert section['properties']['chapter']['enum']==list(range(1,10))
        assert section['properties']['block_ids']['minItems']==1
        if ids:assert section['properties']['block_ids']['items']['enum']==ids
        else:
            assert final_schema['properties']['sections']['maxItems']==0
            assert 'enum' not in section['properties']['block_ids']['items']
        assert json.loads(data['messages'][-1]['content'])==payload
        assert data['response_format']=={'type':'json_object'} and metrics['characters']<=100000
        return '{"sections":[]}'
    monkeypatch.setattr(ai_client,'prepared_completion',prepare)
    monkeypatch.setattr(model,'completion',complete)
    assert sources._profile_completion(messages,sources.Contribution)=='{"sections":[]}'
    assert len(sent)==1 and metered==sent


def test_single_block_contribution_missing_ids_fails_without_filling_or_retry(setup,monkeypatch):
    upload(setup,'baseline.docx',document(),True)
    before=profile(setup)['ai_profile'];calls=[]
    def complete(config,messages,schema):
        data=json.loads(messages[-1]['content']);calls.append(data)
        assert schema['title']=='Contribution' and [block['id'] for block in data['blocks']]==['B1']
        assert schema['$defs']['Section']['properties']['block_ids']['items']['enum']==['B1']
        return json.dumps({'sections':[{'chapter':n,'title':'自拟章节','summary':'合成来源事实'} for n in range(1,8)]})
    monkeypatch.setattr(model,'completion',complete)
    fid=upload(setup,'missing-block-ids.txt','合成来源事实，集团自述且尚未交付。')
    with get_db() as conn:
        row=conn.execute(f'SELECT state,sections_json,error FROM {sources.TABLE} WHERE source_id=?',(fid,)).fetchone()
    assert len(calls)==1 and row['state']=='failed' and json.loads(row['sections_json'])==[]
    assert '来源章节缺少block_ids' in row['error']
    assert profile(setup)['ai_profile'].split(profile_report.heading(10))[0]==before.split(profile_report.heading(10))[0]


def test_adjacent_native_sections_do_not_join_into_one_source_block():
    text='# 当前交付\n本公司提供数据库运维。\n# 集团未来规划\n集团规划，尚未交付。\n未来将建设内部管控。\n# 实际合规事件\n2026年发生实际业务违规事件。'
    source={'kind':'document','id':'synthetic-sections','text':text}
    blocks,mapping=sources.source_blocks(source)
    assert len(blocks)==3 and [block['id'] for block in blocks]==['B1','B2','B3']
    assert ''.join(block['text'] for block in blocks)==text
    assert '集团未来规划' in blocks[1]['text'] and '尚未交付' in blocks[1]['text'] and '未来将建设内部管控' in blocks[1]['text']
    assert '当前交付' not in blocks[1]['text'] and '实际合规事件' not in blocks[1]['text']
    assert all(block['text']==text[mapping[block['id']]['start']:mapping[block['id']]['end']] for block in blocks)
    accepted,rejected=sources.numbered_sections(source,json.dumps({'sections':[{'chapter':8,'summary':'集团规划建设内部管控。','block_ids':['B2']}]}),mapping)
    assert rejected==[] and accepted[0]['quotes']==[blocks[1]['text']]


@pytest.mark.parametrize('title',['# 集团未来规划','集团未来规划：'])
def test_native_source_block_keeps_phase_title_and_wrapped_qualification(title):
    text=title+'\n\n集团自述，尚未\n交付。\n\n未来提供新平\n台。\n\n当前交付：\n\n本公司提供数据库运维。'
    source={'kind':'document','id':'synthetic-phase','text':text}
    blocks,mapping=sources.source_blocks(source)
    assert len(blocks)==2
    assert blocks[0]['text'].startswith(title)
    assert all(fragment in blocks[0]['text'] for fragment in ('集团自述，尚未\n交付。','未来提供新平\n台。'))
    assert '当前交付：' not in blocks[0]['text'] and '本公司提供数据库运维' in blocks[1]['text']
    covered=set().union(*(set(range(entry['start'],entry['end'])) for entry in mapping.values()))
    assert all(index in covered or char.isspace() for index,char in enumerate(text))
    assert all(block['text']==text[mapping[block['id']]['start']:mapping[block['id']]['end']] for block in blocks)
