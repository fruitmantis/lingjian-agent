"""Regression for explicit evidence boundaries and coherent advice after a baseline correction."""
import copy
import json
import pytest
from pydantic import ValidationError
from backend.app import development_engine as engine, development_lifecycle as life, development_views as views, development_model as model
from backend.app.database import get_db
from backend.app.development_types import AdvicePatch, Conversation
from backend.tests.test_unified_flow import unified, generated, prepared
from backend.tests.support.legacy_development import legacy_confirmed

CORRECTION='补充：已有 Python 开发经验，未做过 RAG，请调整实验建议。'
BASE='具备基本上云迁移能力；已有 Python 开发经验；未做过 RAG。'

@pytest.mark.parametrize('partner',[None,'partner-1'])
def test_correction_updates_all_derived_advice_and_preserves_legacy_version(unified,monkeypatch,partner):
    user=unified[0][0];request=unified[0][3]
    request.target_partner_id=partner
    request.development_direction='数据库迁移与 RAG 工程'
    request.known_baseline='具备基本上云迁移能力。'
    original=unified[2];observed=[]
    def completion(config,messages,schema):
        data=json.loads(messages[-1]['content']);stage=messages[0]['content'].split('。')[0]
        if stage.endswith(':patch'):
            assert schema['$defs']['ItemChange']['properties']['item_id']['enum']==data['understanding']['edit_item_ids']
            assert '每个 item_id 最多出现一次' in schema['properties']['changes']['description']
        observed.append((stage,copy.deepcopy(data),messages[0]['content']))
        if stage.endswith(':analyze'):
            assert set(schema['properties']['action']['enum'])==({'answer','patch','regenerate'} if data.get('current') else {'answer','generate'})
        if stage.endswith(':patch'):
            return json.dumps({'target_partner_id':partner,'changes':[{'action':'replace','item_id':data['understanding']['edit_item_ids'][0],
                'items':[{'source_type':'lab','source_id':'unified-lab-3','source_version':1,'focus':'Python 数据实践','reason':'结合已说明的 Python 基础实践，RAG 经验仍待积累。','estimated_hours':1}]}],
                'answer_changes':[{'before':data['understanding']['edit_answer_spans'][0],'after':'已有 Python 经验，未做过 RAG，建议通过实验实践。'}],
                'answer':'已结合本次补充调整。','limitations':['目标平台待核实。','合成目录仅用于测试。'],
                'resource_gaps':[],'next_steps':['使用合成数据完成实践并核验引用。']},ensure_ascii=False)
        result=json.loads(original(config,messages,schema))
        if stage.endswith(':analyze'):
            if data.get('current') and data['message']==CORRECTION:
                result.update(action='patch',effective_baseline=BASE,basis_limitations=['目标平台待核实。'],
                    partner_assessment='用户自述已有 Python 经验，未做过 RAG。',reusable_basis=['用户自述 Python 开发经验。'],
                    edit_item_ids=[data['current']['resources'][1]['item_id']],edit_answer_spans=[data['current']['answer']])
            elif not data.get('current'):
                result['basis_limitations']=['Python 基础待核实。']
                result['answer']='尚未检索候选就生成的草稿，不得进入正式建议。'
        if stage.endswith(':plan'):
            result['stages'][0]['items'][1]['note']='Python 基础待核实；合成环境限制仍有效。'
            result.update(answer='Python 基础待核实，先按当前迁移基础给出建议。',limitations=['Python 基础待核实。','合成目录仅用于测试。'],
                resource_gaps=['旧方向缺少专项课程。'],next_steps=['先确认 Python 基础。'])
        return json.dumps(result,ensure_ascii=False)
    monkeypatch.setattr(model,'completion',completion)
    accepted,before=generated(unified);pid=accepted['plan_id'];base=before['plan']['current_version_id']
    assert before['payload']['analysis']['answer']==''
    plan_input=next(data for stage,data,_ in observed if stage.endswith(':plan'))
    assert plan_input['analysis']['answer']=='' and plan_input['understanding']['answer']==''
    legacy_confirmed(pid,base,user)
    with get_db() as conn:old_row=dict(conn.execute('SELECT * FROM development_versions WHERE id=?',(base,)).fetchone())
    result=views.converse(pid,Conversation(submission_id='basis-patch-'+str(partner),based_on_version_id=base,message=CORRECTION),user)
    engine.execute(result['run_id']);after=views.detail(pid,user)
    assert after['runs'][0]['status']=='ready',after['failureDetails']
    payload=after['payload']
    assert payload['limitations']==['目标平台待核实。','合成目录仅用于测试。']
    assert payload['resource_gaps']==[] and payload['next_steps']==['使用合成数据完成实践并核验引用。']
    assert payload['analysis']['effective_baseline']==payload['overview']['known_baseline']==payload['effective_request']['known_baseline']==BASE
    assert payload['analysis']['basis_limitations']==['目标平台待核实。']
    assert payload['answer']=='已有 Python 经验，未做过 RAG，建议通过实验实践。'
    assert payload['stages'][0]['items'][0]==before['payload']['stages'][0]['items'][0]
    assert payload['stages'][0]['items'][1]['item_id']==before['payload']['stages'][0]['items'][1]['item_id']
    assert 'Python 数据实践' in payload['stages'][0]['title']
    assert before['payload']['limitations']==['Python 基础待核实。','合成目录仅用于测试。']
    with get_db() as conn:
        assert dict(conn.execute('SELECT * FROM development_versions WHERE id=?',(base,)).fetchone())==old_row
        assert conn.execute('SELECT confirmed_version_id FROM development_plans WHERE id=?',(pid,)).fetchone()[0]==base
    patch_input=next(data for stage,data,_ in observed if stage.endswith(':patch'))
    assert patch_input['request']['known_baseline']==BASE
    assert patch_input['current']['resources'][1]['note']=='Python 基础待核实；合成环境限制仍有效。'
    correction_input=next(data for stage,data,_ in observed if stage.endswith(':analyze') and data.get('message')==CORRECTION)
    assert correction_input['current']['resources'][1]['note']==patch_input['current']['resources'][1]['note']
    assert patch_input['current']['presentation']=={'limitations':before['payload']['limitations'],'resource_gaps':before['payload']['resource_gaps'],'next_steps':before['payload']['next_steps']}
    # Move the correction beyond the three-exchange history window; effective facts must persist.
    current=after['plan']['current_version_id']
    for i in range(4):
        result=views.converse(pid,Conversation(submission_id='basis-explain-'+str(i),based_on_version_id=current,message='为什么推荐这个方向？'),user)
        engine.execute(result['run_id'])
        latest=views.detail(pid,user)
        assert latest['runs'][0]['status']=='ready'
        assert latest['plan']['current_version_id']==current and len(latest['versions'])==2
        assert observed[-1][1]['request']['known_baseline']==BASE
        assert latest['payload']['limitations']==payload['limitations']
    # Check the actual outgoing prompt carries the fact-source boundary; live smoke evaluates adherence.
    assert all('候选课程实验不是已有能力的事实来源' in prompt and '不代表已有 API 集成' in prompt for _,_,prompt in observed)


