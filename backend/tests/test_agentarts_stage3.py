import asyncio,json,uuid
import httpx,pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.app import agent_settings as settings,runtime_bridge as bridge,model_resolver
from backend.app.database import get_db
from backend.app.routers import model_config
from backend.agent_runtime import provider,server
from backend.agent_runtime.contracts import StageRequest,ModelOptions,digest,source_manifest,model_route
from backend.agent_runtime.diagnostics import StageFailure
from backend.business import development
from .test_agent_settings import configure

def cloud_model(name='deepseek-v4.1-flash'):
    return model_config.create_config(model_config.ModelConfigCreate(name='合成代理',baseUrl=provider.PROXY_BASE,modelName=name)).id

def packet(workflow='match',thinking=False):
    data={'requirement':'合成需求','standard_tags':[]}
    return StageRequest(task_id=uuid.uuid4(),run_id=uuid.uuid4(),session_id=uuid.uuid4(),operation_id=uuid.uuid4(),
        incarnation=uuid.uuid4(),workflow=workflow,stage='understanding',snapshot=digest(data),sources=source_manifest(data),
        model_fingerprint='a'*64,input_token_budget=262144,data=data,
        model=ModelOptions(provider_route=model_route(provider.PROXY_BASE,'deepseek-v4.1-flash'),name='deepseek-v4.1-flash',
            thinking=thinking,temperature=.2,top_p=.9,max_tokens=4096,timeout_seconds=17.0,timeout_retries=2))

def test_destination_model_policy_frozen_without_processing_reroute(monkeypatch):
    cloud=cloud_model();first='https://test.huaweicloud-agentarts.com/runtimes/match-a/invocations'
    configure('partner_match',executor='runtime',runtimeUrl=first,modelConfigId=cloud,thinking=False,timeoutSeconds=17)
    with get_db() as conn:frozen=settings.execution(conn,'partner_match',accept=True)
    configure('partner_match',runtimeUrl=first.replace('match-a','match-b'),thinking=True,timeoutSeconds=40)
    monkeypatch.setenv('BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED','1')
    monkeypatch.setenv('BANFEI_MATCH_EXECUTOR','local')
    monkeypatch.setenv('BANFEI_RUNTIME_URL','https://unrelated.invalid')
    with settings.execution_scope(frozen):
        assert bridge.mode('match')=='runtime' and bridge.endpoint('match')[0]==first
        selected=model_resolver.resolve_model_record('partner_match')
        assert selected['_agent_execution']['timeoutSeconds']==17
        assert not model_resolver.model_config_from_record(selected).thinking
        assert model_resolver.model_config_from_record(selected).api_key==''
    with get_db() as conn:
        processing=settings.execution(conn,'processing')
        assert processing['executor']=='local' and processing['runtimeUrl'] is None
        assert processing['modelConfigId']!=cloud
    assert 'api_key' not in json.dumps(frozen)
    with pytest.raises(HTTPException):configure('partner_match',executor='local')
    monkeypatch.delenv('BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED')
    with settings.execution_scope(frozen),pytest.raises(ValueError,match='not approved'):bridge.endpoint('match')

@pytest.mark.parametrize('thinking',[False,True])
def test_provider_uses_selected_maas_parameters_once_without_direct_api(monkeypatch,thinking):
    monkeypatch.setenv('BANFEI_MODEL_PROXY_API_KEY','synthetic-proxy-only')
    monkeypatch.delenv('BANFEI_RUNTIME_MODEL_URL',raising=False)
    calls=[]
    real_client=httpx.AsyncClient
    async def handle(request):
        calls.append(request)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"in_scope":false}'}}]})
    def client(**options):
        assert options['timeout']==17 and options['follow_redirects'] is False and options['trust_env'] is False
        return real_client(transport=httpx.MockTransport(handle),**options)
    monkeypatch.setattr(provider.httpx,'AsyncClient',client)
    progress=[]
    asyncio.run(provider.completion(packet(thinking=thinking),progress.append))
    assert progress==[1] and len(calls)==1
    wire=json.loads(calls[0].content)
    assert str(calls[0].url)==provider.PROXY_BASE+'/chat/completions'
    assert wire['model']=='deepseek-v4.1-flash' and wire['chat_template_kwargs']=={'thinking':thinking}
    assert wire['max_completion_tokens']==4096 and 'max_tokens' not in wire
    assert calls[0].headers['Authorization']=='Bearer synthetic-proxy-only'
    monkeypatch.setenv('BANFEI_RUNTIME_MODEL_URL','https://api.deepseek.com')
    with pytest.raises(StageFailure):asyncio.run(provider.completion(packet(),progress.append))
    assert len(calls)==1

def test_dedicated_runtime_rejects_wrong_workflow_before_model(monkeypatch):
    monkeypatch.setenv('BANFEI_RUNTIME_SHARED_KEY','synthetic-shared-key-01234567890123456789')
    monkeypatch.setenv('BANFEI_MODEL_PROXY_API_KEY','synthetic-proxy')
    monkeypatch.delenv('BANFEI_RUNTIME_MODEL_URL',raising=False)
    async def forbidden(*args):raise AssertionError('Wrong workflow must never invoke provider')
    monkeypatch.setattr(provider,'completion',forbidden)
    with TestClient(server.create_app('development')) as client:
        p=packet();p.incarnation=uuid.UUID(client.app.state.incarnation)
        headers={'X-Banfei-Runtime-Key':'synthetic-shared-key-01234567890123456789','X-Hw-Agentarts-Session-Id':str(p.session_id)}
        info=client.get('/runtime-info',headers=headers).json()
        assert info['workflow']=='development' and info['provider_endpoint']==digest(provider.PROXY_BASE)
        assert client.post('/jobs',headers=headers,json=p.model_dump(mode='json')).status_code==422
        assert not client.app.state.jobs

def test_runtime_and_local_business_contracts_are_identical():
    from backend.agent_runtime import prompts,development_types,match_types,workflows
    from backend.business import development_types as types,matching_types
    assert prompts.development is development.request
    assert development_types.Understanding is types.Understanding
    assert match_types.InitialSelection is matching_types.InitialSelection
    workflows.strong_guard('学完不代表具备独立交付能力。')
    with pytest.raises(StageFailure):workflows.strong_guard('学完即具备独立交付能力。')


def test_cloud_metadata_rejects_local_keys_and_does_not_probe_locally(monkeypatch):
    with pytest.raises(HTTPException):
        model_config.create_config(model_config.ModelConfigCreate(name='blocked',baseUrl=provider.PROXY_BASE,apiKey='synthetic-never-stored'))
    mid=cloud_model()
    out=next(row for row in model_config.list_configs() if row.id==mid)
    assert out.credentialsLocation=='runtime' and not out.apiKeyConfigured
    with pytest.raises(HTTPException):model_config.update_config(mid,model_config.ModelConfigUpdate(apiKey='synthetic-never-stored'))
    monkeypatch.setattr(model_config.development_model,'completion',lambda *args: (_ for _ in ()).throw(AssertionError('No local cloud probe')))
    result=model_config.test_connection(mid)
    assert not result.success and 'Runtime' in result.message
