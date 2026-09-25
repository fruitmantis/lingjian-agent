"""Scope decisions, strict transport contract and zero business side effects on rejection."""
from backend.tests.support.legacy_development import legacy_confirmed
import json
import uuid
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException

from backend.app import scope_gate as gate, development_lifecycle as life, development_views as views
from backend.app import development_model as model, error_diagnostics as diagnostics
from backend.app.database import get_db
from backend.app.development_types import Submit, DevelopmentRequest
from backend.app.model_resolver import ResolvedModelConfig
from backend.app.routers import match, development
from .conftest import make_user, make_partner, auth_headers, make_task

OFF_TOPIC = ['明天天气怎么样？', '帮我安排三天旅游行程', '写一个 Python 快速排序函数', '写一首关于月亮的诗']
TABLES = ('match_records', 'demand_profiles', 'project_opportunities', 'capability_tag_suggestions',
          'development_requests', 'development_plans', 'development_runs', 'development_versions', 'development_audit_events')


def counts():
    with get_db() as conn:
        return {table: conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in TABLES}


def forbid_business(monkeypatch):
    blocked = Mock(side_effect=AssertionError('Business processing must not start'))
    monkeypatch.setattr(match, '_perform_partner_match', blocked)
    monkeypatch.setattr(match, '_run_task_enrichment', blocked)
    monkeypatch.setattr(life.enablement_catalog, 'context', blocked)
    monkeypatch.setattr(development.executor, 'submit', blocked)
    monkeypatch.setattr(views.engine, 'blocked_fragments', blocked)
    monkeypatch.setattr(views, 'readable_payload', blocked)
    return blocked


@pytest.mark.parametrize('text', OFF_TOPIC)
@pytest.mark.parametrize('entry', ['tasks', 'legacy', 'development'])
def test_repeated_off_topic_never_creates_business_or_errors(client, monkeypatch, text, entry):
    user=make_user('scope-owner');headers=auth_headers(user)
    before=counts();errors=diagnostics.recent_errors();blocked=forbid_business(monkeypatch)
    classifier=Mock(return_value='{"in_scope":false}')
    monkeypatch.setattr(gate,'_complete',classifier)
    for _ in range(5):
        if entry=='development':
            path='/development/plans';body={'submission_id':str(uuid.uuid4()),'request':{'target_partner_id':'not-read','development_direction':text}}
        else:
            path='/agent/tasks' if entry=='tasks' else '/agent/match'
            body={'requirement':text,**({'requestId':str(uuid.uuid4())} if entry=='tasks' else {})}
        response=client.post(path,headers=headers,json=body)
        assert response.status_code==422
        assert response.json()['detail']==gate.MESSAGES['partner_development' if entry=='development' else 'partner_match']
    assert classifier.call_count==5 and blocked.call_count==0
    assert counts()==before and diagnostics.recent_errors()==errors
    for call in classifier.call_args_list:
        assert json.loads(call.args[1][1]['content'])=={'message':text,'context':''}


@pytest.mark.parametrize('raw', ['{}','[]','{"in_scope":"false"}','{"in_scope":0}','{"in_scope":null}',
                                 '{"in_scope":true,"answer":"poem"}','```json\n{"in_scope":false}\n```','not json'])
@pytest.mark.parametrize('entry',['match','development'])
def test_invalid_gate_is_system_error_not_business_rejection(client, monkeypatch, raw, entry):
    user=make_user('invalid-gate');before=counts();blocked=forbid_business(monkeypatch)
    monkeypatch.setattr(gate,'_complete',lambda *args:raw)
    request_id=str(uuid.uuid4())
    path='/agent/tasks' if entry=='match' else '/development/plans'
    body={'requestId':request_id,'requirement':'帮我推荐伙伴'} if entry=='match' else {'submission_id':request_id,'request':{'target_partner_id':'not-read','development_direction':'学习数据库迁移'}}
    response=client.post(path,headers=auth_headers(user),json=body)
    assert response.status_code==502
    assert response.json()=={'detail':'本次处理失败，请重试。','submissionAccepted':False}
    assert counts()==before and blocked.call_count==0
    errors=diagnostics.recent_errors();assert len(errors)==1
    assert errors[0]['stage']=='scope_gate' and errors[0]['request_id']==request_id
    assert errors[0]['traceback'] and errors[0]['message']


def test_transport_failure_records_model_status_and_redacted_fragment(client, monkeypatch):
    user=make_user('scope-service');blocked=forbid_business(monkeypatch);before=counts()
    config=ResolvedModelConfig('private-scope-credential','https://scope.invalid/v1','existing-model',.7,1,4096,60,'db')
    monkeypatch.setattr(gate,'resolve_model_config',lambda scene:config)
    async def post(self,url,**kwargs):
        return httpx.Response(401,request=httpx.Request('POST',url),json={'error':'rejected private-scope-credential'})
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    response=client.post('/agent/tasks',headers=auth_headers(user),json={'requestId':str(uuid.uuid4()),'requirement':'需要找伙伴'})
    assert response.status_code==502 and response.json()['detail']=='服务异常，请联系管理员。'
    error=diagnostics.recent_errors()[0]
    assert error['stage']=='scope_gate' and error['http_status']==401 and error['model']=='existing-model'
    assert 'rejected' in error['response_excerpt'] and 'private-scope-credential' not in json.dumps(error)
    assert blocked.call_count==0 and counts()==before


