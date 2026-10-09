"""Bounded integration checks for unified understanding, reuse, and local edits."""
import copy
import json
import uuid
import pytest
from fastapi import HTTPException
from backend.app import development_lifecycle as life, development_engine as engine, development_views as views, development_model as model
from backend.app.database import get_db
from backend.app.development_types import Submit, Revise, Conversation
from backend.app.routers import development, match, model_config
from backend.tests.test_development_lifecycle import prepared, plan
from backend.tests.test_enablement import grant, published
from backend.app import enablement


@pytest.fixture
def unified(prepared, monkeypatch):
    user,other,admin,request=prepared
    with get_db() as conn:conn.execute("UPDATE model_configs SET api_key='synthetic-only',api_key_source='db'")
    for i in range(1,4):
        row=enablement.save('resource',f'unified-lab-{i}',enablement.ResourceSave(base_revision=0,metadata=enablement.ResourceMetadata(
            resource_type='lab',title=f'数据库迁移实验{i}',summary='数据库迁移与回退验证',lab_goals='验证数据库迁移和回退',level='advanced',source_url=f'https://example.com/lab/{i}')),admin['id'])
        published(grant(row,admin),admin)
    calls=[]
    def complete(config,messages,schema):
        data=json.loads(messages[-1]['content']);calls.append({'stage':messages[0]['content'].split('。')[0],'data':copy.deepcopy(data),'config':config['id']})
        from backend.tests.support.development_mock import response
        if 'analyze' in messages[0]['content']:
            result=response(messages)
            if data.get('current') and data['message']=='只换第二个实验':
                result.update(action='patch',edit_item_ids=[data['current']['resources'][1]['item_id']])
            return json.dumps(result,ensure_ascii=False)
        if 'patch' in messages[0]['content']:
            return json.dumps({'target_partner_id':request.target_partner_id,'changes':[{'action':'replace','item_id':data['understanding']['edit_item_ids'][0],
                'items':[{'source_type':'lab','source_id':'unified-lab-3','source_version':1,'reason':'按要求替换第二个实验','estimated_hours':1}]}],
                'answer_changes':[],'answer':'已替换第二个实验，其他内容保留。',**data['current']['presentation']})
        result=response(messages)
        result['stages'][0]['items']=sorted(result['stages'][0]['items'],key=lambda item:item['source_id'])[:2]
        return json.dumps(result,ensure_ascii=False)
    monkeypatch.setattr(model,'completion',complete)
    return prepared,calls,complete


def generated(unified):
    user=unified[0][0]
    accepted=life.create(Submit(submission_id='unified-generate',request=unified[0][3]),user)
    engine.execute(accepted['run_id'])
    detail=views.detail(accepted['plan_id'],user)
    assert detail['payload'],detail['runs']
    return accepted,detail


def test_understanding_shared_and_patch_preserves_other_content(unified):
    accepted,detail=generated(unified);pid=accepted['plan_id'];user=unified[0][0]
    assert len(unified[1])==2
    old=detail['payload'];base=detail['plan']['current_version_id']
    result=views.converse(pid,Conversation(submission_id='explain-second',based_on_version_id=base,message='按上一条第二点继续解释'),user)
    engine.execute(result['run_id'])
    result=views.detail(pid,user)['conversation'][-1]
    assert len(unified[1])==3 and plan(pid)['current_version_id']==base
    seen=unified[1][-1]['data'];assert seen['current']['answer']==old['answer']
    assert [x['position'] for x in seen['current']['resources']]==[1,2]
    repeated=views.converse(pid,Conversation(submission_id='repeat-requirement',based_on_version_id=base,message='我还是希望做数据库迁移与回退验证'),user)
    engine.execute(repeated['run_id'])
    assert plan(pid)['current_version_id']==base
    assert unified[1][-1]['data']['recent_exchanges'][-1]['answer']==result['answer']
    modified=views.converse(pid,Conversation(submission_id='patch-only-second',based_on_version_id=base,message='只换第二个实验'),user)
    engine.execute(modified['run_id'])
    after=views.detail(pid,user)
    assert len(unified[1])==6
    assert after['payload']['answer']==old['answer']
    assert after['payload']['stages'][0]['items'][0]==old['stages'][0]['items'][0]
    assert after['payload']['stages'][0]['items'][1]['source_id']=='unified-lab-3'
    assert after['payload']['stages'][0]['items'][1]['item_id']==old['stages'][0]['items'][1]['item_id']
    assert len(after['versions'])==2
    assert after['conversation'][-1]['answer']=='已替换第二个实验，其他内容保留。'


