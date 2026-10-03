"""QA regressions: real VM bridge/Runtime/provider, synthetic MockTransport only."""
import asyncio,json,uuid
import httpx,pytest
from backend.agent_runtime import provider,server
from backend.agent_runtime.contracts import ModelOptions,model_route
from backend.app import development_model,model_timeout_settings
from backend.app.database import get_db
from backend.app.development_types import DevelopmentRequest,Submit
from backend.app import development_lifecycle as life,development_engine as engine,development_views as views
from backend.app.routers import match
from .test_agentarts_runtime import transport,packet
from .test_development_lifecycle import prepared,plan
from .test_partner_match_stages import answer
from .conftest import make_partner
from fastapi import HTTPException
from fastapi.testclient import TestClient
REAL_COMPLETION=provider.completion

@pytest.fixture
def provider_transport(transport,monkeypatch):
    monkeypatch.setattr(provider,'completion',REAL_COMPLETION)
    original=httpx.AsyncClient
    transport['network_calls']=[];transport['network_hook']=None
    async def handle(request):
        payload=json.loads(request.content)
        transport['network_calls'].append(payload)
        if transport['network_hook']:await transport['network_hook'](request,payload)
        messages=payload['messages'];system=messages[0]['content']
        if system.startswith('partner_development:'):
            from .support.development_mock import response
            content=json.dumps(response(messages),ensure_ascii=False)
        elif 'MatchUnderstanding' in system:content='{"in_scope":true,"facts":{"technicalNeeds":"数据库迁移"}}'
        elif 'InitialSelection' in system:content='{"candidates":[{"partnerId":"partner-1","verificationFocus":"数据库迁移"}]}'
        else:content=answer()
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':content}}]})
    def client(*args,**kwargs):
        kwargs['transport']=httpx.MockTransport(handle)
        return original(*args,**kwargs)
    monkeypatch.setattr(httpx,'AsyncClient',client)
    return transport

def run_workflow(workflow,prepared,success=True,submission='qa-fix-submission'):
    user=prepared[0]
    if workflow=='match':
        if success:
            result=match.match_partners(match.MatchRequest(requirement='数据库迁移'),user)
            assert result.taskStatus=='ready'
            return result
        with pytest.raises(HTTPException):match.match_partners(match.MatchRequest(requirement='数据库迁移'),user)
        with get_db() as conn:
            row=conn.execute('SELECT task_status,recommendations_json FROM match_records ORDER BY created_at DESC LIMIT 1').fetchone()
            assert row['task_status']=='failed' and json.loads(row['recommendations_json'])==[]
    else:
        accepted=life.create(Submit(submission_id=submission,request=DevelopmentRequest(development_direction='数据库迁移课程与实验')),user)
        engine.execute(accepted['run_id'])
        if success:
            detail=views.detail(accepted['plan_id'],user)
            assert detail['payload'] and len(detail['versions'])==1
            return detail
        assert plan(accepted['plan_id'])['current_version_id'] is None
        with get_db() as conn:assert conn.execute('SELECT count(*) FROM development_versions').fetchone()[0]==0

@pytest.mark.parametrize('workflow',['match','development'])
@pytest.mark.parametrize('change',['model_disabled','source_revoked','owner_disabled'])
def test_timeout_needs_fresh_vm_authorization(prepared,provider_transport,workflow,change):
    model_timeout_settings.save(model_timeout_settings.TimeoutSettings(timeoutSeconds=4001.,timeoutRetries=5))
    async def timeout_and_revoke(request,payload):
        with get_db() as conn:
            if change=='model_disabled':conn.execute('UPDATE model_configs SET enabled=0')
            elif change=='source_revoked':conn.execute("UPDATE partners SET status='disabled' WHERE id='partner-1'")
            else:conn.execute("UPDATE users SET status='disabled' WHERE id=?",(prepared[0]['id'],))
        raise httpx.ReadTimeout('synthetic first attempt timeout',request=request)
    provider_transport['network_hook']=timeout_and_revoke
    run_workflow(workflow,prepared,success=False)
    assert len(provider_transport['network_calls'])==1
    assert provider_transport['retry_posts']==[]
    assert provider_transport['packets'][0]['model']['timeout_seconds']==4001.
    assert provider_transport['packets'][0]['model']['timeout_retries']==5

@pytest.mark.parametrize('workflow',['match','development'])
def test_all_configured_retries_are_vm_authorized(prepared,provider_transport,workflow):
    model_timeout_settings.save(model_timeout_settings.TimeoutSettings(timeoutSeconds=4001.,timeoutRetries=5))
    async def timeout(request,payload):raise httpx.ReadTimeout('synthetic timeout',request=request)
    provider_transport['network_hook']=timeout
    run_workflow(workflow,prepared,success=False)
    assert len(provider_transport['network_calls'])==6
    assert [p['after_attempt'] for p in provider_transport['retry_posts']]==[1,2,3,4,5]
    assert provider_transport['posts']==1

