import json
import time
from pathlib import Path
import pytest
from backend.app import enablement as service
from backend.app.database import get_db
from .test_enablement_migration import assert_initialization_rollback_and_retry
from backend.tests.conftest import make_user, make_partner, make_task, auth_headers
from backend.tests.test_enablement import admin, metadata, create, grant, published


def test_catalog_auth_unknown_filters_and_published_snapshot(client,admin,metadata):
    user=make_user('reader');h=auth_headers(user)
    row=published(grant(create(admin,metadata),admin,flags=(True,False,False)),admin)
    assert client.get('/enablement/resources').status_code==401
    r=client.get('/enablement/resources',headers=h)
    assert r.status_code==200 and r.headers['cache-control']=='no-store'
    item=r.json()['items'][0]
    assert item['level']=='basic' and item['duration_minutes'] is None
    assert item['status']=='published' and 'review' not in item
    assert not {'draft_json','model_allowed','partner_allowed','reviewer_id'} & item.keys()
    for query,count in [('q=合成',1),('q=不存在',0),('source_type=lab',0),('role_id=role-1',1),('level=advanced',0),('status=unpublished',0),('page=2',0),('capability_tag_id=missing',0)]:
        assert len(client.get('/enablement/resources?'+query,headers=h).json()['items'])==count
    metadata['title']='DRAFT SECRET'
    service.save('resource',row['source_id'],service.ResourceSave(base_revision=row['revision'],metadata=metadata),admin['id'])
    assert 'DRAFT SECRET' not in client.get('/enablement/resources',headers=h).text
    assert client.get('/enablement/resource-filters',headers=h).json()['roles']
    assert client.get('/admin/enablement/resources',headers=h).status_code==403


@pytest.mark.parametrize('kind',['resource'])
@pytest.mark.parametrize('actor_role',['user','admin'])
def test_workspace_revocation_shared_projection_and_redirect(client,admin,metadata,kind,actor_role):
    reader=make_user('reader',role=actor_role);h=auth_headers(reader)
    row=published(grant(create(admin,metadata,kind),admin,kind,flags=(True,False,False)),admin,kind)
    source='case' if kind=='case' else 'course';path=f'/enablement/resources/{source}/{row["source_id"]}'
    response=client.get(path,headers=h);assert response.status_code==200
    assert 'INTERNAL' not in response.text
    assert client.post(path+'/redirect',headers=h,json={'source_version':1,'url':'https://evil.example'}).status_code==422
    event=client.post(path+'/redirect',headers=h,json={'source_version':1})
    assert event.status_code==200 and event.json()['event_label']=='发起跳转'
    with get_db() as conn:
        stored=conn.execute('SELECT * FROM resource_redirect_events').fetchone()
        assert stored['actor_user_id']==reader['id'] and stored['event_type']=='redirect_initiated'
        assert 'url' not in stored.keys()
    row=grant(row,admin,kind,(False,False,False))
    assert client.get(path,headers=h).status_code==404
    assert client.post(path+'/redirect',headers=h,json={'source_version':1}).status_code==404
    assert client.get('/enablement/resources',headers=h).json()['total']==0
    row=grant(row,admin,kind)
    assert client.get(path,headers=h).status_code==404
    row=published(row,admin,kind)
    assert client.get(path,headers=h).status_code==200
    assert client.get(path+'?source_version=1',headers=h).status_code==404
    assert client.post(path+'/redirect',headers=h,json={'source_version':1}).status_code==404
    with get_db() as conn: assert conn.execute('SELECT count(*) FROM resource_redirect_events').fetchone()[0]==1


@pytest.mark.parametrize('field,value',[('role_id','role-1'),('zone_id','zone-1'),('level','basic')])
def test_all_metadata_filters(client,admin,metadata,field,value):
    published(grant(create(admin,metadata),admin),admin)
    h=auth_headers(admin)
    assert client.get('/enablement/resources',params={field:value},headers=h).json()['total']==1
    alternate='advanced' if field=='level' else 'nonmatching'
    assert client.get('/enablement/resources',params={field:alternate},headers=h).json()['total']==0


