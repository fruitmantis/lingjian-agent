"""Task/Run commit ordering and progressive results, using isolated synthetic inputs."""
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import pytest

from backend.app import development_engine as engine, development_model as model, development_views as views
from backend.app.database import get_db
from backend.app.routers import development, match
from backend.tests.conftest import auth_headers
from backend.tests.test_development_lifecycle import prepared
from backend.tests.test_unified_flow import unified
from backend.tests.test_process_recovery import free_port, wait_health, stop_process


def submit(client, unified, kind):
    headers = auth_headers(unified[0][0])
    original = '  数据库迁移需求\n需要保留完整原文。  '
    if kind == 'match':
        url, body = '/agent/tasks', {'requestId': str(uuid4()), 'requirement': original}
    else:
        url, body = '/development/plans', {'submission_id': str(uuid4()), 'request': {
            **unified[0][3].model_dump(), 'raw_demand': original, 'development_direction': original}}
    return url, body, headers, original


def detail(client, kind, accepted, headers):
    url = '/agent/tasks/' + accepted['recordId'] if kind == 'match' else '/development/plans/' + accepted['plan_id']
    result = client.get(url, headers=headers)
    assert result.status_code == 200
    return result.json()


@pytest.mark.parametrize('kind', ['match', 'development'])
def test_blocked_first_model_cannot_block_committed_acceptance(client, unified, monkeypatch, kind):
    entered, release = threading.Event(), threading.Event()
    url, body, headers, original = submit(client, unified, kind)
    def block(*args):
        with get_db() as conn:
            table = 'match_records' if kind == 'match' else 'development_runs'
            assert conn.execute('SELECT count(*) FROM ' + table).fetchone()[0] == 1
        entered.set()
        assert release.wait(5)
        raise TimeoutError('isolated blocked first model')
    monkeypatch.setattr(model, 'completion', block)
    executor = match.executor if kind == 'match' else development.executor
    # Join all jobs before the isolated database fixture is removed.
    with ThreadPoolExecutor(max_workers=1) as pool:
        monkeypatch.setattr(executor, 'submit', pool.submit)
        started = time.perf_counter()
        response = client.post(url, headers=headers, json=body)
        try:
            assert response.status_code == 202 and time.perf_counter() - started < 1
            assert entered.wait(2)
            data = detail(client, kind, response.json(), headers)
            assert data['progress']['finished_at'] is None
            assert data['progress']['stages'][0]['status'] == 'running'
            if kind == 'match':
                assert data['requirement'] == original and data['recommendations'] == []
                assert data['understanding'] is None and data['demandProfile'] is None
            else:
                assert data['request']['raw_demand'] == original and data['payload'] is None
                assert data['versions'] == [] and data['analysis'] is None
        finally:
            release.set()
    data = detail(client, kind, response.json(), headers)
    assert data['failureDetails'][0]['code'] == 'timeout'
    assert data['progress']['finished_at'] and data['progress']['stages'][0]['finished_at']


@pytest.mark.parametrize('kind', ['match', 'development'])
@pytest.mark.parametrize('error,code', [
    (TimeoutError('synthetic timeout'), 'timeout'),
    (httpx.ReadTimeout('synthetic timeout'), 'timeout'),
    (httpx.ConnectError('synthetic connection'), 'connection'),
    (httpx.HTTPStatusError('synthetic auth', request=httpx.Request('POST', 'https://synthetic.invalid'), response=httpx.Response(401)), 'authentication'),
    (ValueError('synthetic invalid format'), 'invalid_result'),
    (RuntimeError('synthetic unexpected failure'), 'unknown'),
])
def test_all_first_stage_failures_update_existing_task(client, unified, monkeypatch, kind, error, code):
    jobs = []
    executor = match.executor if kind == 'match' else development.executor
    monkeypatch.setattr(executor, 'submit', lambda fn, *args: jobs.append((fn, args)))
    def fail(*args): raise error
    monkeypatch.setattr(model, 'completion', fail)
    url, body, headers, original = submit(client, unified, kind)
    accepted = client.post(url, headers=headers, json=body)
    assert accepted.status_code == 202
    data = detail(client, kind, accepted.json(), headers)
    assert data['progress']['stages'][0]['status'] == 'pending'
    jobs[0][0](*jobs[0][1])
    data = detail(client, kind, accepted.json(), headers)
    assert data['failureDetails'][0]['code'] == code
    assert (data['taskStatus'] if kind == 'match' else data['runs'][0]['status']) == 'failed'
    assert client.post(url, headers=headers, json=body).status_code == 202 and len(jobs) == 1
    assert data['progress']['finished_at']


