"""Synthetic PostgreSQL + real ASGI Runtime transport, separate from legacy-only regressions."""
import asyncio,copy,json,uuid
import httpx,pytest
from fastapi.testclient import TestClient
from backend.agent_runtime import server,provider
from backend.agent_runtime.contracts import StageRequest,ModelOptions,digest,source_manifest,model_route
from backend.agent_runtime.workflows import messages_for,validate_output,validate_budget
from backend.app import runtime_bridge as bridge,development_lifecycle as life,development_engine as engine,development_views as views
from backend.app.database import get_db
from backend.app.development_types import Submit,DevelopmentRequest,Conversation
from backend.app.routers import match
from .test_development_lifecycle import prepared,plan
from .test_unified_flow import unified,generated
from .test_partner_match_stages import answer
from .support.legacy_development import legacy_confirmed

@pytest.fixture
def transport(monkeypatch,prepared):
    from backend.app.model_resolver import resolve_model_record,model_config_from_record
    selected=model_config_from_record(resolve_model_record("partner_development"))
    monkeypatch.setenv("BANFEI_RUNTIME_MODEL_URL",selected.base_url)
    monkeypatch.setenv("BANFEI_RUNTIME_MODEL_NAME",selected.model)
    monkeypatch.setenv("BANFEI_RUNTIME_MODEL_KEY","synthetic-provider-key")
    for key,value in {'BANFEI_MATCH_EXECUTOR':'runtime','BANFEI_DEVELOPMENT_EXECUTOR':'runtime',
      'BANFEI_RUNTIME_URL':'http://127.0.0.1:19081','BANFEI_RUNTIME_LOCAL_TEST':'1',
      'BANFEI_RUNTIME_SHARED_KEY':'synthetic-runtime-key-01234567890123456789','BANFEI_RUNTIME_POLL_SECONDS':'0.001'}.items():monkeypatch.setenv(key,value)
    apps={};state={'packets':[],'posts':0,'calls':[],'fault':None,'complete':None,'retry_posts':[]}
    async def complete(packet,progress):
        state['calls'].append(packet.stage);progress(1)
        await asyncio.sleep(.001)
        messages,schema=messages_for(packet)
        if state['complete']:return state['complete']({'id':'synthetic-runtime'},messages,schema)
        if packet.workflow=='development':
            from .support.development_mock import response
            return json.dumps(response(messages),ensure_ascii=False)
        if packet.stage=='understanding':return '{"in_scope":true,"facts":{"technicalNeeds":"数据库迁移"}}'
        if packet.stage=='initial_selection':return '{"candidates":[{"partnerId":"partner-1","verificationFocus":"迁移能力与交付边界"}]}'
        return answer()
    monkeypatch.setattr(provider,'completion',complete)
    def client(session):
        if session not in apps:apps[session]=TestClient(server.create_app()).__enter__()
        return apps[session]
    class Adapter:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def request(self,method,url,headers,**kwargs):
            session=headers['X-Hw-Agentarts-Session-Id'];path=url.removeprefix('http://127.0.0.1:19081')
            response=client(session).request(method,path,headers=headers,**kwargs)
            packet=kwargs.get('json')
            if packet and path.endswith('/retry'):
                state['retry_posts'].append(copy.deepcopy(packet))
                if state.get('drop_retry_ack'):
                    state['drop_retry_ack']=False
                    raise httpx.ReadError('synthetic retry lost acknowledgement')
            if packet and path=='/jobs':
                state['posts']+=1;state['packets'].append(copy.deepcopy(packet))
                fault=state['fault']
                if fault=='drop_ack':state['fault']=None;raise httpx.ReadError('synthetic lost acknowledgement')
                if fault=='runtime_restart':
                    apps[session].__exit__(None,None,None);apps[session]=TestClient(server.create_app()).__enter__();raise httpx.ReadError('synthetic Runtime restart')
                if fault=='vm_restart':
                    if packet['workflow']=='development':life.recover(startup=True)
                    else:
                        from backend.app.database import recover_stale_tasks
                        recover_stale_tasks(startup=True)
                if fault=='revoke':
                    with get_db() as conn:conn.execute("UPDATE partners SET status='disabled' WHERE id='partner-1'")
            if state['fault']=='wrong_run' and '/jobs' in path:
                data=response.json();data['run_id']=str(uuid.uuid4());return httpx.Response(response.status_code,json=data,request=response.request)
            if state['fault']=='out_of_order' and method=='GET' and '/jobs/' in path:
                data=response.json();data.update(status='accepted',attempt=-1);return httpx.Response(200,json=data,request=response.request)
            return response
        def post(self,url,**kwargs):return self.request('POST',url,**kwargs)
        def get(self,url,**kwargs):return self.request('GET',url,**kwargs)
        def delete(self,url,**kwargs):return self.request('DELETE',url,**kwargs)
    monkeypatch.setattr(bridge,'client_for',Adapter)
    yield state
    for c in apps.values():c.__exit__(None,None,None)