@pytest.mark.parametrize('mode', ['partner_match','partner_development'])
@pytest.mark.parametrize('host', ['https://scope.invalid/v1','https://api.deepseek.com'])
def test_reuses_existing_scene_with_small_strict_independent_call(monkeypatch, mode, host):
    selection=Mock(return_value=ResolvedModelConfig('scope-secret',host,'deepseek-v4-flash',.7,1,4096,60,'db'))
    monkeypatch.setattr(gate,'resolve_model_config',selection)
    config={'base_url':host,'model_name':'deepseek-v4-flash','api_key':'scope-secret','max_tokens':4096}
    dev_selection=Mock(return_value=config.copy());monkeypatch.setattr(model,'configuration',dev_selection)
    calls=[]
    async def post(self,url,**kwargs):
        calls.append(kwargs['json'])
        return httpx.Response(200,request=httpx.Request('POST',url),json={'choices':[{'message':{'content':'{"in_scope":true}'},'finish_reason':'stop'}]})
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    assert gate.check(mode,'为什么这样推荐？',context='云应用交付') is True
    assert len(calls)==1
    payload=calls[0]
    assert payload['temperature']==0 and payload['max_tokens']==64
    assert payload['response_format']['type']==('json_object' if 'deepseek' in host else 'json_schema')
    assert json.loads(payload['messages'][1]['content'])=={'message':'为什么这样推荐？','context':'云应用交付'}
    assert config['max_tokens']==4096
    assert (selection.call_count,dev_selection.call_count)==((1,0) if mode=='partner_match' else (0,1))


@pytest.mark.parametrize('text', ['需要一个伙伴，具体要求还没想好','为什么这样推荐？','旅游项目需要软件交付伙伴，也想了解当地天气','希望伙伴发展编程能力'])
def test_positive_decision_reaches_business_without_keyword_filter(client, monkeypatch, text):
    user=make_user('scope-positive');headers=auth_headers(user);make_partner()
    classifier=Mock(return_value='{"in_scope":true}');monkeypatch.setattr(gate,'_complete',classifier)
    generated=Mock();monkeypatch.setattr(match,'_process_created_task',generated)
    response=client.post('/agent/tasks',headers=headers,json={'requestId':str(uuid.uuid4()),'requirement':text})
    assert response.status_code==202 and generated.call_count==1
    executor=Mock();monkeypatch.setattr(development.executor,'submit',executor)
    response=client.post('/development/plans',headers=headers,json={'submission_id':str(uuid.uuid4()),'request':{'target_partner_id':'partner-1','development_direction':text}})
    assert response.status_code==202 and executor.call_count==1
    assert classifier.call_count==2


def saved_plan(user, monkeypatch):
    make_partner();monkeypatch.setattr(gate,'_complete',lambda *args:'{"in_scope":true}')
    result=life.create(Submit(submission_id='scope-base',request=DevelopmentRequest(target_partner_id='partner-1',development_direction='数据库迁移能力发展')),user)
    run=life.claim(result['run_id'])
    version=life.complete(run['id'],run['execution_token'],{'stages':[],'diagnoses':[],'overview':{'development_direction':'数据库迁移能力发展'}},[],lambda *args:None)
    legacy_confirmed(result['plan_id'],version,user)
    return result['plan_id'],version


@pytest.mark.parametrize('action',['conversation','revise'])
@pytest.mark.parametrize('text', OFF_TOPIC)
def test_existing_plan_off_topic_preserves_versions_and_stops_context_read(client,monkeypatch,action,text):
    user=make_user('plan-owner');pid,version=saved_plan(user,monkeypatch);headers=auth_headers(user)
    before=counts();blocked=forbid_business(monkeypatch);classifier=Mock(return_value='{"in_scope":false}')
    monkeypatch.setattr(gate,'_complete',classifier)
    for _ in range(3):
        response=client.post(f'/development/plans/{pid}/{action}',headers=headers,json={'submission_id':str(uuid.uuid4()),'based_on_version_id':version,('message' if action=='conversation' else 'instruction'):text})
        assert response.status_code==422 and response.json()['detail']==gate.MESSAGES['partner_development']
    assert counts()==before and blocked.call_count==0 and diagnostics.recent_errors()==[]
    with get_db() as conn:
        row=conn.execute('SELECT current_version_id,confirmed_version_id,active_run_id FROM development_plans WHERE id=?',(pid,)).fetchone()
        assert row['current_version_id']==row['confirmed_version_id']==version and row['active_run_id'] is None
    assert json.loads(classifier.call_args.args[1][1]['content'])=={'message':text,'context':'数据库迁移能力发展'}


