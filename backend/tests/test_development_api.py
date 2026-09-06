import copy,json,threading,time
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from backend.app import development_lifecycle as life,development_engine as engine,development_views as views,enablement
from backend.app.development_types import Submit,Revise,Edit
from backend.app.database import get_db
from backend.tests.test_development_engine import scenario,execute,CANARY
from backend.tests.test_development_lifecycle import prepared,plan
from backend.tests.conftest import auth_headers


def test_api_quick_accept_unified_tasks_ownership_and_idempotency(scenario,client,monkeypatch):
    from backend.app.routers import development
    queued=[];monkeypatch.setattr(development.executor,'submit',lambda fn,id:queued.append(id))
    user,other,admin,req=scenario[0];headers=auth_headers(user)
    body={'submission_id':'api-development-create','request':req.model_dump()}
    response=client.post('/development/plans',headers=headers,json=body);assert response.status_code==202
    accepted=response.json();id=accepted['plan_id'];assert len(queued)==1
    assert client.post('/development/plans',headers=headers,json=body).json()['run_id']==accepted['run_id'] and len(queued)==1
    listing=client.get('/agent/tasks?task_type=development_plan',headers=headers).json();assert listing['total']==1 and listing['items'][0]['taskStatus']=='matching'
    assert client.get('/agent/tasks/'+id,headers=headers).json()['task_type']=='development_plan'
    for url in ['/development/plans/'+id,'/agent/tasks/'+id,'/development/plans/'+id+'/transferable','/development/plans/'+id+'/candidates']:
        assert client.get(url,headers=auth_headers(other)).status_code==404
        assert client.get(url).status_code==401
    assert client.get('/development/plans/'+id,headers=auth_headers(admin)).status_code==200
    assert client.get('/agent/tasks?task_type=development_plan',headers=auth_headers(other)).json()['total']==0
    assert client.get('/admin/tasks?task_type=development_plan',headers=auth_headers(admin)).json()['total']==1
    assert client.patch('/agent/tasks/'+id+'/archive',headers=headers).status_code==409
    engine.execute(accepted['run_id'])
    assert client.get('/development/plans/'+id,headers=headers).headers['cache-control']=='no-store'
    assert client.patch('/agent/tasks/'+id+'/archive',headers=auth_headers(other)).status_code==404
    assert client.patch('/agent/tasks/'+id+'/archive',headers=headers).status_code==204
    assert client.get('/agent/tasks?task_type=development_plan',headers=headers).json()['total']==0
    assert client.get('/agent/tasks?task_type=development_plan&status=archived',headers=headers).json()['total']==1
    assert client.patch('/agent/tasks/'+id+'/restore',headers=headers).status_code==204


def stages(payload):
    return [{'title':s['title'],'items':[{k:i[k] for k in ('source_type','source_id','source_version','capability_tag_id','reason','estimated_hours','note')} for i in s['items']]} for s in payload['stages']]


def test_edit_confirm_transfer_and_cas(scenario):
    accepted,run,payload=execute(scenario);id=accepted['plan_id'];user=scenario[0][0];v1=plan(id)['current_version_id']
    with pytest.raises(HTTPException) as err:views.transferable(id,user)
    assert err.value.status_code==409
    views.confirm(id,v1,user);before=views.transferable(id,user)['text'];assert '数据库课程' in before and CANARY not in before
    edited=stages(payload);edited[0]['title']='内部阶段标题';edited[0]['items'][0]['note']='内部编辑备注不外发'
    result=views.edit(id,Edit(based_on_version_id=v1,stages=edited),user);v2=result['version_id']
    assert plan(id)['confirmed_version_id']==v1 and plan(id)['current_version_id']==v2
    assert views.transferable(id,user)['text']==before
    with pytest.raises(HTTPException) as err:views.edit(id,Edit(based_on_version_id=v1,stages=edited),user)
    assert err.value.status_code==409
    views.confirm(id,v2,user)
    with pytest.raises(HTTPException):views.transferable(id,user,expected=v1,copy_event=True)
    text=views.transferable(id,user,expected=v2,copy_event=True)['text']
    for forbidden in [CANARY,'内部编辑备注','内部阶段标题',id,v1,'source_id','model_inference','/tasks/','error_stage']:assert forbidden not in text
    with get_db() as conn:assert conn.execute("SELECT COUNT(*) FROM development_audit_events WHERE action='transfer_copy'").fetchone()[0]==1