def test_both_flows_execute_through_runtime_and_persist(prepared,transport):
    user=prepared[0]
    result=match.match_partners(match.MatchRequest(requirement='需要数据库迁移伙伴'),user)
    assert result.taskStatus=='ready'
    accepted=life.create(Submit(submission_id='runtime-no-partner',request=DevelopmentRequest(development_direction='数据库迁移课程与实验')),user)
    engine.execute(accepted['run_id']);detail=views.detail(accepted['plan_id'],user)
    assert detail['payload'] and detail['payload']['target_partner_id'] is None,detail['runs']
    assert transport['calls']==['understanding','initial_selection','detailed_review','analyze','plan']
    packets=transport['packets'];assert len({p['session_id'] for p in packets})==2
    for packet in packets:
        assert len({packet['task_id'],packet['run_id'],packet['session_id']})==3
        assert 'api_key' not in json.dumps(packet) and 'synthetic-runtime-key' not in json.dumps(packet)
        assert packet['sources']==[s.model_dump() for s in source_manifest(packet['data'])]
    with get_db() as conn:
        saved=[json.loads(r[0]) for r in conn.execute("SELECT value FROM app_metadata WHERE key LIKE 'runtime_stage:%'")]
    assert len(saved)==5 and all(s['status']=='completed' for s in saved)


def test_runtime_explanation_patch_current_confirmed_and_idempotency(unified,transport):
    transport['complete']=unified[2]
    accepted,detail=generated(unified);user=unified[0][0];pid=accepted['plan_id'];base=detail['plan']['current_version_id']
    legacy_confirmed(pid,base,user)
    explained=views.converse(pid,Conversation(submission_id='runtime-explain',based_on_version_id=base,message='为什么推荐第二个实验？'),user)
    engine.execute(explained['run_id']);assert plan(pid)['current_version_id']==base
    assert len(views.detail(pid,user)['versions'])==1
    body=Conversation(submission_id='runtime-patch',based_on_version_id=base,message='只换第二个实验')
    changed=views.converse(pid,body,user);engine.execute(changed['run_id']);after=views.detail(pid,user)
    assert after['payload']['stages'][0]['items'][1]['source_id']=='unified-lab-3',after['runs']
    assert after['payload']['stages'][0]['items'][0]==detail['payload']['stages'][0]['items'][0]
    assert after['payload']['answer']==detail['payload']['answer']
    assert plan(pid)['confirmed_version_id']==base and plan(pid)['current_version_id']!=base
    before=transport['posts'];engine.execute(changed['run_id']);assert transport['posts']==before
    assert len(after['versions'])==2


def test_lost_acknowledgement_queries_without_resubmitting(prepared,transport):
    transport['fault']='drop_ack'
    accepted=life.create(Submit(submission_id='lost-ack',request=prepared[3]),prepared[0]);engine.execute(accepted['run_id'])
    assert views.detail(accepted['plan_id'],prepared[0])['payload']
    assert transport['posts']==2 and transport['calls']==['analyze','plan']


@pytest.mark.parametrize('fault',['wrong_run','out_of_order','revoke','runtime_restart','vm_restart'])
@pytest.mark.parametrize('workflow',['development','match'])
def test_faults_never_commit_a_version(prepared,transport,fault,workflow):
    transport['fault']=fault
    if workflow=='development':
        accepted=life.create(Submit(submission_id='fault-'+fault,request=prepared[3]),prepared[0]);engine.execute(accepted['run_id'])
        assert plan(accepted['plan_id'])['current_version_id'] is None
    else:
        from fastapi import HTTPException
        with pytest.raises(HTTPException):match.match_partners(match.MatchRequest(requirement='数据库迁移'),prepared[0])
        with get_db() as conn:
            row=conn.execute('SELECT task_status,recommendations_json FROM match_records').fetchone()
        assert row['task_status']=='failed' and json.loads(row['recommendations_json'])==[]
    with get_db() as conn:assert conn.execute('SELECT count(*) FROM development_versions').fetchone()[0]==0
    assert transport['posts']==1


