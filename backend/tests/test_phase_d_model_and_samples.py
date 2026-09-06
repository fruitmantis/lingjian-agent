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
    data=json.loads(messages[-1]['content']);request=data.get('request',data)
    if 'diagnose' in messages[0]['content']:
        return {'target_partner_id':request['target_partner_id'],'diagnoses':[
            {'capability_tag_id':t['capability_tag_id'],'target_requirement':t['requirement'],
             'target_satisfaction':'needs_assessment','evidence_status':'partial','judgment_source':'model_inference',
             'evidence_refs':[],'pending_verifications':['人员基础待核验'],'problem_type':'trainable_gap'} for t in request['targets']]}
    items=[]
    for resource in data['candidates']:
        tag=next(d['capability_tag_id'] for d in data['diagnoses'] if d['capability_tag_id'] in resource['capability_tag_ids'])
        items.append({k:resource[k] for k in ('source_type','source_id','source_version')}|{'capability_tag_id':tag,'reason':'匹配合成目标能力','estimated_hours':2,'note':''})
    return {'target_partner_id':request['target_partner_id'],'stages':[{'title':'分阶段实践','items':items}],
            'limitations':[],'resource_gaps':[] if any(i['source_type']=='lab' for i in items) else ['当前资源库未找到匹配实验']}


def add_resource(admin, tag, name):
    metadata=enablement.ResourceMetadata(resource_type='course',title=name,summary='固定验收合成资源',
        target_capability=name,audience='工程师',source_platform='合成平台',source_url='https://example.com/synthetic',capability_tag_ids=[tag])
    row=enablement.save('resource',name,enablement.ResourceSave(base_revision=0,metadata=metadata),admin['id'])
    return published(grant(row,admin),admin)


def test_fixed_same_partner_different_goals_have_disjoint_capabilities_and_candidates(prepared,monkeypatch,record_property):
    user,_,admin,base=prepared
    with get_db() as conn:tags=[r[0] for r in conn.execute("SELECT id FROM capability_tags WHERE enabled=1 AND name IN ('数据库','盘古大模型') ORDER BY name")]
    assert len(tags)==2
    captured=[]
    def mock(config,messages,schema):
        captured.append(copy.deepcopy(messages));return json.dumps(structured(messages))
    with get_db() as conn:config=dict(conn.execute('SELECT * FROM model_configs LIMIT 1').fetchone())
    monkeypatch.setattr(model,'configuration',lambda:config);monkeypatch.setattr(model,'completion',mock)
    results=[]
    for number,(tag,goal) in enumerate(zip(tags,['数据库迁移','Agent 应用交付'])):
        add_resource(admin,tag,f'synthetic-goal-{number}')
        request=base.model_copy(deep=True);request.development_goal=goal
        request.targets=[base.targets[0].model_copy(update={'capability_tag_id':tag,'requirement':goal})]
        accepted=life.create(Submit(submission_id=f'fixed-goal-{number}',request=request),user);engine.execute(accepted['run_id'])
        detail=views.detail(accepted['plan_id'],user);assert detail['runs'][0]['status']=='ready'
        payload=detail['payload'];diagnosis=payload['diagnoses'][0]
        assert diagnosis['problem_type']=='trainable_gap' and diagnosis['capability_tag_id']==tag
        assert payload['resource_gaps']==['当前资源库未找到匹配实验']
        ids={i['source_id'] for s in payload['stages'] for i in s['items']}
        assert ids=={f'synthetic-goal-{number}'}
        results.append({'goal':goal,'capability':tag,'resource_ids':sorted(ids),'plan_id':accepted['plan_id']})
    assert results[0]['capability']!=results[1]['capability']
    assert not set(results[0]['resource_ids']) & set(results[1]['resource_ids'])
    assert CANARY not in json.dumps(captured)
    record_property('fixed_samples',json.dumps(results,ensure_ascii=False))


def test_three_parallel_plans_keep_distinct_partner_owner_and_resources(prepared,monkeypatch,record_property):
    user,other,admin,base=prepared
    owners=[user,other,make_user('parallel-third')]
    with get_db() as conn:
        tags=[r[0] for r in conn.execute('SELECT id FROM capability_tags WHERE enabled=1 ORDER BY id LIMIT 3')]
        config=dict(conn.execute('SELECT * FROM model_configs LIMIT 1').fetchone())
    barrier=threading.Barrier(3);captured=[];jobs=[]
    def mock(c,m,s):
        if 'diagnose' in m[0]['content']:barrier.wait(timeout=10)
        captured.append(copy.deepcopy(m));return json.dumps(structured(m))
    monkeypatch.setattr(model,'configuration',lambda:config);monkeypatch.setattr(model,'completion',mock)
    for n,owner in enumerate(owners):
        partner=f'parallel-partner-{n}';make_partner(partner)
        add_resource(admin,tags[n],f'parallel-course-{n}')
        # A distinct shared case in each capability pool also exercises case IDs.
        case=f'parallel-case-{n}'
        with get_db() as conn:conn.execute('INSERT INTO cases VALUES (?,?,?,?,?)',(case,partner,'合成案例',CANARY,'2026'))
        metadata=enablement.ShareMetadata(title=f'共享案例 {n}',summary='批准的合成摘要',methods='核验与实施',contributor_role='实施',source_platform='合成',source_url='https://example.com/shared',capability_tag_ids=[tags[n]])
        row=enablement.save('case',case,enablement.ShareSave(base_revision=0,metadata=metadata),admin['id']);published(grant(row,admin,'case'),admin,'case')
        request=base.model_copy(deep=True);request.target_partner_id=partner
        request.targets=[base.targets[0].model_copy(update={'capability_tag_id':tags[n]})]
        accepted=life.create(Submit(submission_id=f'parallel-distinct-{n}',request=request),owner);jobs.append(accepted)
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(lambda a:engine.execute(a['run_id']),jobs))
    for n,(owner,accepted) in enumerate(zip(owners,jobs)):
        detail=views.detail(accepted['plan_id'],owner)
        assert detail['runs'][0]['status']=='ready' and len(detail['versions'])==1
        assert detail['payload']['target_partner_id']==f'parallel-partner-{n}'
        ids={i['source_id'] for s in detail['payload']['stages'] for i in s['items']}
        assert ids=={f'parallel-course-{n}',f'parallel-case-{n}'}
        assert detail['plan']['owner_user_id']==owner['id'] and detail['plan']['confirmed_version_id'] is None
    assert CANARY not in json.dumps(captured)
    record_property('parallel_plans', '3 owners / 3 partners / 3 courses / 3 cases; diagnostic barrier reached simultaneously; one version each')


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
