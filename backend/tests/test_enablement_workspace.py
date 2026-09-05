import json
import sqlite3
import time
from pathlib import Path
import pytest
from backend.app import enablement as service
from backend.app.database import get_db
from backend.app.enablement_schema import migrate_to_v11
from backend.tests.conftest import make_user, make_partner, make_task, auth_headers
from backend.tests.test_enablement import admin, metadata, create, grant, published


def test_catalog_auth_unknown_filters_and_published_snapshot(client,admin,metadata):
    user=make_user('reader');h=auth_headers(user)
    row=published(grant(create(admin,metadata),admin,flags=(True,False,False)),admin)
    assert client.get('/enablement/resources').status_code==401
    r=client.get('/enablement/resources',headers=h)
    assert r.status_code==200 and r.headers['cache-control']=='no-store'
    item=r.json()['items'][0]
    assert item['audience']=='未知' and item['duration_minutes'] is None
    assert item['status']=='published' and item['review']['content_checked']==1
    assert not {'draft_json','model_allowed','partner_allowed','reviewer_id'} & item.keys()
    for query,count in [('q=合成',1),('q=不存在',0),('source_type=lab',0),('audience=未知',1),('difficulty=unknown',1),('status=unpublished',0),('page=2',0),('capability_tag_id=missing',0)]:
        assert len(client.get('/enablement/resources?'+query,headers=h).json()['items'])==count
    metadata['title']='DRAFT SECRET'
    service.save('resource',row['source_id'],service.ResourceSave(base_revision=row['revision'],metadata=metadata),admin['id'])
    assert 'DRAFT SECRET' not in client.get('/enablement/resources',headers=h).text
    assert client.get('/enablement/resource-filters',headers=h).json()['capabilities']
    assert client.get('/admin/enablement/resources',headers=h).status_code==403


@pytest.mark.parametrize('kind',['resource','case'])
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


@pytest.mark.parametrize('field,value',[('audience','工程师'),('product_direction','数据库'),('difficulty','advanced'),('language','中文'),('site','中国站'),('cost','free'),('account_requirement','企业账号'),('environment_requirement','自备环境'),('prerequisites','SQL基础')])
def test_all_metadata_filters(client,admin,metadata,field,value):
    metadata[field]=value
    published(grant(create(admin,metadata),admin),admin)
    h=auth_headers(admin)
    assert client.get('/enablement/resources',params={field:value},headers=h).json()['total']==1
    assert client.get('/enablement/resources',params={field:'nonmatching'},headers=h).json()['total']==0


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


def test_shared_context_is_current_shared_version_not_internal_evidence(client,admin,metadata):
    row=published(grant(create(admin,metadata,'case'),admin,'case'),admin,'case')
    h=auth_headers(make_user('reader'))
    data=client.get('/enablement/context?case_id=shared-case&case_version=1',headers=h).json()
    assert data['partner'] is None and data['evidence']==[]
    assert 'INTERNAL' not in json.dumps(data)
    assert data['shared_case']['contributor_id']=='partner-1'
    assert client.get('/enablement/resources?contributor_id=partner-1',headers=h).json()['total']==1
    assert client.get('/enablement/resources?contributor_id=other',headers=h).json()['total']==0
    with get_db() as conn: conn.execute('UPDATE capability_tags SET enabled=0 WHERE id=?',(metadata['capability_tag_ids'][0],))
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
    class Failing(sqlite3.Connection):
        count=0
        def execute(self,sql,*args,**kwargs):
            if sql.startswith('CREATE ') or sql.startswith("UPDATE app_metadata SET value='11'"):
                self.count+=1
                if fail_at==self.count: raise sqlite3.OperationalError('synthetic migration failure')
            return super().execute(sql,*args,**kwargs)
    path=tmp_path/'migration.db'
    with sqlite3.connect(path) as conn:
        conn.executescript("CREATE TABLE app_metadata(key TEXT PRIMARY KEY,value TEXT); INSERT INTO app_metadata VALUES('schema_version','10'); CREATE TABLE users(id TEXT PRIMARY KEY); INSERT INTO users VALUES ('retained');")
    conn=sqlite3.connect(path,factory=Failing)
    if fail_at:
        with pytest.raises(sqlite3.OperationalError): migrate_to_v11(conn)
        assert conn.execute("SELECT value FROM app_metadata").fetchone()[0]=='10'
        assert conn.execute("SELECT count(*) FROM sqlite_master WHERE name='resource_redirect_events'").fetchone()[0]==0
    conn.close()
    with sqlite3.connect(path) as conn:
        migrate_to_v11(conn);migrate_to_v11(conn)
        assert conn.execute('SELECT * FROM users').fetchall()==[('retained',)]
        assert conn.execute('SELECT value FROM app_metadata').fetchone()[0]=='11'
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