def packet(incarnation):
    data={'requirement':'合成数据库迁移需求','standard_tags':[]}
    return StageRequest(task_id=uuid.uuid4(),run_id=uuid.uuid4(),session_id=uuid.uuid4(),operation_id=uuid.uuid4(),
      incarnation=incarnation,workflow='match',stage='understanding',snapshot=digest(data),sources=source_manifest(data),
      model_fingerprint='a'*64,input_token_budget=16000,data=data,
      model=ModelOptions(provider_route=model_route('https://example.test/v1','synthetic'),name='synthetic',temperature=.3,top_p=1,max_tokens=1000,timeout_seconds=1,timeout_retries=0))


def test_runtime_protocol_auth_dedup_session_restart_and_budget(monkeypatch):
    monkeypatch.setenv('BANFEI_RUNTIME_SHARED_KEY','synthetic-key-0123456789012345678901234')
    count=[]
    async def complete(request,progress):
        count.append(1);await asyncio.sleep(.01);return '{"in_scope":false}'
    monkeypatch.setattr(provider,'completion',complete)
    app=server.create_app()
    with TestClient(app) as client:
        p=packet(app.state.incarnation);headers={'X-Banfei-Runtime-Key':'synthetic-key-0123456789012345678901234','X-Hw-Agentarts-Session-Id':str(p.session_id)}
        assert client.post('/jobs',json=p.model_dump(mode='json')).status_code==401
        assert client.post('/jobs',headers=headers,json=p.model_dump(mode='json')).status_code==202
        assert client.post('/jobs',headers=headers,json=p.model_dump(mode='json')).status_code==202
        wrong=p.model_copy(update={'snapshot':'b'*64});assert client.post('/jobs',headers=headers,json=wrong.model_dump(mode='json')).status_code==422
        changed=p.model_copy(update={'input_token_budget':17000});assert client.post('/jobs',headers=headers,json=changed.model_dump(mode='json')).status_code==409
        other={**headers,'X-Hw-Agentarts-Session-Id':str(uuid.uuid4())};assert client.get('/jobs/'+str(p.operation_id),headers=other).status_code==404
        different=p.model_copy(update={'run_id':uuid.uuid4(),'operation_id':uuid.uuid4()});assert client.post('/jobs',headers=headers,json=different.model_dump(mode='json')).status_code==409
        with TestClient(server.create_app()) as restarted:
            assert restarted.post('/jobs',headers=headers,json=p.model_dump(mode='json')).status_code==409
            assert restarted.get('/jobs/'+str(p.operation_id),headers=headers).status_code==404
        assert len(count)==1
        with pytest.raises(ValueError):validate_budget(p,100)


def test_runtime_is_database_free_and_mode_is_fail_closed(monkeypatch):
    import subprocess,sys,os
    env={k:v for k,v in os.environ.items() if k not in ('DATABASE_URL','BANFEI_TEST_DATABASE_URL','JWT_SECRET_KEY','BANFEI_IDENTITY_ENCRYPTION_KEY')}
    check=subprocess.run([sys.executable,'-B','-c',"import sys; import backend.agent_runtime.server; assert 'backend.app.database' not in sys.modules"],env=env,capture_output=True,text=True)
    assert check.returncode==0,check.stderr
    monkeypatch.setenv('BANFEI_MATCH_EXECUTOR','typo')
    with pytest.raises(ValueError):bridge.mode('match')
    monkeypatch.setenv('BANFEI_RUNTIME_URL','https://example.com/runtime');monkeypatch.delenv('BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED',raising=False)
    with pytest.raises(ValueError):bridge.endpoint()


