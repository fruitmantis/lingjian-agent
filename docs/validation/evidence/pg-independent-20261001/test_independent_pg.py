"""Audit-only tests. Existing product code and original assertions are untouched.

Only synthetic fixtures in protected random PG schemas; final observations use
psycopg directly, not the application's repository or view functions.
"""
import copy
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import HTTPException

from catalog_audit import direct
from backend.app import development_engine as engine, development_lifecycle as life
from backend.app import development_model as model, development_views as views
from backend.app.database import get_db
from backend.app.development_types import Submit, Conversation
from backend.app.postgres_storage import Connection
from backend.app.routers import development, match
from backend.tests.conftest import auth_headers, recommendation
from backend.tests.test_development_lifecycle import prepared
from backend.tests.test_unified_flow import unified


def rows(sql, args=()):
    with direct(os.environ['DATABASE_URL']) as conn:
        return conn.execute(sql,args).fetchall()


def write(sql, args=()):
    # The fixture has already validated the dedicated DB and random schema.
    from backend.tests.support.model_test_boundary import require_test_database
    require_test_database()
    with direct(os.environ['DATABASE_URL'],readonly=False) as conn:
        conn.execute(sql,args)


def wait_run(rid):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        r=rows('SELECT * FROM development_runs WHERE id=%s',(rid,))[0]
        if r['status'] not in ('pending','running'):return r
        time.sleep(.02)
    raise AssertionError('Run did not finish independently')


def version(pid):
    return rows('''SELECT p.current_version_id,p.confirmed_version_id,p.active_run_id,
        v.payload_json,v.run_id FROM development_plans p LEFT JOIN development_versions v
        ON v.id=p.current_version_id WHERE p.id=%s''',(pid,))[0]


def match_reply(messages,schema,marker):
    if schema['title']=='MatchUnderstanding':
        return json.dumps({'in_scope':True,'facts':{'technicalNeeds':'数据库迁移 '+marker}})
    if schema['title']=='InitialSelection':
        return json.dumps({'candidates':[{'partnerId':'partner-1','verificationFocus':'数据库迁移'}]})
    return json.dumps({'answer':'合成匹配 '+marker,'recommendations':[
        {**recommendation(),'evidenceCases':[],'evidenceDeliverables':[]}],
        'supplyStatus':'partial','gapAnalysis':marker})