def test_context_owner_selection_and_no_inferred_training(client,admin,metadata):
    a=make_user('a');b=make_user('b');make_partner();task=make_task(a,'客户原始需求')
    path=f'/enablement/context?partner_id=partner-1&task_id={task}'
    assert client.get(path,headers=auth_headers(b)).status_code==404
    for actor in [a,admin]:
        data=client.get(path,headers=auth_headers(actor)).json()
        assert data['partner']['id']=='partner-1'
        assert data['project']=={'task_id':task,'requirement':'客户原始需求','risk_notes':'资料需复核','risk_status':'待能力发展流程复核'}
        assert 'training_needs' not in data and 'plan' not in data
    make_partner('other')
    assert client.get(path.replace('partner-1','other'),headers=auth_headers(a)).status_code==404
    with get_db() as conn: conn.execute("UPDATE partners SET status='disabled' WHERE id='partner-1'")
    assert client.get(path,headers=auth_headers(a)).status_code==404


def test_case_context_uses_current_visibility_without_tag_or_version_gate(client,admin,metadata):
    row=published(grant(create(admin,metadata,'case'),admin,'case'),admin,'case')
    h=auth_headers(make_user('reader'))
    data=client.get('/enablement/context?case_id=shared-case&case_version=1',headers=h).json()
    assert data['partner'] is None and data['evidence']==[]
    assert 'INTERNAL' not in json.dumps(data)
    assert data['shared_case']['contributor_id']=='partner-1'
    assert client.get('/enablement/resources?contributor_id=partner-1',headers=h).json()['total']==1
    assert client.get('/enablement/resources?contributor_id=other',headers=h).json()['total']==0
    with get_db() as conn: conn.execute('UPDATE capability_tags SET enabled=0 WHERE id=?',(row['metadata']['capability_tag_ids'][0],))
    assert client.get('/enablement/context?case_id=shared-case',headers=h).status_code==200
    with get_db() as conn: conn.execute("UPDATE cases SET visible=0 WHERE id='shared-case'")
    assert client.get('/enablement/context?case_id=shared-case',headers=h).status_code==404
    assert client.get('/enablement/resources',headers=h).json()['total']==0


def test_task_type_retains_owner_and_admin_semantics(client,admin):
    a=make_user('a');b=make_user('b');ta=make_task(a,'A');make_task(b,'B')
    for actor in [a,b]:
        response=client.get('/agent/tasks?task_type=partner_match',headers=auth_headers(actor)).json()
        assert response['total']==1 and response['items'][0]['task_type']=='partner_match'
        assert client.get('/agent/tasks?task_type=development_plan',headers=auth_headers(actor)).json()['total']==0
    assert client.get('/admin/tasks?task_type=partner_match',headers=auth_headers(admin)).json()['total']==2
    assert client.get('/agent/tasks/'+ta,headers=auth_headers(b)).status_code==404
    assert client.get('/agent/tasks/'+ta,headers=auth_headers(a)).json()['task_type']=='partner_match'
    assert client.get('/agent/tasks?task_type=unknown',headers=auth_headers(a)).status_code==422


@pytest.mark.parametrize('fail_at',[1,2,3,None])
def test_v11_transaction_failure_recovery_and_idempotence(tmp_path,fail_at):
    assert_initialization_rollback_and_retry(fail_at)