@pytest.fixture
def wire_runtime(monkeypatch,tmp_path):
    """Actual child Runtime + actual loopback model HTTP, no ASGI transport substitution."""
    import os,socket,subprocess,sys,threading,time
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    from backend.tests.support.development_mock import response as development_response
    class WireCalls(list):pass
    calls=WireCalls();calls.delay=0
    class ModelHandler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            messages=payload['messages'];system=messages[0]['content'];calls.append(system.split('。')[0])
            if calls.delay:time.sleep(calls.delay)
            if system.startswith('partner_development:'):result=json.dumps(development_response(messages),ensure_ascii=False)
            elif 'MatchUnderstanding' in system:result='{"in_scope":true,"facts":{"technicalNeeds":"数据库迁移"}}'
            elif 'InitialSelection' in system:result='{"candidates":[{"partnerId":"partner-1","verificationFocus":"数据库迁移"}]}'
            else:result=answer()
            data=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':result}}]}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers()
            try:self.wfile.write(data)
            except BrokenPipeError:pass
    model=ThreadingHTTPServer(('127.0.0.1',0),ModelHandler);thread=threading.Thread(target=model.serve_forever,daemon=True);thread.start()
    with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    key='wire-only-synthetic-key-01234567890123456789'
    from backend.app.model_resolver import resolve_model_record
    selected=resolve_model_record('partner_development')
    with get_db() as conn:
        conn.execute('UPDATE model_configs SET base_url=? WHERE id=?',('http://127.0.0.1:'+str(model.server_port),selected['id']))
    env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL','PYTHONPATH')}
    env.update(PYTHONDONTWRITEBYTECODE='1',BANFEI_RUNTIME_SHARED_KEY=key,BANFEI_RUNTIME_LOCAL_TEST='1',
      BANFEI_RUNTIME_MODEL_URL='http://127.0.0.1:'+str(model.server_port),BANFEI_RUNTIME_MODEL_NAME=selected['model_name'],BANFEI_RUNTIME_MODEL_KEY='synthetic-model-only')
    log=(tmp_path/'runtime-process.log').open('w')
    child=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.agent_runtime.server:app','--host','127.0.0.1','--port',str(port),'--workers','1','--no-access-log'],env=env,stdout=log,stderr=log)
    try:
        for attempt in range(100):
            if child.poll() is not None:raise AssertionError('Runtime child exited')
            try:
                if httpx.get(f'http://127.0.0.1:{port}/ping',trust_env=False).status_code==200:break
            except httpx.ConnectError:pass
            time.sleep(.03)
        else:raise AssertionError('Runtime startup timed out')
        for k,v in {'BANFEI_RUNTIME_URL':f'http://127.0.0.1:{port}','BANFEI_RUNTIME_SHARED_KEY':key,
          'BANFEI_RUNTIME_LOCAL_TEST':'1','BANFEI_RUNTIME_POLL_SECONDS':'.01','BANFEI_MATCH_EXECUTOR':'runtime','BANFEI_DEVELOPMENT_EXECUTOR':'runtime'}.items():monkeypatch.setenv(k,v)
        def restart():
            nonlocal child
            child.kill();child.wait(timeout=5)
            child=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.agent_runtime.server:app','--host','127.0.0.1','--port',str(port),'--workers','1','--no-access-log'],env=env,stdout=log,stderr=log)
            for _ in range(100):
                try:
                    if httpx.get(f'http://127.0.0.1:{port}/ping',trust_env=False).status_code==200:return
                except httpx.ConnectError:pass
                time.sleep(.03)
            raise AssertionError('Restart failed')
        calls.provider_route=model_route(env['BANFEI_RUNTIME_MODEL_URL'],env['BANFEI_RUNTIME_MODEL_NAME'])
        calls.restart=restart;calls.base=f'http://127.0.0.1:{port}';calls.key=key
        yield calls
    finally:
        child.terminate()
        try:child.wait(timeout=5)
        except subprocess.TimeoutExpired:child.kill();child.wait()
        model.shutdown();model.server_close();thread.join(timeout=2);log.close()


@pytest.mark.parametrize('workflow',['match','development'])
def test_real_http_runtime_process_and_synthetic_model(prepared,wire_runtime,workflow):
    if workflow=='match':
        result=match.match_partners(match.MatchRequest(requirement='需要数据库迁移伙伴'),prepared[0])
        assert result.taskStatus=='ready' and len(wire_runtime)==3
    else:
        accepted=life.create(Submit(submission_id='wire-development',request=DevelopmentRequest(development_direction='数据库迁移课程与实验')),prepared[0])
        engine.execute(accepted['run_id']);detail=views.detail(accepted['plan_id'],prepared[0])
        assert detail['payload'] and detail['payload']['target_partner_id'] is None,detail['runs']
        assert len(wire_runtime)==2