@pytest.mark.parametrize('kinds',[('development','development'),('match','match'),('development','match')])
def test_two_owners_progress_without_model_wait_lock(client,unified,monkeypatch,kinds,record_property):
    a,b=unified[0][:2]; ha,hb=auth_headers(a),auth_headers(b)
    entered,release=threading.Event(),threading.Event()
    observed=[];calls=[];original=unified[2];execute=Connection.execute
    expected=rows('SELECT current_database() AS db,current_schema() AS schema')[0]
    def audited(self,sql,parameters=()):
        identity=self.connection.exec_driver_sql('SELECT current_database(),current_schema(),pg_backend_pid()').one()
        assert identity[:2]==(expected['db'],expected['schema'])
        observed.append({'db':identity[0],'schema':identity[1],'pid':identity[2],
                         'thread':threading.current_thread().name,'sql_kind':sql.lstrip().split()[0]})
        return execute(self,sql,parameters)
    monkeypatch.setattr(Connection,'execute',audited)
    def complete(config,messages,schema):
        body=messages[-1]['content'];marker='AUDIT_A' if 'AUDIT_A' in body else 'AUDIT_B'
        assert not ('AUDIT_A' in body and 'AUDIT_B' in body)
        calls.append((marker,schema['title']))
        if marker=='AUDIT_A':
            entered.set();assert release.wait(15)
        if schema['title'] in ('MatchUnderstanding','InitialSelection','MatchAnswer'):
            return match_reply(messages,schema,marker)
        return original(config,messages,schema)
    monkeypatch.setattr(model,'completion',complete)
    def submit(kind,user,headers,marker):
        if kind=='match':
            body={'requestId':str(uuid4()),'requirement':'数据库迁移 '+marker}
            endpoint='/agent/tasks'
        else:
            body={'submission_id':str(uuid4()),'request':{'target_partner_id':'partner-1','development_direction':'数据库迁移 '+marker}}
            endpoint='/development/plans'
        response=client.post(endpoint,headers=headers,json=body)
        assert response.status_code==202
        out=response.json();tid=out['recordId'] if kind=='match' else out['plan_id']
        return endpoint,body,out,tid
    def ready(kind,out):
        if kind=='development':return wait_run(out['run_id'])['status']=='ready'
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            status=rows('SELECT task_status FROM match_records WHERE id=%s',(out['recordId'],))[0]['task_status']
            if status not in ('matching','enriching'):return status=='ready'
            time.sleep(.02)
        raise AssertionError('Other owner stalled behind model')
    try:
        ea,ba,oa,ta=submit(kinds[0],a,ha,'AUDIT_A')
        assert entered.wait(3)
        started=time.monotonic();eb,bb,ob,tb=submit(kinds[1],b,hb,'AUDIT_B')
        assert ready(kinds[1],ob)
        second_seconds=time.monotonic()-started
        assert not release.is_set()
        with direct(os.environ['DATABASE_URL']) as probe:
            assert probe.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(current_database() || '.' || current_schema(),179183912)) AS ok").fetchone()['ok']
            states=probe.execute('SELECT pid,state,xact_start IS NOT NULL AS in_transaction FROM pg_stat_activity WHERE pid=ANY(%s)',(list({x['pid'] for x in observed}),)).fetchall()
        assert states and all(not x['in_transaction'] for x in states)
        assert client.get(ea+'/'+ta,headers=hb).status_code==404
        assert client.get(eb+'/'+tb,headers=ha).status_code==404
        replay=client.post(ea,headers=ha,json=ba);assert replay.status_code==202
        assert (replay.json().get('recordId') or replay.json().get('plan_id'))==ta
    finally:release.set()
    assert ready(kinds[0],oa)
    for kind,tid,owner,marker in [(kinds[0],ta,a,'AUDIT_A'),(kinds[1],tb,b,'AUDIT_B')]:
        if kind=='development':
            row=rows('''SELECT p.owner_user_id,v.payload_json FROM development_plans p
                JOIN development_versions v ON v.id=p.current_version_id WHERE p.id=%s''',(tid,))[0]
            assert marker in row['payload_json']
            assert rows('SELECT count(*) AS n FROM development_versions WHERE plan_id=%s',(tid,))[0]['n']==1
        else:
            row=rows('SELECT owner_user_id,requirement FROM match_records WHERE id=%s',(tid,))[0]
            assert marker in row['requirement']
            assert rows('SELECT gap_analysis FROM demand_profiles WHERE match_record_id=%s',(tid,))[0]['gap_analysis']==marker
        assert row['owner_user_id']==owner['id']
    record_property('independent_connection_evidence',json.dumps({'kinds':kinds,'actual':expected,
        'application_pids':sorted({x['pid'] for x in observed}),'threads':sorted({x['thread'] for x in observed}),
        'executed_statements':len(observed),'other_task_completed_while_first_blocked_seconds':second_seconds,
        'during_wait_pg_stat_activity':states,'model_calls':calls,'cross_owner_http':[404,404]}))


