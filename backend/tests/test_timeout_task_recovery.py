"""Timeouts remain durable, retryable execution failures; isolated data only."""
import json
from uuid import uuid4
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from backend.app import development_lifecycle as life, development_engine as engine, development_model as model, development_views as views
from backend.app.database import get_db
from backend.app.development_types import Submit, Revise
from backend.app.routers import development, match
from backend.tests.conftest import auth_headers
from backend.tests.test_unified_flow import unified, generated
from backend.tests.test_development_lifecycle import prepared


def timeout(*args, **kwargs):
    raise TimeoutError('synthetic provider timeout')


@pytest.fixture(autouse=True)
def inline_background(monkeypatch):
    # Deterministically finish isolated API jobs before each fixture database is removed.
    for executor in (match.executor, development.executor):
        monkeypatch.setattr(executor, 'submit', lambda fn,*args,**kwargs: fn(*args,**kwargs))


def counts():
    with get_db() as conn:
        return tuple(conn.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('development_requests','development_plans','development_runs','development_versions'))


@pytest.mark.parametrize('exception', [TimeoutError, httpx.ReadTimeout])
def test_matching_understanding_timeout_keeps_original_request_and_retry(client, unified, monkeypatch, exception):
    user=unified[0][0]; headers=auth_headers(user); identifier=str(uuid4())
    def failed(*args,**kwargs):raise exception('synthetic timeout')
    monkeypatch.setattr(model,'completion',failed)
    body={'requestId':identifier,'requirement':'需要数据库交付伙伴'}
    result=client.post('/agent/tasks',headers=headers,json=body)
    assert result.status_code==202 and result.json()['recordId']==identifier and result.json()['runId']
    detail=client.get('/agent/tasks/'+identifier,headers=headers).json()
    assert detail['failureDetails'][0]['code']=='timeout' and detail['recommendations']==[]
    replay=client.post('/agent/tasks',headers=headers,json=body).json()
    assert replay['runId']==result.json()['runId'] and replay['taskStatus']=='failed'
    assert client.get('/agent/tasks/'+identifier,headers=auth_headers(unified[0][1])).status_code==404
    # A further timeout on retry preserves this same Task and its failure reason.
    assert client.post('/agent/tasks/'+identifier+'/retry',headers=headers).status_code==502
    assert client.get('/agent/tasks/'+identifier,headers=headers).json()['failureDetails'][0]['code']=='timeout'
    def complete(config,messages,schema):
        if schema['title']=='MatchUnderstanding':return '{"in_scope":true,"facts":{"technicalNeeds":"数据库迁移"}}'
        if schema['title']=='InitialSelection':return '{"candidates":[{"partnerId":"partner-1","verificationFocus":"数据库迁移"}]}'
        return '{"answer":"待补充资料。","recommendations":[],"supplyStatus":"unknown","gapAnalysis":"资料不足"}'
    monkeypatch.setattr(model,'completion',complete)
    assert client.post('/agent/tasks/'+identifier+'/retry',headers=headers).json()['taskStatus']=='ready'
    with get_db() as conn:assert conn.execute('SELECT count(*) FROM match_records').fetchone()[0]==1


def test_development_timeout_creates_failed_run_and_retries_same_plan(unified,monkeypatch,client):
    user=unified[0][0];headers=auth_headers(user);body={'submission_id':'timed-out-initial','request':unified[0][3].model_dump()}
    monkeypatch.setattr(model,'completion',timeout)
    response=client.post('/development/plans',headers=headers,json=body)
    assert response.status_code==202
    accepted=response.json();pid=accepted['plan_id'];rid=accepted['run_id']
    detail=views.detail(pid,user)
    assert detail['runs'][0]['status']=='failed' and detail['failureDetails'][0]['code']=='timeout'
    assert detail['plan']['active_run_id'] is None and detail['plan']['current_version_id'] is None
    assert counts()==(1,1,1,0)
    assert client.get('/development/submissions/timed-out-initial',headers=headers).json()['status']=='failed'
    replay=client.post('/development/plans',headers=headers,json=body).json()
    assert replay['plan_id']==pid and replay['run_id']==rid and replay['replayed']
    assert counts()==(1,1,1,0)
    # Repair an old terminal Run still holding the task lock on the normal detail read.
    with get_db() as conn:conn.execute('UPDATE development_plans SET active_run_id=? WHERE id=?',(rid,pid))
    assert client.get('/development/plans/'+pid,headers=auth_headers(unified[0][1])).status_code==404
    with get_db() as conn:assert conn.execute('SELECT active_run_id FROM development_plans WHERE id=?',(pid,)).fetchone()[0]==rid
    assert views.detail(pid,user)['plan']['active_run_id'] is None
    retry_body=development.RetryRun(submission_id='retry-same-task',run_id=rid,based_on_version_id=None)
    again=life.retry(pid,retry_body,user)
    engine.execute(again['run_id'])
    assert counts()==(1,1,2,0) and views.detail(pid,user)['runs'][0]['status']=='failed'
    assert life.retry(pid,retry_body,user)['run_id']==again['run_id'] and counts()==(1,1,2,0)
    monkeypatch.setattr(model,'completion',unified[2])
    final=life.retry(pid,development.RetryRun(submission_id='retry-success',run_id=again['run_id']),user)
    engine.execute(final['run_id'])
    assert final['plan_id']==pid and counts()==(1,1,3,1)
    assert views.detail(pid,user)['presentation']['current_available']