def test_failure_retry_reuses_understanding_and_preserves_current(unified,monkeypatch):
    accepted,detail=generated(unified);user=unified[0][0];pid=accepted['plan_id'];base=detail['plan']['current_version_id']
    from backend.tests.support.legacy_development import legacy_confirmed
    legacy_confirmed(pid,base,user)
    old_payload=copy.deepcopy(detail['payload'])
    result=views.converse(pid,Conversation(submission_id='patch-failure-second',based_on_version_id=base,message='只换第二个实验'),user)
    original=unified[2]
    def fail(config,messages,schema):
        if messages[0]['content'].startswith('partner_development:patch'):raise TimeoutError('synthetic failure')
        return original(config,messages,schema)
    monkeypatch.setattr(model,'completion',fail);engine.execute(result['run_id'])
    assert plan(pid)['current_version_id']==base
    monkeypatch.setattr(model,'completion',original)
    before=len(unified[1])
    retry=life.retry(pid,development.RetryRun(submission_id='retry-local-edit',run_id=result['run_id'],based_on_version_id=base),user)
    engine.execute(retry['run_id'])
    assert len(unified[1])==before+1 and plan(pid)['current_version_id']!=base
    after=views.detail(pid,user)
    assert plan(pid)['confirmed_version_id']==base
    assert after['payload']['stages'][0]['items'][1]['source_id']=='unified-lab-3'
    assert after['payload']['stages'][0]['items'][0]==old_payload['stages'][0]['items'][0]
    assert len(after['versions'])==2
    repeated=life.retry(pid,development.RetryRun(submission_id='retry-local-edit',run_id=result['run_id'],based_on_version_id=base),user)
    assert repeated['replayed'] and repeated['run_id']==retry['run_id']
    engine.execute(repeated['run_id'])
    assert len(views.detail(pid,user)['versions'])==2 and len(unified[1])==before+1

    with pytest.raises(HTTPException) as stale:
        life.retry(pid,development.RetryRun(submission_id='retry-completed-run',run_id=retry['run_id'],based_on_version_id=plan(pid)['current_version_id']),user)
    assert stale.value.status_code==409 and len(unified[1])==before+1


@pytest.mark.parametrize('change',['permission','profile','config'])
def test_changes_invalidate_successful_understanding(unified,monkeypatch,change):
    user=unified[0][0]
    accepted=life.create(Submit(submission_id='changed-generate',request=unified[0][3]),user)
    original=unified[2]
    def changed(config,messages,schema):
        result=original(config,messages,schema)
        if change=='permission':
            with get_db() as conn:conn.execute("UPDATE enablement_resources SET model_allowed=0,authorization_epoch=authorization_epoch+1 WHERE id='unified-lab-1'")
        elif change=='profile':
            with get_db() as conn:conn.execute("UPDATE partners SET intro='新资料' WHERE id='partner-1'")
        else:
            with get_db() as conn:conn.execute("UPDATE model_configs SET temperature=0.6")
        return result
    monkeypatch.setattr(model,'completion',changed)
    engine.execute(accepted['run_id']);assert plan(accepted['plan_id'])['current_version_id'] is None
    monkeypatch.setattr(model,'completion',original)
    before=len(unified[1]);retry=life.retry(accepted['plan_id'],development.RetryRun(submission_id='changed-retry',run_id=accepted['run_id']),user)
    engine.execute(retry['run_id'])
    assert len(unified[1])==before+2
    assert plan(accepted['plan_id'])['current_version_id']


def test_model_disabled_between_calls_stops_run(unified,monkeypatch):
    accepted=life.create(Submit(submission_id='disable-between-stages',request=unified[0][3]),unified[0][0])
    original=unified[2]
    def disable(config,messages,schema):
        result=original(config,messages,schema)
        with get_db() as conn:conn.execute('UPDATE model_configs SET enabled=0')
        return result
    monkeypatch.setattr(model,'completion',disable)
    engine.execute(accepted['run_id'])
    assert len(unified[1])==1
    assert plan(accepted['plan_id'])['current_version_id'] is None