@pytest.mark.parametrize('workflow',['match','development'])
def test_lost_retry_ack_reconciles_without_duplicate(prepared,provider_transport,workflow):
    async def first_timeout(request,payload):
        if len(provider_transport['network_calls'])==1:raise httpx.ReadTimeout('synthetic first timeout',request=request)
    provider_transport['network_hook']=first_timeout
    provider_transport['drop_retry_ack']=True
    run_workflow(workflow,prepared)
    assert len(provider_transport['retry_posts'])==1
    assert len(provider_transport['network_calls'])==(4 if workflow=='match' else 3)

@pytest.mark.parametrize('workflow',['match','development'])
def test_same_name_other_endpoint_rejected_before_material_dispatch(prepared,provider_transport,monkeypatch,workflow):
    monkeypatch.setenv('BANFEI_RUNTIME_MODEL_URL','https://other-provider.invalid/v1')
    run_workflow(workflow,prepared,success=False)
    assert provider_transport['posts']==0 and provider_transport['network_calls']==[]

@pytest.mark.parametrize('workflow',['match','development'])
def test_local_runtime_same_input_output(prepared,transport,monkeypatch,workflow):
    from backend.agent_runtime.workflows import messages_for
    from .support.development_mock import response
    seen={'local':[],'runtime':[]};which='local'
    def complete(config,messages,schema):
        seen[which].append((schema['title'],json.loads(messages[-1]['content'])))
        if workflow=='development':return json.dumps(response(messages),ensure_ascii=False)
        if schema['title']=='MatchUnderstanding':return '{"in_scope":true,"facts":{"technicalNeeds":"数据库迁移"}}'
        if schema['title']=='InitialSelection':return '{"candidates":[{"partnerId":"partner-1","verificationFocus":"数据库迁移"}]}'
        return answer()
    monkeypatch.setattr(development_model,'completion',complete);transport['complete']=complete
    monkeypatch.setenv('BANFEI_'+workflow.upper()+'_EXECUTOR','local')
    first=run_workflow(workflow,prepared,submission='compare-local')
    which='runtime';monkeypatch.setenv('BANFEI_'+workflow.upper()+'_EXECUTOR','runtime')
    second=run_workflow(workflow,prepared,submission='compare-runtime')
    assert seen['local']==seen['runtime']
    if workflow=='match':assert first.recommendations==second.recommendations
    else:
        assert first['payload']==second['payload']
        assert first['plan']['target_partner_id'] is None and second['plan']['target_partner_id'] is None


def test_all_61_candidates_and_synonym_partner_match_local_input(prepared,transport,monkeypatch):
    for i in range(59):make_partner('candidate-'+str(i),'RAG普通候选'+str(i))
    make_partner('zz-semantic','企业知识检索伙伴')
    with get_db() as conn:
        conn.execute("UPDATE partners SET intro='RAG演示经验'")
        conn.execute("UPDATE partners SET intro='检索增强生成与企业知识库交付；仅限国内',capabilities='' WHERE id='zz-semantic'")
    seen={'local':[],'runtime':[]};which='local'
    def complete(config,messages,schema):
        stage=schema['title'];body=json.loads(messages[-1]['content']);seen[which].append((stage,body))
        if stage=='MatchUnderstanding':return '{"in_scope":true,"facts":{"technicalNeeds":"RAG"}}'
        if stage=='InitialSelection':
            assert len(body['partners'])==61
            target=next(p for p in body['partners'] if p['partnerId']=='zz-semantic')
            assert 'RAG' not in json.dumps(target,ensure_ascii=False)
            return '{"candidates":[{"partnerId":"zz-semantic","verificationFocus":"知识库交付边界"}]}'
        return answer('zz-semantic','企业知识检索伙伴')
    monkeypatch.setattr(development_model,'completion',complete);transport['complete']=complete
    for executor in ['local','runtime']:
        which=executor;monkeypatch.setenv('BANFEI_MATCH_EXECUTOR',executor)
        result=match.match_partners(match.MatchRequest(requirement='寻找RAG交付伙伴'),prepared[0])
        assert result.recommendations[0].partnerId=='zz-semantic'
    assert seen['local']==seen['runtime']