def test_same_plan_concurrent_revise_edit_and_failed_adjustment(scenario,monkeypatch):
    accepted,_,payload=execute(scenario);id=accepted['plan_id'];user,_,_,req=scenario[0];v1=plan(id)['current_version_id'];views.confirm(id,v1,user)
    def attempt(n):
        try:return life.revise(id,Revise(submission_id=f'concurrent-adjust-{n}',based_on_version_id=v1,instruction='调整周期',request=req),user)
        except HTTPException as e:return e.status_code
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(attempt,range(3)))
    assert results.count(409)==2
    with pytest.raises(HTTPException) as err:views.edit(id,Edit(based_on_version_id=v1,stages=stages(payload)),user)
    assert err.value.status_code==409
    from backend.app import development_model
    monkeypatch.setattr(development_model,'completion',lambda *args: (_ for _ in ()).throw(RuntimeError(CANARY)))
    engine.execute(next(r['run_id'] for r in results if isinstance(r,dict)))
    assert plan(id)['current_version_id']==v1 and plan(id)['confirmed_version_id']==v1
    assert '数据库课程' in views.transferable(id,user)['text']
    assert CANARY not in json.dumps(views.detail(id,user))


@pytest.mark.parametrize('kind',['ordinary_course','sensitive_course','partner_permission','model_permission','system_permission'])
def test_resource_revocation_filters_historical_text(scenario,kind):
    accepted,_,payload=execute(scenario);id=accepted['plan_id'];user=scenario[0][0];v1=plan(id)['current_version_id'];views.confirm(id,v1,user)
    with get_db() as conn:
        stored=conn.execute('SELECT payload_json FROM development_versions WHERE id=?',(v1,)).fetchone()[0]
        if kind=='ordinary_course':conn.execute("UPDATE enablement_resources SET status='unpublished' WHERE id='test-course'")
        elif kind=='sensitive_course':conn.execute("UPDATE enablement_resources SET status='revoked',authorization_epoch=authorization_epoch+1 WHERE id='test-course'")
        else:conn.execute(f"UPDATE enablement_resources SET {kind.split('_')[0]}_allowed=0,authorization_epoch=authorization_epoch+1 WHERE id='test-course'".replace('system_allowed','system_visible'))
    current=views.detail(id,user)
    if kind=='ordinary_course':
        assert not current['hidden'];assert current['payload']['stages'][0]['items'][0]['availability']=='unavailable'
        assert '数据库课程' not in views.transferable(id,user)['text']
    else:
        assert current['hidden'] and current['payload'] is None
        with pytest.raises(HTTPException):views.transferable(id,user)
    with get_db() as conn:assert conn.execute('SELECT payload_json FROM development_versions WHERE id=?',(v1,)).fetchone()[0]==stored


def test_business_correction_has_provenance(scenario):
    accepted,_,payload=execute(scenario);id=accepted['plan_id'];user=scenario[0][0];tag=scenario[0][3].targets[0].capability_tag_id
    views.edit(id,Edit(based_on_version_id=plan(id)['current_version_id'],stages=stages(payload),corrections={tag:'经理已核验人员评估'}),user)
    diagnosis=views.detail(id,user)['payload']['diagnoses'][0]
    assert diagnosis['judgment_source']=='business_correction' and diagnosis['confirmation']['actor_user_id']==user['id']

@pytest.mark.parametrize('sensitive',[False,True])
def test_case_stop_or_sensitive_revoke_hides_inline_text_and_preserves_snapshot(scenario,sensitive,client):
    from backend.tests.test_enablement import grant,published
    user,_,admin,req=scenario[0]
    metadata=enablement.ShareMetadata(title='共享案例',summary='获准共享的方法摘要',methods='逐项核实并复盘',contributor_role='实施',source_platform='共享平台',source_url='https://example.com/shared',capability_tag_ids=[req.targets[0].capability_tag_id])
    row=enablement.save('case','secret-case',enablement.ShareSave(base_revision=0,metadata=metadata),admin['id']);published(grant(row,admin,'case'),admin,'case')
    accepted,_,payload=execute(scenario);id=accepted['plan_id'];v1=plan(id)['current_version_id'];views.confirm(id,v1,user)
    assert CANARY in client.get('/enablement/context?partner_id=partner-1',headers=auth_headers(user)).text
    assert CANARY not in json.dumps(scenario[1]) and CANARY not in views.transferable(id,user)['text']
    with get_db() as conn:
        stored=conn.execute('SELECT payload_json FROM development_versions WHERE id=?',(v1,)).fetchone()[0]
        conn.execute("UPDATE case_share_configs SET status=?,authorization_epoch=authorization_epoch+? WHERE case_id='secret-case'",('revoked' if sensitive else 'unpublished',int(sensitive)))
    assert views.detail(id,user)['hidden']
    with pytest.raises(HTTPException):views.transferable(id,user)
    listing=client.get('/agent/tasks?task_type=development_plan',headers=auth_headers(user)).json()
    assert listing['items'][0]['requirement']=='发展方案（来源授权已变化）'
    with get_db() as conn:
        assert conn.execute('SELECT payload_json FROM development_versions WHERE id=?',(v1,)).fetchone()[0]==stored
        assert not any(c['source_type']=='case' for c in engine.candidates(conn,req.model_dump(),payload['diagnoses']))