def test_catalog_3000_published_resources_search_p95(client,admin,metadata,record_property,monkeypatch):
    from backend.app.enablement_catalog import catalog
    resource=published(grant(create(admin,metadata),admin),admin)
    case=published(grant(create(admin,metadata,'case'),admin,'case'),admin,'case')
    with get_db() as conn:
        for index in range(999):
            conn.execute("INSERT INTO cases (id,partner_id,title,description,created_at,category_id,visible,updated_at) VALUES (?,'partner-1',?,'案例正文','2026','technical-1',1,'2026')",(f'case-{index}',f'迁移案例 {index}'))
        for kind,row,count in [('resource',resource,1999)]:
            table,versions,key=service.TABLES[kind]
            head=dict(conn.execute(f'SELECT * FROM {table} WHERE {key}=?',(row['source_id'],)).fetchone())
            version=dict(conn.execute(f'SELECT * FROM {versions} WHERE source_id=?',(row['source_id'],)).fetchone())
            for index in range(count):
                source_id=f'performance-{kind}-{index}'
                payload=json.loads(version['payload_json']);payload['title']=f'迁移资源 {index}'
                if kind=='resource': payload['resource_type']='course' if index%2 else 'lab'
                else: conn.execute('INSERT INTO cases (id,partner_id,title,description,created_at) VALUES (?,?,?,?,?)',(source_id,'partner-1','内部标题','不可共享正文','2026'))
                cloned={**head,key:source_id};snapshot={**version,'source_id':source_id,'payload_json':json.dumps(payload,ensure_ascii=False)}
                for target,values in [(table,cloned),(versions,snapshot)]:
                    conn.execute(f"INSERT INTO {target} ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",list(values.values()))
    assert catalog()['total']==3000
    elapsed=[]
    for index in range(60):
        started=time.perf_counter()
        result=catalog(q='迁移',page=index%3+1)
        elapsed.append(time.perf_counter()-started)
        # Only the generated clone titles contain the search term.
        assert result['total']==2998 and len(result['items'])==12
    ordered=sorted(elapsed);p95=ordered[56]
    record_property('catalog_performance',json.dumps({'course_lab_count':2000,'case_count':1000,'samples':60,
        'p50_seconds':ordered[29],'p95_seconds':p95,'max_seconds':max(elapsed),
        'scope':'catalog Python service: SQL search/count + permission projection + 12 details; no HTTP/browser/external source time'}))
    assert p95<2
    from backend.app import development_engine as engine
    request={'constraints':dict.fromkeys(['language','site','account','network','environment','cost','budget'],'无要求'),'trainee_role':'工程师'}
    diagnosis=[{'problem_type':'trainable_gap','capability_tag_id':case['metadata']['capability_tag_ids'][0], 'target_requirement':'迁移'}]
    from backend.app.postgres_storage import Connection
    original_execute=Connection.execute
    sql_times=[];sql_count=[];query_time=0;query_count=0
    def measured(conn,*args,**kwargs):
        nonlocal query_time,query_count
        started=time.perf_counter()
        try:return original_execute(conn,*args,**kwargs)
        finally:query_time+=time.perf_counter()-started;query_count+=1
    monkeypatch.setattr(Connection,'execute',measured)
    timings=[]
    for _ in range(30):
        query_time=0;query_count=0
        started=time.perf_counter()
        with get_db() as conn:pool=engine.candidates(conn,request,diagnosis)
        timings.append(time.perf_counter()-started)
        sql_times.append(query_time);sql_count.append(query_count)
        assert len(pool)==100
    ordered=sorted(timings)
    record_property('candidate_performance',json.dumps({'course_lab_count':2000,'case_count':1000,'samples':30,
        'p50_seconds':ordered[14],'p95_seconds':ordered[28],'max_seconds':max(timings),
        'sql_query_count':sql_count,'sql_seconds':sql_times,'processing_seconds':[t-q for t,q in zip(timings,sql_times)],
        'scope':'model-safe candidate SQL, permission and constraints filtering; 100 candidate cap; no model/network/browser'}))
    assert ordered[28]<2


def test_pg_catalog_initialization_preserves_existing_rows(client):
    from .postgres_support import snapshot
    from backend.app.database import initialize_storage
    with get_db() as conn: before=snapshot(conn)
    initialize_storage();initialize_storage()
    with get_db() as conn:
        assert snapshot(conn)==before
        assert conn.execute('SELECT count(*) FROM resource_redirect_events').fetchone()[0]==0
