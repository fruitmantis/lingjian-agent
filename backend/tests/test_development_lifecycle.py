import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from backend.app import development_lifecycle as life
from backend.app.development_types import DevelopmentRequest,Submit,Revise
from backend.app.database import get_db
from backend.tests.conftest import make_user,make_partner

@pytest.fixture
def prepared(client):
    user=make_user('developer-a');other=make_user('developer-b');admin=make_user('developer-admin',role='admin');make_partner()
    with get_db() as conn:tag=conn.execute("SELECT id FROM capability_tags WHERE name='数据库' AND enabled=1 LIMIT 1").fetchone()[0]
    request=DevelopmentRequest(target_partner_id='partner-1',raw_demand='原始诉求须保留',development_goal='数据库迁移',trainee_role='工程师',trainee_count=3,known_baseline='基础未知，已接受入门假设',duration_weeks=4,hours_per_week=3,constraints=dict.fromkeys(life.CONSTRAINTS,'无要求'),model_input_allowed=True,partner_goal_allowed=True,targets=[{'capability_tag_id':tag,'requirement':'独立交付'}])
    return user,other,admin,request


def start(prepared):
    user,_,_,request=prepared
    accepted=life.create(Submit(submission_id='submission-one',request=request),user)
    run=life.claim(accepted['run_id'])
    return accepted,run


def result(prepared):
    target=prepared[3].targets[0]
    return {'request':prepared[3].model_dump(),'diagnoses':[{'capability_tag_id':target.capability_tag_id,'problem_type':'evidence_gap'}],'stages':[{'title':'待核实','items':[]}],'resource_gaps':['当前资源库未找到匹配项']}


def complete(prepared,accepted,run):return life.complete(accepted['run_id'],run['execution_token'],result(prepared),[],lambda *_:None)

def plan(plan_id):
    with get_db() as conn:return dict(conn.execute('SELECT * FROM development_plans WHERE id=?',(plan_id,)).fetchone())


def test_only_partner_and_direction_are_required(prepared):
    minimal=DevelopmentRequest(target_partner_id='partner-1',development_direction='Agent 应用交付')
    assert life.clarify(minimal)['missing_fields']==[]
    accepted=life.create(Submit(submission_id='minimal-direction',request=minimal),prepared[0])
    with get_db() as conn:
        payload=json.loads(conn.execute('SELECT payload_json FROM development_requests').fetchone()[0])
        assert payload['raw_demand']=='Agent 应用交付'
        assert payload['trainee_count'] is None and payload['targets']==[]
    assert accepted['plan_id']


def test_submission_idempotency_and_single_execution(prepared):
    payload=Submit(submission_id='same-submission',request=prepared[3])
    with ThreadPoolExecutor(max_workers=3) as pool:accepted=list(pool.map(lambda _:life.create(payload,prepared[0]),range(3)))
    assert len({r['plan_id'] for r in accepted})==1
    with ThreadPoolExecutor(max_workers=3) as pool:claimed=list(pool.map(lambda _:life.claim(accepted[0]['run_id']),range(3)))
    assert sum(r is not None for r in claimed)==1
    with get_db() as conn:assert conn.execute('SELECT count(*) FROM development_requests').fetchone()[0]==1
    changed=payload.model_copy(deep=True);changed.request.development_goal='不同请求'
    with pytest.raises(HTTPException) as error:life.create(changed,prepared[0])
    assert error.value.status_code==409


def test_pointer_lifecycle_conflicts_owner_archive_and_failure(prepared):
    user,other,admin,request=prepared;accepted,run=start(prepared);pid=accepted['plan_id']
    with get_db() as conn:
        with pytest.raises(HTTPException) as error:life.authorize(conn,pid,other)
        assert error.value.status_code==404
        assert life.authorize(conn,pid,admin)
    with pytest.raises(HTTPException):life.archive(pid,user)
    v1=complete(prepared,accepted,run)
    assert (plan(pid)['current_version_id'],plan(pid)['confirmed_version_id'])==(v1,None)
    life.confirm(pid,v1,user)
    revise=Revise(submission_id='revise-two',based_on_version_id=v1,instruction='缩短周期',request=request)
    second=life.revise(pid,revise,user);run2=life.claim(second['run_id'])
    with pytest.raises(HTTPException):life.revise(pid,revise.model_copy(update={'submission_id':'another-run'}),user)
    v2=complete(prepared,second,run2)
    assert (plan(pid)['current_version_id'],plan(pid)['confirmed_version_id'])==(v2,v1)
    with pytest.raises(HTTPException):life.revise(pid,revise.model_copy(update={'submission_id':'stale-edit'}),user)
    third=life.revise(pid,revise.model_copy(update={'submission_id':'failed-third','based_on_version_id':v2}),user)
    run3=life.claim(third['run_id']);life.finish_failure(third['run_id'],run3['execution_token'],'model')
    assert (plan(pid)['current_version_id'],plan(pid)['confirmed_version_id'])==(v2,v1)
    with pytest.raises(HTTPException):complete(prepared,third,run3)
    life.confirm(pid,v2,user);life.archive(pid,user)
    assert plan(pid)['status']=='archived' and plan(pid)['confirmed_version_id']==v2
    life.archive(pid,user,restore=True)
    assert plan(pid)['status']=='active' and plan(pid)['current_version_id']==v2
    with get_db() as conn:
        with pytest.raises(sqlite3.IntegrityError):conn.execute('UPDATE development_versions SET payload_json=? WHERE id=?',('{}',v1))


@pytest.mark.parametrize('fault',['version','item','diagnosis','pointer'])
def test_atomic_save_faults_do_not_leave_half_versions(prepared,fault):
    accepted,run=start(prepared);data=result(prepared)
    data['stages'][0]['items']=[{'synthetic':'item'}]
    target={'version':('INSERT','development_versions',''),'item':('INSERT','development_version_items',''),'diagnosis':('INSERT','development_diagnoses',''),'pointer':('UPDATE','development_plans','WHEN NEW.current_version_id IS NOT OLD.current_version_id')}[fault]
    with get_db() as conn:conn.execute(f"CREATE TRIGGER synthetic_failure BEFORE {target[0]} ON {target[1]} {target[2]} BEGIN SELECT RAISE(ABORT,'synthetic fault'); END")
    with pytest.raises(sqlite3.IntegrityError):life.complete(accepted['run_id'],run['execution_token'],data,[],lambda *_:None)
    with get_db() as conn:
        for table in ['development_versions','development_version_items','development_diagnoses']:assert conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==0
    assert plan(accepted['plan_id'])['current_version_id'] is None
    life.finish_failure(accepted['run_id'],run['execution_token'],'persistence')
    assert plan(accepted['plan_id'])['active_run_id'] is None


def test_startup_recovery_rejects_late_results(prepared):
    accepted,run=start(prepared);life.recover(startup=True)
    with pytest.raises(HTTPException):complete(prepared,accepted,run)
    with get_db() as conn:assert conn.execute('SELECT status FROM development_runs').fetchone()[0]=='interrupted'
    assert plan(accepted['plan_id'])['current_version_id'] is None