@pytest.mark.parametrize('method',['lease','cancel'])
def test_runtime_cancels_orphaned_model_work(monkeypatch,method):
    import time,threading
    monkeypatch.setenv('BANFEI_RUNTIME_SHARED_KEY','lease-test-key-0123456789012345678901234')
    started=threading.Event();stopped=threading.Event()
    async def slow(request,progress):
        started.set()
        try:await asyncio.sleep(30)
        finally:stopped.set()
    monkeypatch.setattr(provider,'completion',slow)
    app=server.create_app()
    with TestClient(app) as client:
        p=packet(app.state.incarnation);headers={'X-Banfei-Runtime-Key':'lease-test-key-0123456789012345678901234','X-Hw-Agentarts-Session-Id':str(p.session_id)}
        assert client.post('/jobs',headers=headers,json=p.model_dump(mode='json')).status_code==202
        assert started.wait(2)
        if method=='lease':app.state.jobs[str(p.operation_id)]['_lease']=time.monotonic()-1
        else:assert client.delete('/jobs/'+str(p.operation_id),headers=headers).status_code==200
        assert stopped.wait(3)
        result=client.get('/jobs/'+str(p.operation_id),headers=headers).json()
        assert result['status'] in ('failed','interrupted') and 'result' not in result


@pytest.mark.parametrize('fault',['runtime_restart','vm_restart','wrong_run'])
def test_runtime_failure_preserves_current_and_historical_confirmed(unified,transport,fault):
    transport['complete']=unified[2]
    accepted,detail=generated(unified);pid=accepted['plan_id'];base=detail['plan']['current_version_id'];user=unified[0][0]
    legacy_confirmed(pid,base,user);transport['fault']=fault
    changed=views.converse(pid,Conversation(submission_id='failed-edit-'+fault,based_on_version_id=base,message='只换第二个实验'),user)
    engine.execute(changed['run_id'])
    assert plan(pid)['current_version_id']==base and plan(pid)['confirmed_version_id']==base
    after=views.detail(pid,user);assert len(after['versions'])==1 and after['payload']==detail['payload']



def test_actual_runtime_process_kill_rejects_old_operation(prepared,wire_runtime):
    import time
    wire_runtime.delay=1
    session=str(uuid.uuid4());headers={'X-Banfei-Runtime-Key':wire_runtime.key,'X-Hw-Agentarts-Session-Id':session}
    with httpx.Client(base_url=wire_runtime.base,headers=headers,trust_env=False) as client:
        incarnation=client.get('/runtime-info').json()['incarnation']
        p=packet(incarnation).model_copy(update={'session_id':uuid.UUID(session),'model':packet(incarnation).model.model_copy(update={'provider_route':wire_runtime.provider_route,'name':__import__('backend.app.model_resolver',fromlist=['resolve_model_record']).resolve_model_record('partner_development')['model_name']})})
        assert client.post('/jobs',json=p.model_dump(mode='json')).status_code==202
        for _ in range(100):
            if wire_runtime:break
            time.sleep(.01)
        assert len(wire_runtime)==1
        wire_runtime.restart()
        assert client.get('/jobs/'+str(p.operation_id)).status_code==404
        assert client.post('/jobs',json=p.model_dump(mode='json')).status_code==409
        assert len(wire_runtime)==1