def test_outside_scope_retains_task_and_owner_isolation(unified,monkeypatch):
    accepted,detail=generated(unified);base=detail['plan']['current_version_id'];pid=accepted['plan_id']
    with pytest.raises(HTTPException) as denied:
        views.converse(pid,Conversation(submission_id='outside-owner',based_on_version_id=base,message='解释一下'),unified[0][1])
    assert denied.value.status_code==404
    original=unified[2]
    def outside(c,m,s):
        result=json.loads(original(c,m,s));result['in_scope']=False;return json.dumps(result)
    monkeypatch.setattr(model,'completion',outside)
    outside=life.create(Submit(submission_id='outside-scope-test',request=unified[0][3]),unified[0][0])
    engine.execute(outside['run_id'])
    result=views.detail(outside['plan_id'],unified[0][0])
    assert result['runs'][0]['status']=='ready' and result['scopeMessage']
    assert result['payload'] is None and not result['failureDetails']
    with get_db() as conn:assert conn.execute('SELECT count(*) FROM development_plans').fetchone()[0]==2


def test_match_two_calls_shared_facts_local_recall_and_no_rule_fallback(unified,monkeypatch):
    calls=[]
    def complete(config,messages,schema):
        calls.append(schema['title'])
        if schema['title']=='MatchUnderstanding':
            return json.dumps({'in_scope':True,'facts':{'customerName':'合成客户','industry':'金融','region':'北京市','technicalNeeds':'数据库迁移'},'tag_suggestions':[]})
        assert schema['title']=='MatchAnswer'
        data=json.loads(messages[-1]['content'])
        assert data['requirement']=='合成客户需要数据库迁移伙伴'
        assert data['facts']['customerName']=='合成客户'
        assert 'understanding' not in data and data['candidates']
        return json.dumps({'recommendations':[],'supplyStatus':'unknown','gapAnalysis':'资料不足，需要补充交付证据。'})
    monkeypatch.setattr(model,'completion',complete)
    result=match.match_partners(match.MatchRequest(requirement='合成客户需要数据库迁移伙伴'),unified[0][0])
    assert calls==['MatchUnderstanding','MatchAnswer']
    from backend.app import match_understanding
    with get_db() as conn:
        snapshot=match_understanding.load(conn,result.recordId)
    assert snapshot['initial_selection']['method']=='postgres_keywords'
    detail=match.get_match_record(result.recordId,unified[0][0])
    assert result.taskStatus=='ready' and detail.opportunity['customerName']=='合成客户'
    assert detail.demandProfile['supplyStatus']=='unknown'
    assert detail.answer=='本次暂无正式推荐。\n\n资料不足，需要补充交付证据。'
    assert detail.demandProfile['gapAnalysis']=='资料不足，需要补充交付证据。'
    def broken(*args,**kwargs):raise RuntimeError('synthetic model failure')
    monkeypatch.setattr(match,'chat_completion',broken)
    with pytest.raises(RuntimeError):match._generate_demand_profile(result.recordId,'合成需求',[],life.now())


def test_equivalent_search_phrases_use_same_tokenization(unified):
    with get_db() as conn:
        short=engine.candidates(conn,unified[0][3].model_dump(),{'priorities':[{'search_terms':['数据库','迁移','回退'],'name':'数据库迁移'}],'resource_types':['lab']})
        long=engine.candidates(conn,unified[0][3].model_dump(),{'priorities':[{'search_terms':['数据库迁移 回退验证'],'name':'数据库迁移'}],'resource_types':['lab']})
    assert {r['source_id'] for r in short}=={r['source_id'] for r in long}=={f'unified-lab-{i}' for i in range(1,4)}


def test_match_retry_reuses_successful_facts_after_generation_failure(unified,monkeypatch):
    calls=[]
    def complete(config,messages,schema):
        calls.append(schema['title'])
        if schema['title']=='MatchUnderstanding':return '{"in_scope":true,"facts":{"technicalNeeds":"数据库迁移"}}'
        assert schema['title']=='MatchAnswer'
        if calls.count('MatchAnswer')==1:raise TimeoutError('synthetic second-stage failure')
        return '{"recommendations":[],"supplyStatus":"unknown","gapAnalysis":"待补充交付证据"}'
    monkeypatch.setattr(model,'completion',complete)
    with pytest.raises(HTTPException):match.match_partners(match.MatchRequest(requirement='需要数据库迁移伙伴'),unified[0][0])
    with get_db() as conn:task=conn.execute('SELECT id FROM match_records').fetchone()[0]
    assert match.get_match_record(task,unified[0][0]).answer==''
    result=match.retry_match_record(task,unified[0][0])
    assert result.taskStatus=='ready'
    assert calls==['MatchUnderstanding','MatchAnswer','MatchAnswer']
    detail=match.get_match_record(task,unified[0][0])
    assert detail.demandProfile['supplyStatus']=='unknown'
    assert detail.answer=='本次暂无正式推荐。\n\n待补充交付证据'