def test_patch_requires_explicit_presentation_refresh():
    with pytest.raises(ValidationError) as error:
        AdvicePatch.model_validate({'target_partner_id':None,'changes':[],'answer_changes':[],'answer':'已调整'})
    assert {e['loc'][0] for e in error.value.errors()}=={'limitations','resource_gaps','next_steps'}


def test_patch_preserves_unaffected_group_title_and_rejects_unrelated_items():
    old={'target_partner_id':None,'answer':'原文','stages':[{'title':'不变组','items':[{'item_id':'untouched','focus':'原方向'}]},
        {'title':'已过时的方向','items':[{'item_id':'removed','focus':'旧方向'}]}], 'limitations':['旧提示'],'resource_gaps':[],'next_steps':[]}
    original=copy.deepcopy(old)
    analysis={'edit_item_ids':['removed'],'edit_answer_spans':[],'priorities':[],'basis_limited':False}
    request={'target_partner_id':None,'development_direction':'新方向','known_baseline':'用户自述基础'}
    patch={'target_partner_id':None,'changes':[{'action':'remove','item_id':'removed','items':[]}], 'answer_changes':[],
        'answer':'已移除','limitations':['新提示'],'resource_gaps':[],'next_steps':[]}
    merged=engine.merge_patch(old,patch,analysis,request,[],None)
    assert merged['stages'][0]==old['stages'][0] and old==original
    invalid=copy.deepcopy(patch);invalid['changes'][0]['item_id']='untouched'
    with pytest.raises(engine.InvalidOutput,match='outside requested items'):
        engine.merge_patch(old,invalid,analysis,request,[],None)


def test_capability_guard_does_not_join_unrelated_resource_and_caution_fields():
    engine.strong_guard({'changes':[{'reason':'实际可迁移程度需进一步确认。'}],
        'limitations':['不能据此判断其具备或不具备这些能力。']})


@pytest.mark.parametrize('claim',['确认该伙伴不具备开发能力','确认不足','明确不满足','没有开发能力','学完课程就具备','能力已提升'])
def test_capability_guard_still_rejects_strong_claims_in_nested_fields(claim):
    with pytest.raises(engine.InvalidOutput,match='Unsupported capability conclusion'):
        engine.strong_guard({'stages':[{'items':[{'note':claim}]}]})