def test_authorization_and_submission_replay_precede_gate(client,monkeypatch):
    user=make_user('scope-owner');other=make_user('scope-other');pid,version=saved_plan(user,monkeypatch)
    classifier=Mock(side_effect=AssertionError('Gate must not run'));monkeypatch.setattr(gate,'_complete',classifier)
    response=client.post(f'/development/plans/{pid}/conversation',headers=auth_headers(other),json={'submission_id':'other-identity','based_on_version_id':version,'message':'为什么这样推荐？'})
    assert response.status_code==404
    response=client.post('/development/plans',headers=auth_headers(user),json={'submission_id':'scope-base','request':{'target_partner_id':'partner-1','development_direction':'数据库迁移能力发展'}})
    assert response.status_code==202 and response.json()['replayed'] is True
    task=make_task(user,'天气查询',task_status='failed')
    response=client.post('/agent/tasks',headers=auth_headers(user),json={'requestId':task,'requirement':'天气查询'})
    assert response.status_code==202
    assert classifier.call_count==0


def test_retry_rechecks_before_changing_existing_task(client,monkeypatch):
    user=make_user('retry-owner');headers=auth_headers(user)
    task=make_task(user,OFF_TOPIC[0],task_status='partial')
    pid,version=saved_plan(user,monkeypatch)
    monkeypatch.setattr(gate,'_complete',lambda *args:'{"in_scope":true}')
    from backend.app.development_types import Revise
    accepted=life.revise(pid,Revise(submission_id='previous-fail',based_on_version_id=version,instruction=OFF_TOPIC[0]),user)
    run=life.claim(accepted['run_id']);life.finish_failure(run['id'],run['execution_token'],'generation',error=ValueError('previous failure'))
    before=counts();errors=diagnostics.recent_errors();blocked=forbid_business(monkeypatch)
    monkeypatch.setattr(gate,'_complete',lambda *args:'{"in_scope":false}')
    assert client.post(f'/agent/tasks/{task}/retry',headers=headers).status_code==422
    assert client.post(f'/development/plans/{pid}/retry',headers=headers,json={'submission_id':'retry-off-topic','run_id':run['id'],'based_on_version_id':version}).status_code==422
    assert counts()==before and diagnostics.recent_errors()==errors and blocked.call_count==0
    with get_db() as conn:
        assert conn.execute('SELECT task_status FROM match_records WHERE id=?',(task,)).fetchone()[0]=='partial'


@pytest.mark.parametrize('kind',['explain','revise'])
def test_in_scope_followup_checks_once_and_keeps_normal_conversation(client,monkeypatch,kind):
    user=make_user('followup-owner');pid,version=saved_plan(user,monkeypatch)
    classifier=Mock(return_value='{"in_scope":true}');monkeypatch.setattr(gate,'_complete',classifier)
    monkeypatch.setattr(model,'configuration',lambda:{})
    generator=Mock(return_value={'target_partner_id':'partner-1','kind':kind,'answer':'围绕迁移能力进一步说明','references':[]})
    monkeypatch.setattr(views.engine,'call',generator)
    executor=Mock();monkeypatch.setattr(development.executor,'submit',executor)
    message='为什么建议先做这个？' if kind=='explain' else '再增加迁移回退实践'
    response=client.post(f'/development/plans/{pid}/conversation',headers=auth_headers(user),json={'submission_id':'positive-followup','based_on_version_id':version,'message':message})
    assert response.status_code==200 and response.json()['kind']==kind
    assert classifier.call_count==generator.call_count==1
    assert executor.call_count==(1 if kind=='revise' else 0)
    assert json.loads(classifier.call_args.args[1][1]['content'])['context']=='数据库迁移能力发展'
    with get_db() as conn:
        assert conn.execute('SELECT count(*) FROM development_versions').fetchone()[0]==1
    assert diagnostics.recent_errors()==[]


def test_scope_diagnostics_do_not_relabel_following_generation(monkeypatch):
    monkeypatch.setattr(gate,'_complete',lambda *args:'{"in_scope":true}')
    with diagnostics.diagnostic_scope(task_id='task',stage='partner_match'):
        assert gate.check('partner_match','伙伴选择')
        assert diagnostics.current_stage('unknown')=='partner_match'


def test_missing_model_key_keeps_selected_model_in_diagnostics(client,monkeypatch):
    user=make_user('scope-config');before=counts()
    monkeypatch.delenv('LLM_API_KEY',raising=False)
    config={'base_url':'https://scope.invalid','model_name':'selected-existing-model','api_key':'','api_key_source':'db','api_key_env_name':''}
    monkeypatch.setattr(model,'configuration',lambda:config)
    blocked=forbid_business(monkeypatch)
    response=client.post('/development/plans',headers=auth_headers(user),json={'submission_id':'scope-config-missing','request':{'target_partner_id':'not-read','development_direction':'伙伴应用开发能力'}})
    assert response.status_code==502 and response.json()['submissionAccepted'] is False
    error=diagnostics.recent_errors()[0]
    assert error['stage']=='scope_gate' and error['model']=='selected-existing-model'
    assert 'API key is not configured' in error['message']
    assert blocked.call_count==0 and counts()==before