def test_model_plan_free_text_cannot_assert_confirmed_gap(scenario,monkeypatch):
    from backend.app import development_model
    original=scenario[2]
    def mock(*args):
        output=json.loads(original(*args))
        if 'stages' in output:output['stages'][0]['title']='该伙伴确认不具备数据库能力'
        return json.dumps(output)
    monkeypatch.setattr(development_model,'completion',mock)
    accepted,run,payload=execute(scenario);assert run['status']=='failed' and payload is None


def test_task_creation_p95_under_one_second_without_waiting_model(scenario,client,monkeypatch,record_property):
    from backend.app.routers import development
    queued=[];monkeypatch.setattr(development.executor,'submit',lambda fn,id:queued.append(id))
    elapsed=[];user,_,_,req=scenario[0]
    for n in range(20):
        started=time.perf_counter();res=client.post('/development/plans',headers=auth_headers(user),json={'submission_id':f'p95-submission-{n:03d}','request':req.model_dump()});elapsed.append(time.perf_counter()-started)
        assert res.status_code==202
    p95=sorted(elapsed)[18];record_property('development_create_p95_seconds',round(p95,6));assert p95<1
    assert len(queued)==20
    assert client.get('/agent/tasks?task_type=development_plan&pageSize=7&page=3',headers=auth_headers(user)).json()['total']==20
    with get_db() as conn:assert conn.execute('SELECT COUNT(*) FROM development_versions').fetchone()[0]==0


def test_conversational_revision_applies_typed_changes_without_silent_external_permission(scenario,monkeypatch):
    from backend.app import development_model
    accepted,_,_=execute(scenario);user,_,_,req=scenario[0];id=accepted['plan_id'];v1=plan(id)['current_version_id'];views.confirm(id,v1,user)
    original=scenario[2]
    def mock(*args):
        output=json.loads(original(*args))
        if 'diagnoses' in output:output['request_adjustment']={'duration_weeks':2,'development_goal':'调整后的目标','constraints':{'language':'无要求'}}
        return json.dumps(output)
    monkeypatch.setattr(development_model,'completion',mock)
    accepted=life.revise(id,Revise(submission_id='conversational-revision',based_on_version_id=v1,instruction='缩短周期并改变目标',request=req),user);engine.execute(accepted['run_id'])
    data=views.detail(id,user)
    assert data['payload']['overview']['duration_weeks']==2
    assert data['request']['development_goal']=='调整后的目标' and data['request']['partner_goal_allowed'] is False
    assert data['plan']['confirmed_version_id']==v1


def test_three_parallel_plans_keep_owner_and_goal_snapshots(scenario):
    user,other,_,req=scenario[0];submissions=[]
    for n in range(3):
        owner=other if n==2 else user
        accepted=life.create(Submit(submission_id=f'parallel-plans-{n}',request=req.model_copy(update={'development_goal':f'不同目标 {n}'})),owner)
        submissions.append((accepted,owner,n))
    with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(engine.execute,[x[0]['run_id'] for x in submissions]))
    versions=set()
    for accepted,owner,n in submissions:
        d=views.detail(accepted['plan_id'],owner);assert d['runs'][0]['status']=='ready';assert d['payload']['overview']['development_goal']==f'不同目标 {n}'
        versions.add(d['plan']['current_version_id'])
    assert len(versions)==3


def test_ordinary_course_new_publication_keeps_historical_name_without_url(scenario):
    from backend.tests.test_enablement import published
    accepted,_,_=execute(scenario);user,_,admin,req=scenario[0];id=accepted['plan_id']
    row=enablement.detail('resource','test-course')
    metadata=enablement.ResourceMetadata(resource_type='course',title='新版课程名称',summary='新版本共享摘要',target_capability='交付',audience='工程师',source_platform='合成平台',source_url='https://example.com/new-course',capability_tag_ids=[req.targets[0].capability_tag_id])
    row=enablement.save('resource','test-course',enablement.ResourceSave(base_revision=row['revision'],metadata=metadata),admin['id']);published(row,admin)
    data=views.detail(id,user);assert not data['hidden']
    item=data['payload']['stages'][0]['items'][0]
    assert item['title']=='数据库课程' and item['availability']=='unavailable' and 'source_url' not in item