def test_validated_analysis_visible_before_official_version(client, unified, monkeypatch):
    original = unified[2]
    observed = []
    def inspect(config, messages, schema):
        if messages[0]['content'].startswith('partner_development:plan'):
            with get_db() as conn: pid = conn.execute('SELECT id FROM development_plans').fetchone()[0]
            current = views.detail(pid, unified[0][0])
            assert current['analysis']['interpretation']
            assert current['payload'] is None and current['versions'] == []
            assert [s['status'] for s in current['progress']['stages']] == ['completed', 'completed', 'running']
            observed.append(current['analysis'])
        return original(config, messages, schema)
    monkeypatch.setattr(model, 'completion', inspect)
    monkeypatch.setattr(development.executor, 'submit', lambda fn, *args: fn(*args))
    url, body, headers, _ = submit(client, unified, 'development')
    accepted = client.post(url, headers=headers, json=body)
    current = detail(client, 'development', accepted.json(), headers)
    assert len(observed) == 1 and current['payload'] and len(current['versions']) == 1
    assert all(s['status'] == 'completed' and s['started_at'] and s['finished_at'] for s in current['progress']['stages'])


def test_recommendations_visible_during_enrichment_and_retained_on_failure(client, unified, monkeypatch):
    from backend.tests.conftest import recommendation
    def complete(config, messages, schema):
        if schema['title'] == 'MatchUnderstanding': return '{"in_scope":true,"facts":{"technicalNeeds":"数据库迁移"}}'
        if schema['title'] == 'InitialSelection': return '{"candidates":[{"partnerId":"partner-1","verificationFocus":"数据库迁移经验"}]}'
        return json.dumps({ 'recommendations':[{**recommendation(), 'evidenceCases':[], 'evidenceDeliverables':[]}], 'supplyStatus':'partial','gapAnalysis':'交付能力待核实'})
    observed = []
    def fail_after_save(record_id, *args, **kwargs):
        current = match.get_match_record(record_id, unified[0][0])
        assert current.taskStatus == 'enriching' and current.recommendations and current.answer
        assert [s['status'] for s in current.progress['stages']] == ['completed', 'completed', 'completed', 'running']
        observed.append(current.recommendations)
        raise RuntimeError('isolated enrichment failure')
    monkeypatch.setattr(model, 'completion', complete)
    monkeypatch.setattr(match, '_run_task_enrichment', fail_after_save)
    monkeypatch.setattr(match.executor, 'submit', lambda fn, *args: fn(*args))
    url, body, headers, _ = submit(client, unified, 'match')
    accepted = client.post(url, headers=headers, json=body)
    current = detail(client, 'match', accepted.json(), headers)
    assert len(observed) == 1 and current['recommendations'] and current['taskStatus'] == 'partial'
    assert current['progress']['stages'][2]['status'] == 'completed'
    assert current['progress']['stages'][3]['status'] == 'failed'