def test_actual_vm_process_kill_preserves_pg_and_rejects_late_result(prepared,wire_runtime):
    import os,subprocess,sys,time
    wire_runtime.delay=2
    accepted=life.create(Submit(submission_id='vm-kill-wire',request=prepared[3]),prepared[0])
    child=subprocess.Popen([sys.executable,'-B','-c',"from backend.app.development_engine import execute; execute("+repr(accepted['run_id'])+")"],env=dict(os.environ),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(200):
            if wire_runtime:break
            if child.poll() is not None:raise AssertionError('VM worker exited before remote request')
            time.sleep(.02)
        assert wire_runtime
        child.kill();child.wait(timeout=5)
        life.recover(startup=True)
        with get_db() as conn:
            run=conn.execute('SELECT status FROM development_runs WHERE id=?',(accepted['run_id'],)).fetchone()
            metadata=json.loads(conn.execute('SELECT value FROM app_metadata WHERE key=?',('runtime_stage:'+accepted['run_id']+':analyze',)).fetchone()[0])
        assert run['status']=='interrupted' and metadata['status']=='interrupted'
        time.sleep(2.1)
        engine.execute(accepted['run_id'])
        assert plan(accepted['plan_id'])['current_version_id'] is None
        with get_db() as conn:assert conn.execute('SELECT count(*) FROM development_versions').fetchone()[0]==0
        assert len(wire_runtime)==1
    finally:
        if child.poll() is None:child.kill();child.wait(timeout=5)



def test_runtime_health_requires_model_configuration(monkeypatch):
    monkeypatch.setenv('BANFEI_RUNTIME_SHARED_KEY','health-key-012345678901234567890123456789')
    monkeypatch.delenv('BANFEI_RUNTIME_MODEL_KEY',raising=False)
    with TestClient(server.create_app()) as client:
        assert client.get('/ping').status_code==503
        monkeypatch.setenv('BANFEI_RUNTIME_MODEL_KEY','synthetic')
        monkeypatch.setenv('BANFEI_RUNTIME_MODEL_URL','https://example.com/v1')
        monkeypatch.setenv('BANFEI_RUNTIME_MODEL_NAME','synthetic')
        assert client.get('/ping').json()['status']=='Healthy'


@pytest.mark.parametrize('partner_count',[1,12,179])
@pytest.mark.parametrize('saved_limit',[512,131072])
def test_matching_stages_use_saved_limits_and_remaining_context(prepared,transport,partner_count,saved_limit):
    from .conftest import make_partner
    from backend.app import partner_match_context as context
    for index in range(2,partner_count+1):make_partner('partner-'+str(index),'合成伙伴'+str(index))
    with get_db() as conn:conn.execute('UPDATE model_configs SET max_tokens=? WHERE enabled=1',(saved_limit,))
    result=match.match_partners(match.MatchRequest(requirement='合成数据库迁移需求'),prepared[0])
    assert result.taskStatus=='ready'
    packets={p['stage']:p for p in transport['packets']}
    initial=packets['initial_selection']
    assert len(initial['data']['partners'])==partner_count
    selected=initial['model']['max_tokens']
    assert 0<selected<=saved_limit
    if saved_limit==512:assert selected==512
    else:assert 2048<selected<=context.UNKNOWN_CONTEXT_CEILING
    assert packets['understanding']['model']['max_tokens']==saved_limit
    detail_output=packets['detailed_review']['model']['max_tokens']
    assert 0<detail_output<=saved_limit
    if saved_limit==512:assert detail_output==512
    else:assert 8192<detail_output<=context.UNKNOWN_CONTEXT_CEILING
    for p in packets.values():
        assert p['model']['temperature']==initial['model']['temperature']
        assert p['model']['top_p']==initial['model']['top_p']
        assert p['model']['timeout_seconds']==300
        assert p['model']['timeout_retries']==3
    assert transport['calls']==['understanding','initial_selection','detailed_review']


def test_initial_runtime_full_request_budget_preserves_qa_input(prepared,transport,monkeypatch):
    from .conftest import make_partner
    from backend.app import partner_match_context as context
    for index in range(2,13):make_partner('partner-'+str(index),'合成伙伴')
    with get_db() as conn:
        conn.execute("UPDATE model_configs SET base_url='https://api.deepseek.com',model_name='deepseek-flash',max_tokens=131072 WHERE enabled=1")
    monkeypatch.setenv('BANFEI_RUNTIME_MODEL_URL','https://api.deepseek.com')
    monkeypatch.setenv('BANFEI_RUNTIME_MODEL_NAME','deepseek-flash')
    compact=[{'partnerId':'partner-'+str(i),'name':'合成伙伴','capabilities':'合成能力',
        'industries':'制造','regions':'广东','summary':'','intro':'甲'*3600,
        'evidenceState':'资料有限，待核实','visibleCaseCount':0,'visibleDeliverableCount':0} for i in range(1,13)]
    monkeypatch.setattr(context,'compact_candidates',lambda _:copy.deepcopy(compact))
    result=match.match_partners(match.MatchRequest(requirement='合成数据库迁移需求'),prepared[0])
    assert result.taskStatus=='ready'
    packet=next(p for p in transport['packets'] if p['stage']=='initial_selection')
    assert packet['data']['partners']==compact
    full=validate_budget(StageRequest.model_validate(packet))
    byte_count=len(json.dumps(full,ensure_ascii=False).encode('utf-8'))
    assert packet['model']['max_tokens']==bridge.RUNTIME_INPUT_BUDGET-byte_count
    assert 2048<packet['model']['max_tokens']<131072
    assert transport['calls']==['understanding','initial_selection','detailed_review']


@pytest.mark.parametrize('large_field',['summary','intro','name'])
def test_runtime_budget_is_rechecked_inside_existing_input_compaction(prepared,transport,monkeypatch,large_field):
    from .conftest import make_partner
    from backend.app import partner_match_context as context
    from fastapi import HTTPException
    for index in range(2,13):make_partner('partner-'+str(index),'合成伙伴')
    with get_db() as conn:conn.execute('UPDATE model_configs SET max_tokens=131072 WHERE enabled=1')
    # Tighten the same bridge budget in this isolated test to exercise the
    # input-only failure path before any initial-selection dispatch.
    monkeypatch.setattr(bridge,'RUNTIME_INPUT_BUDGET',12000)
    compact=[{'partnerId':'partner-'+str(i),'name':'合成伙伴','capabilities':'',
        'industries':'','regions':'','summary':'','intro':'数据库迁移经验。',
        'evidenceState':'资料待核实','visibleCaseCount':0,'visibleDeliverableCount':0} for i in range(1,13)]
    for item in compact:item[large_field]='数据库迁移经验。\n'*90
    monkeypatch.setattr(context,'compact_candidates',lambda _:copy.deepcopy(compact))
    attempts=[];original=context.checked_config
    def checked(config,messages,schema,*args):
        if schema['title']=='InitialSelection':attempts.append(json.loads(messages[-1]['content']))
        return original(config,messages,schema,*args)
    monkeypatch.setattr(context,'checked_config',checked)
    if large_field=='name':
        with pytest.raises(HTTPException):match.match_partners(match.MatchRequest(requirement='数据库迁移'),prepared[0])
        assert transport['calls']==['understanding']
        assert len(attempts)==3
        with get_db() as conn:assert conn.execute('SELECT task_status FROM match_records').fetchone()[0]=='failed'
    else:
        result=match.match_partners(match.MatchRequest(requirement='数据库迁移'),prepared[0])
        assert result.taskStatus=='ready'
        assert len(attempts)==(2 if large_field=='summary' else 3)
        packet=next(p for p in transport['packets'] if p['stage']=='initial_selection')
        assert packet['data']==attempts[-1]
        full=validate_budget(StageRequest.model_validate(packet))
        used=len(json.dumps(full,ensure_ascii=False).encode('utf-8'))
        assert 0<packet['model']['max_tokens']<=12000-used
        assert packet['input_token_budget']==12000
        assert all(len(p[large_field])<len(compact[0][large_field]) for p in packet['data']['partners'])
        assert transport['calls']==['understanding','initial_selection','detailed_review']
    expected={p['partnerId'] for p in compact}
    assert all({p['partnerId'] for p in a['partners']}==expected for a in attempts)


@pytest.mark.parametrize('saved_limit',[131072,131073,384000])
def test_large_saved_output_limit_respects_all_stage_wire_protocol(prepared,transport,monkeypatch,saved_limit):
    with get_db() as conn:
        conn.execute("UPDATE model_configs SET base_url='https://api.deepseek.com',model_name='deepseek-flash',max_tokens=? WHERE enabled=1",(saved_limit,))
    monkeypatch.setenv('BANFEI_RUNTIME_MODEL_URL','https://api.deepseek.com')
    monkeypatch.setenv('BANFEI_RUNTIME_MODEL_NAME','deepseek-flash')
    result=match.match_partners(match.MatchRequest(requirement='合成数据库迁移需求'),prepared[0])
    assert result.taskStatus=='ready'
    packets={p['stage']:p for p in transport['packets']}
    assert packets['initial_selection']['model']['max_tokens']==131072
    assert packets['understanding']['model']['max_tokens']==131072
    assert packets['detailed_review']['model']['max_tokens']==131072
    for p in packets.values():validate_budget(StageRequest.model_validate(p))
    assert transport['calls']==['understanding','initial_selection','detailed_review']
    with get_db() as conn:assert conn.execute('SELECT max_tokens FROM model_configs WHERE enabled=1').fetchone()[0]==saved_limit