def test_provider_checks_actual_endpoint_even_after_handshake(monkeypatch):
    p=packet(uuid.uuid4())
    monkeypatch.setenv('BANFEI_RUNTIME_MODEL_NAME','synthetic')
    monkeypatch.setenv('BANFEI_RUNTIME_MODEL_URL','https://other-provider.invalid/v1')
    monkeypatch.setenv('BANFEI_RUNTIME_MODEL_KEY','synthetic-only')
    def forbidden(*args,**kwargs):raise AssertionError('Must reject before provider client')
    monkeypatch.setattr(httpx,'AsyncClient',forbidden)
    from backend.agent_runtime.diagnostics import StageFailure
    with pytest.raises(StageFailure) as error:asyncio.run(REAL_COMPLETION(p,lambda *_:None))
    assert error.value.runtime_diagnostic == {
        'reason_code':'model_configuration_invalid','error_type':'ValueError','retryable':False}


def test_runtime_waits_and_deduplicates_retry_grants(monkeypatch):
    import time
    key='synthetic-grant-test-01234567890123456789'
    monkeypatch.setenv('BANFEI_RUNTIME_SHARED_KEY',key)
    calls=[]
    async def timeout(packet,progress):calls.append(1);raise httpx.ReadTimeout('synthetic')
    monkeypatch.setattr(provider,'completion',timeout)
    app=server.create_app()
    with TestClient(app) as client:
        p=packet(app.state.incarnation)
        p=p.model_copy(update={'model':p.model.model_copy(update={'timeout_retries':5})})
        headers={'X-Banfei-Runtime-Key':key,'X-Hw-Agentarts-Session-Id':str(p.session_id)}
        path='/jobs/'+str(p.operation_id)
        assert client.post('/jobs',headers=headers,json=p.model_dump(mode='json')).status_code==202
        for _ in range(100):
            if client.get(path,headers=headers).json()['status']=='awaiting_retry':break
            time.sleep(.005)
        time.sleep(.03);assert len(calls)==1
        second=p.model_copy(update={'operation_id':uuid.uuid4()})
        assert client.post('/jobs',headers=headers,json=second.model_dump(mode='json')).status_code==409
        grant={'incarnation':str(p.incarnation),'after_attempt':1}
        other={**headers,'X-Hw-Agentarts-Session-Id':str(uuid.uuid4())}
        assert client.post(path+'/retry',headers=other,json=grant).status_code==404
        assert client.post(path+'/retry',headers=headers,json={**grant,'after_attempt':2}).status_code==409
        assert client.post(path+'/retry',headers=headers,json={**grant,'incarnation':str(uuid.uuid4())}).status_code==409
        assert client.post(path+'/retry',headers=headers,json=grant).status_code==202
        assert client.post(path+'/retry',headers=headers,json=grant).status_code==202
        for _ in range(100):
            if len(calls)==2:break
            time.sleep(.005)
        assert len(calls)==2
        client.delete(path,headers=headers)
        assert client.post(path+'/retry',headers=headers,json={**grant,'after_attempt':2}).status_code==409


@pytest.mark.parametrize('workflow',['match','development'])
def test_non_timeout_failure_is_not_retried(prepared,provider_transport,workflow):
    async def fail(request,payload):raise httpx.ConnectError('synthetic transport failure',request=request)
    provider_transport['network_hook']=fail
    run_workflow(workflow,prepared,success=False)
    assert len(provider_transport['network_calls'])==1 and provider_transport['retry_posts']==[]

@pytest.mark.parametrize('executor',['local','runtime'])
def test_budget_failure_does_not_drop_candidates(prepared,transport,monkeypatch,executor):
    from backend.app import partner_match_context
    from backend.app.task_failures import MatchInputBudgetError
    for i in range(60):make_partner('budget-'+str(i),'同义候选'+str(i))
    observed=[]
    def reject(config,messages,schema,*args):
        if schema['title']=='InitialSelection':
            ids={p['partnerId'] for p in json.loads(messages[-1]['content'])['partners']}
            observed.append(ids)
            raise MatchInputBudgetError('Synthetic full candidate input exceeds budget')
        return original(config,messages,schema,*args)
    original=partner_match_context.checked_config
    monkeypatch.setattr(partner_match_context,'checked_config',reject)
    def understanding(config,messages,schema):
        assert schema['title']=='MatchUnderstanding'
        return '{"in_scope":true,"facts":{"technicalNeeds":"知识库"}}'
    monkeypatch.setattr(development_model,'completion',understanding)
    transport['complete']=understanding
    monkeypatch.setenv('BANFEI_MATCH_EXECUTOR',executor)
    with pytest.raises(HTTPException):match.match_partners(match.MatchRequest(requirement='知识库交付'),prepared[0])
    assert observed and all(len(ids)==61 for ids in observed)
    assert all(ids==observed[0] for ids in observed)
    assert all(p['stage']=='understanding' for p in transport['packets'])
    with get_db() as conn:
        row=conn.execute('SELECT task_status,recommendations_json FROM match_records').fetchone()
        assert row['task_status']=='failed' and json.loads(row['recommendations_json'])==[]
