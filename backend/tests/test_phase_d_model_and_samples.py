"""Synthetic acceptance samples and loopback-only supplier compatibility tests."""
import copy
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from backend.app import development_engine as engine, development_lifecycle as life, development_model as model, development_views as views, enablement
from backend.app.database import get_db
from backend.app.development_types import Submit, Revise
from backend.tests.conftest import make_partner, make_user
from backend.tests.test_development_lifecycle import prepared, plan
from backend.tests.test_development_engine import scenario, execute, CANARY
from backend.tests.test_enablement import grant, published


def structured(messages):
    from backend.tests.support.development_mock import response
    return response(messages)


def add_resource(admin, tag, name):
    metadata=enablement.ResourceMetadata(resource_type='course',title=name,summary='固定验收合成资源',
        target_capability=name,audience='工程师',source_platform='合成平台',source_url='https://example.com/synthetic',capability_tag_ids=[tag])
    row=enablement.save('resource',name,enablement.ResourceSave(base_revision=0,metadata=metadata),admin['id'])
    return published(grant(row,admin),admin)


# V1.2 semantic and three-owner sample assertions live in test_v12_agent.py.
# Keep all supplier transport/schema/timeout and version-preservation regression below.

@pytest.fixture
def supplier(scenario,monkeypatch):
    state={'mode':'normal','requests':[]}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state['requests'].append(payload)
            mode=state['mode']
            if mode=='slow':time.sleep(.3)
            content=json.dumps(structured(payload['messages']))
            if mode=='markdown':content='```json\n'+content+'\n```'
            elif mode=='empty':content=''
            elif mode=='invalid':content='{invalid'
            elif mode=='enum':content=json.dumps({'target_partner_id':'partner-1','diagnoses':[{'evidence_status':'illegal'}]})
            body=json.dumps({'choices':[{'message':{'content':content}}]}).encode()
            self.send_response(503 if mode=='http_error' else 200);self.send_header('Content-Length',str(len(body)));self.end_headers()
            try:
                if mode=='dribble':
                    self.wfile.write(body[:1]);self.wfile.flush();time.sleep(.2)
                    self.wfile.write(body[1:2]);self.wfile.flush();time.sleep(.4)
                    self.wfile.write(body[2:])
                else:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    with get_db() as conn:config=dict(conn.execute('SELECT * FROM model_configs LIMIT 1').fetchone())
    config.update(base_url=f'http://127.0.0.1:{server.server_port}/v1',api_key='synthetic-only',api_key_source='db')
    monkeypatch.setattr(model,'configuration',lambda:config)
    monkeypatch.setattr(model,'completion',REAL_COMPLETION)
    yield state
    server.shutdown();server.server_close();worker.join(3)

# Capture before scenario replaces it; this is the real adapter, only a loopback test server receives requests.
REAL_COMPLETION=model.completion


@pytest.mark.parametrize('mode',['normal','markdown','empty','invalid','enum','http_error','slow','dribble'])
def test_loopback_supplier_schema_error_timeout_and_retry(scenario,supplier,monkeypatch,mode,caplog,record_property):
    accepted,_,_=execute(scenario);user,_,_,request=scenario[0];pid=accepted['plan_id']
    v1=plan(pid)['current_version_id'];assert v1;views.confirm(pid,v1,user)
    supplier['mode']=mode
    if mode=='slow':monkeypatch.setenv('DEVELOPMENT_MODEL_TIMEOUT_SECONDS','.08')
    if mode=='dribble':monkeypatch.setenv('DEVELOPMENT_MODEL_TIMEOUT_SECONDS','.25')
    second=life.revise(pid,Revise(submission_id='supplier-revise-'+mode,based_on_version_id=v1,instruction='缩短周期',request=request),user)
    started=time.perf_counter();engine.execute(second['run_id']);elapsed=time.perf_counter()-started
    with get_db() as conn:status=conn.execute('SELECT status FROM development_runs WHERE id=?',(second['run_id'],)).fetchone()[0]
    if mode=='normal':assert status=='ready' and plan(pid)['current_version_id']!=v1
    else:
        assert status=='failed' and plan(pid)['current_version_id']==v1
        assert plan(pid)['confirmed_version_id']==v1 and views.transferable(pid,user)['text']
        supplier['mode']='normal';monkeypatch.delenv('DEVELOPMENT_MODEL_TIMEOUT_SECONDS',raising=False)
        retry=life.revise(pid,Revise(submission_id='supplier-retry-'+mode,based_on_version_id=v1,instruction='重试',request=request),user)
        engine.execute(retry['run_id']);assert plan(pid)['current_version_id']!=v1
    if mode=='slow':assert elapsed<2
    if mode=='dribble':assert elapsed<.38
    assert all(r['response_format']['json_schema']['strict'] is True for r in supplier['requests'])
    for boundary in [json.dumps(supplier['requests']),caplog.text,json.dumps(views.transferable(pid,user))]:assert CANARY not in boundary
    record_property('loopback_supplier',json.dumps({'mode':mode,'status':status,'seconds':elapsed,'real_provider_calls':0}))