def test_process_stop_after_commit_before_execution_preserves_both_tasks(client, unified, tmp_path):
    """Actual server termination with the executor deliberately paused before dispatch."""
    port = free_port()
    base = f'http://127.0.0.1:{port}'
    script = '''
from backend.app.main import app
from backend.app.routers import development, match
# Fault injection only in this isolated process: accepted work has not started.
for executor in (development.executor, match.executor):
    executor.submit = lambda *args, **kwargs: None
import uvicorn
uvicorn.run(app, host='127.0.0.1', port=PORT, log_level='error')
'''.replace('PORT', str(port))
    process = None
    with (tmp_path / 'server.log').open('w') as log:
        try:
            process = subprocess.Popen([sys.executable, '-c', script], env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT)
            wait_health(base + '/health', process)
            requests = []
            for kind in ('match', 'development'):
                url, body, headers, original = submit(client, unified, kind)
                response = httpx.post(base + url, json=body, headers=headers)
                assert response.status_code == 202
                accepted = response.json()
                current = detail(client, kind, accepted, headers)
                assert current['progress']['stages'][0]['status'] == 'pending'
                requests.append((kind, accepted, headers, original))
            stop_process(process)
            process = subprocess.Popen([sys.executable, '-c', script], env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT)
            wait_health(base + '/health', process)
            for kind, accepted, headers, original in requests:
                data = detail(client, kind, accepted, headers)
                assert data['failureDetails'][0]['code'] == 'interrupted'
                assert data['progress']['finished_at']
                if kind == 'match':
                    assert data['requirement'] == original and data['taskStatus'] == 'failed'
                else:
                    assert data['request']['raw_demand'] == original and data['runs'][0]['status'] == 'interrupted'
                    retry = httpx.post(base + f"/development/plans/{accepted['plan_id']}/retry", headers=headers,
                        json={'submission_id':str(uuid4()),'run_id':accepted['run_id']})
                    assert retry.status_code == 202 and retry.json()['plan_id'] == accepted['plan_id']
        finally:
            stop_process(process)


@pytest.mark.parametrize('kind', ['match', 'development'])
def test_dispatch_stops_after_commit_still_returns_durable_ids(client, unified, monkeypatch, kind):
    executor=match.executor if kind=='match' else development.executor
    def stopped(*args):raise RuntimeError('synthetic executor stopped')
    monkeypatch.setattr(executor,'submit',stopped)
    url,body,headers,original=submit(client,unified,kind)
    response=client.post(url,headers=headers,json=body)
    assert response.status_code==202
    current=detail(client,kind,response.json(),headers)
    assert current['failureDetails'][0]['code']=='interrupted'
    assert current['progress']['finished_at']
    assert not unified[1]


@pytest.mark.parametrize('kind',['match','development'])
def test_http_acceptance_commit_concurrency_and_lost_response(client,unified,monkeypatch,kind,record_property):
    """A real HTTP server, stalled first model, independent PG reader and duplicate clients."""
    import uvicorn
    from sqlalchemy import text
    from backend.app.main import app
    from backend.app.postgres_storage import engine_for
    port=free_port();base=f'http://127.0.0.1:{port}'
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='error',lifespan='off'))
    worker=threading.Thread(target=server.run,daemon=True);worker.start()
    entered,release=threading.Event(),threading.Event();calls=[];dispatches=[]
    executor=match.executor if kind=='match' else development.executor
    real_submit=executor.submit
    def dispatch(fn,*args):
        dispatches.append(args);return real_submit(fn,*args)
    def blocked(*args):
        calls.append(True);entered.set();assert release.wait(10)
        raise TimeoutError('HTTP acceptance verification')
    monkeypatch.setattr(executor,'submit',dispatch)
    monkeypatch.setattr(model,'completion',blocked)
    url,body,headers,original=submit(client,unified,kind)
    try:
        deadline=time.monotonic()+5
        while not server.started:
            assert worker.is_alive() and time.monotonic()<deadline
            time.sleep(.01)
        def send(_):
            start=time.perf_counter()
            response=httpx.post(base+url,json=body,headers=headers,timeout=2)
            return response,time.perf_counter()-start
        with ThreadPoolExecutor(max_workers=3) as pool:responses=list(pool.map(send,range(3)))
        assert all(r.status_code==202 and elapsed<1 for r,elapsed in responses)
        accepted=responses[0][0].json();id_key='recordId' if kind=='match' else 'plan_id'
        assert len({r.json()[id_key] for r,_ in responses})==1
        assert entered.wait(2) and len(dispatches)==len(calls)==1
        # An independent connection sees the committed row while the model is still blocked.
        with engine_for(os.environ['DATABASE_URL']).connect() as connection:
            table='match_records' if kind=='match' else 'development_plans'
            assert connection.execute(text(f'SELECT count(*) FROM {table}')).scalar_one()==1
            assert connection.execute(text("SELECT pg_try_advisory_xact_lock(hashtextextended(current_database() || '.' || current_schema(), 179183912))")).scalar_one()
        with httpx.Client(base_url=base) as browser:
            current=detail(browser,kind,accepted,headers)
        assert current['progress']['stages'][0]['status']=='running'
        listing=httpx.get(base+'/agent/tasks',headers=headers)
        assert listing.status_code==200 and accepted[id_key] in listing.text
        # Treat the first reply as lost; resubmission must reuse the same task and job.
        repeated,elapsed=send(None)
        assert repeated.json()[id_key]==accepted[id_key] and len(dispatches)==len(calls)==1
        record_property('durable_http_acceptance',json.dumps({'kind':kind,'seconds':[t for _,t in responses], 'tasks':1,'dispatches':1,'model_attempts':1,'independent_pg_visible':True}))
    finally:
        release.set();server.should_exit=True;worker.join(5)
    deadline=time.monotonic()+5
    while True:
        data=detail(client,kind,accepted,headers)
        if data['progress']['finished_at']:break
        assert time.monotonic()<deadline;time.sleep(.01)
    assert data['failureDetails'][0]['code']=='timeout'