def test_answer_failure_patch_retry_and_late_result_independent_pg(client,unified,monkeypatch,record_property):
    user=unified[0][0];original=unified[2]
    first=life.create(Submit(submission_id='independent-first',request=unified[0][3]),user)
    engine.execute(first['run_id']);assert wait_run(first['run_id'])['status']=='ready'
    pid=first['plan_id'];before=version(pid);base=before['current_version_id'];assert base
    write('UPDATE development_plans SET confirmed_version_id=%s WHERE id=%s',(base,pid))
    old=json.loads(before['payload_json'])
    answer=views.converse(pid,Conversation(submission_id='independent-answer',based_on_version_id=base,message='为什么推荐第一个实验？'),user)
    engine.execute(answer['run_id']);assert wait_run(answer['run_id'])['status']=='ready'
    history=json.loads(rows('SELECT payload_json FROM development_requests WHERE id=(SELECT request_id FROM development_plans WHERE id=%s)',(pid,))[0]['payload_json'])['_conversation']
    assert history[-1]['answer'].strip()
    assert version(pid)['current_version_id']==base
    def contradiction(c,m,s):
        data=json.loads(original(c,m,s));data['action']='regenerate';return json.dumps(data)
    monkeypatch.setattr(model,'completion',contradiction)
    rejected=views.converse(pid,Conversation(submission_id='independent-reject',based_on_version_id=base,message='哪个实验更难？'),user)
    engine.execute(rejected['run_id']);assert wait_run(rejected['run_id'])['status']=='failed'
    assert rows('SELECT count(*) AS n FROM development_versions WHERE plan_id=%s',(pid,))[0]['n']==1
    monkeypatch.setattr(model,'completion',original)
    write("CREATE FUNCTION audit_pointer_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'independent audit pointer failure' USING ERRCODE='23514'; END $$")
    write('CREATE TRIGGER audit_pointer_fault BEFORE UPDATE OF current_version_id ON development_plans FOR EACH ROW WHEN (NEW.current_version_id IS DISTINCT FROM OLD.current_version_id) EXECUTE FUNCTION audit_pointer_fault()')
    failed=views.converse(pid,Conversation(submission_id='independent-patch',based_on_version_id=base,message='只换第二个实验'),user)
    engine.execute(failed['run_id']);failed_row=wait_run(failed['run_id']);assert failed_row['status']=='failed'
    assert version(pid)['payload_json']==before['payload_json']
    assert rows('SELECT count(*) AS n FROM development_versions WHERE plan_id=%s',(pid,))[0]['n']==1
    assert rows('SELECT count(*) AS n FROM development_version_items WHERE version_id NOT IN (SELECT id FROM development_versions)')[0]['n']==0
    write('DROP TRIGGER audit_pointer_fault ON development_plans');write('DROP FUNCTION audit_pointer_fault()')
    body=development.RetryRun(submission_id='independent-retry',run_id=failed['run_id'],based_on_version_id=base)
    retry=life.retry(pid,body,user);engine.execute(retry['run_id']);assert wait_run(retry['run_id'])['status']=='ready'
    new=version(pid);payload=json.loads(new['payload_json'])
    assert new['current_version_id']!=base and new['confirmed_version_id']==base and new['run_id']==retry['run_id']
    assert payload['stages'][0]['items'][0]==old['stages'][0]['items'][0]
    assert payload['stages'][0]['items'][1]['source_id']=='unified-lab-3' and payload['answer']==old['answer']
    count=len(unified[1]);again=life.retry(pid,body,user);engine.execute(again['run_id'])
    assert len(unified[1])==count and again['run_id']==retry['run_id']
    with pytest.raises(HTTPException) as stale:
        life.complete(failed['run_id'],failed_row['execution_token'],old,[],lambda *_:None)
    assert stale.value.status_code==409
    assert version(pid)==new and rows('SELECT count(*) AS n FROM development_versions WHERE plan_id=%s',(pid,))[0]['n']==2
    record_property('independent_business_assertions',json.dumps({'successful_explanation_answer':True,
        'contradictory_modification_rejected_separately':True,'server_trigger_failure_sqlstate':'23514',
        'rollback':True,'retry_version_run_link':True,'current_advanced_confirmed_preserved':True,
        'unmodified_item_and_answer_preserved':True,'successful_retry_idempotent':True,'late_save_http':409}))


def test_old_matching_enrichment_cannot_overwrite_retry(prepared,monkeypatch,record_property):
    from backend.app.database import recover_stale_tasks
    user=prepared[0];entered,release=threading.Event(),threading.Event()
    current={'marker':'AUDIT_OLD'};original=match._generate_demand_profile
    def completion(c,m,s):return match_reply(m,s,current['marker'])
    monkeypatch.setattr(model,'completion',completion)
    def delayed(*args,**kwargs):
        if kwargs.get('data',{}).get('gapAnalysis')=='AUDIT_OLD':
            entered.set();assert release.wait(15)
        return original(*args,**kwargs)
    monkeypatch.setattr(match,'_generate_demand_profile',delayed)
    accepted=match.create_task(match.TaskCreateRequest(requestId=uuid4(),requirement='数据库迁移独立迟到审查'),user)
    try:
        assert entered.wait(3)
        write("UPDATE match_records SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=%s",(accepted.recordId,))
        assert recover_stale_tasks(record_id=accepted.recordId,stale_after_seconds=1)==1
        # A legitimate candidate change forces the retry to recompute its answer.
        write("UPDATE partners SET intro='合成资料更新，仍具备数据库迁移经验' WHERE id='partner-1'")
        current['marker']='AUDIT_NEW'
        retried=match.retry_match_record(accepted.recordId,user)
        assert retried.taskStatus=='ready'
        new=rows('SELECT gap_analysis FROM demand_profiles WHERE match_record_id=%s',(accepted.recordId,))[0]['gap_analysis']
        assert new=='AUDIT_NEW'
    finally:release.set()
    # Join only this test's executor while its own schema still exists.
    match.executor.shutdown(wait=True)
    after=rows('SELECT gap_analysis FROM demand_profiles WHERE match_record_id=%s',(accepted.recordId,))[0]['gap_analysis']
    state=rows('SELECT task_status FROM match_records WHERE id=%s',(accepted.recordId,))[0]['task_status']
    record_property('late_enrichment_observation',json.dumps({'new_retry_value':new,'after_old_worker':after,'task_status':state}))
    assert after==new, 'Old matching worker overwrote the newer retry demand profile'