def test_concurrent_timeout_submission_creates_only_one_request_plan_and_run(unified,monkeypatch):
    monkeypatch.setattr(model,'completion',timeout)
    payload=Submit(submission_id='concurrent-timeout-submission',request=unified[0][3])
    with ThreadPoolExecutor(max_workers=3) as pool:
        accepted=list(pool.map(lambda _:life.create(payload,unified[0][0]),range(3)))
    assert len({item['plan_id'] for item in accepted})==len({item['run_id'] for item in accepted})==1
    assert counts()==(1,1,1,0)
    engine.execute(accepted[0]['run_id'])
    with get_db() as conn:
        run=conn.execute('SELECT status,safe_error_message FROM development_runs').fetchone()
    assert run['status']=='failed' and json.loads(run['safe_error_message'])[0]['code']=='timeout'


def test_later_understanding_timeout_preserves_successful_result(unified,monkeypatch):
    accepted,detail=generated(unified);user=unified[0][0];pid=accepted['plan_id'];version=detail['plan']['current_version_id']
    monkeypatch.setattr(model,'completion',timeout)
    body=Revise(submission_id='later-understanding-timeout',based_on_version_id=version,instruction='重新规划建议',request=unified[0][3])
    failed=life.revise(pid,body,user)
    engine.execute(failed['run_id'])
    assert views.detail(pid,user)['runs'][0]['status']=='failed' and failed['plan_id']==pid
    assert life.revise(pid,body,user)['run_id']==failed['run_id']
    after=views.detail(pid,user)
    assert after['plan']['current_version_id']==version and after['payload']==detail['payload']
    assert after['presentation']['current_available'] and after['failureDetails'][0]['code']=='timeout'
    assert counts()==(1,1,2,1)


def test_known_preparation_failure_is_not_uncertain_but_commit_failure_is(unified,monkeypatch,client):
    from backend.app.task_failures import PublicTaskError
    user=unified[0][0];body={'requestId':str(uuid4()),'requirement':'合成匹配需求'}
    def failed(*args,**kwargs):raise PublicTaskError(httpx.ConnectError('synthetic unreachable'))
    monkeypatch.setattr(match.understanding,'prepare',failed)
    response=client.post('/agent/tasks',headers=auth_headers(user),json=body)
    assert response.status_code==202
    detail=client.get('/agent/tasks/'+body['requestId'],headers=auth_headers(user)).json()
    assert detail['taskStatus']=='failed' and detail['failureDetails'][0]['code']=='connection'
    body['requestId']=str(uuid4())
    monkeypatch.setattr(match.understanding,'prepare',lambda *_: {})
    original=match.get_db;calls=0
    @contextmanager
    def fail_commit():
        nonlocal calls
        calls+=1
        with original() as conn:
            yield conn
            if calls==1:raise RuntimeError('synthetic ambiguous commit response')
    monkeypatch.setattr(match,'get_db',fail_commit)
    response=client.post('/agent/tasks',headers=auth_headers(user),json=body)
    assert response.status_code==500 and 'submissionAccepted' not in response.json()


def test_out_of_scope_matching_keeps_normal_task(unified,monkeypatch,client):
    monkeypatch.setattr(model,'completion',lambda *_:'{"in_scope":false}')
    response=client.post('/agent/tasks',headers=auth_headers(unified[0][0]),json={'requestId':str(uuid4()),'requirement':'合成范围外'})
    assert response.status_code==202
    result=match.get_match_record(response.json()['recordId'],unified[0][0])
    assert result.taskStatus=='ready' and result.scopeMessage and not result.failureDetails
    with get_db() as conn:assert conn.execute('SELECT count(*) FROM match_records').fetchone()[0]==1