@pytest.mark.parametrize('kind',['match','development'])
def test_database_creation_fault_never_dispatches_model(client_no_raise,unified,monkeypatch,kind):
    from backend.tests.postgres_support import install_failure
    from backend.app.error_diagnostics import recent_errors
    table='match_records' if kind=='match' else 'development_runs'
    with get_db() as conn:install_failure(conn,table,'INSERT',name='creation_fault')
    jobs=[];calls=[]
    executor=match.executor if kind=='match' else development.executor
    monkeypatch.setattr(executor,'submit',lambda *args:jobs.append(args))
    monkeypatch.setattr(model,'completion',lambda *args:calls.append(args))
    url,body,headers,_=submit(client_no_raise,unified,kind)
    response=client_no_raise.post(url,json=body,headers=headers)
    assert response.status_code==500
    assert not jobs and not calls
    with get_db() as conn:
        for target in ('match_records','development_requests','development_plans','development_runs'):
            assert conn.execute(f'SELECT count(*) FROM {target}').fetchone()[0]==0
    assert any('synthetic failure' in row['message'] for row in recent_errors())



def test_failed_initial_run_retry_persists_its_version(client,unified,monkeypatch):
    from backend.app import development_lifecycle as life
    from backend.app.development_types import Submit
    from backend.app.routers.development import RetryRun
    user=unified[0][0];original=unified[2];attempts=[]
    def fail(*args):
        attempts.append(True);raise TimeoutError('first generation failure')
    monkeypatch.setattr(model,'completion',fail)
    first=life.create(Submit(submission_id='first-generation-failure',request=unified[0][3]),user)
    engine.execute(first['run_id']);before=views.detail(first['plan_id'],user)
    assert attempts==[True] and not before['versions'] and before['runs'][0]['status']=='failed'
    monkeypatch.setattr(model,'completion',original)
    payload=RetryRun(submission_id='first-generation-retry',run_id=first['run_id'])
    retry=life.retry(first['plan_id'],payload,user);engine.execute(retry['run_id'])
    after=views.detail(first['plan_id'],user)
    assert len(after['versions'])==1 and after['payload']['stages']
    assert after['plan']['current_version_id'] and after['runs'][0]['status']=='ready'
    with get_db() as conn:
        assert conn.execute('SELECT run_id FROM development_versions WHERE id=?',(after['plan']['current_version_id'],)).fetchone()[0]==retry['run_id']
    count=len(unified[1]);repeated=life.retry(first['plan_id'],payload,user)
    engine.execute(repeated['run_id'])
    assert repeated['replayed'] and repeated['run_id']==retry['run_id']
    assert len(views.detail(first['plan_id'],user)['versions'])==1 and len(unified[1])==count
