import copy
import itertools
import json
from sqlalchemy.exc import DBAPIError
from .postgres_support import install_failure
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException

from backend.app import enablement as service
from backend.app.database import get_db
from backend.tests.conftest import make_user, make_partner, auth_headers


@pytest.fixture
def admin(client):
    return make_user('resource-admin',role='admin')


@pytest.fixture
def metadata():
    with get_db() as conn:
        tag=conn.execute('SELECT id FROM capability_tags WHERE enabled=1 LIMIT 1').fetchone()[0]
    return {'resource_type':'course','title':'合成课程','summary':'仅测试资源','level':'basic', 'role_ids':['role-1','role-4'], 'zone_ids':['zone-1'],
            'source_url':'https://example.com/course'}


def create(admin, metadata, kind='resource'):
    if kind=='case':
        make_partner()
        with get_db() as conn:
            conn.execute("INSERT INTO cases (id,partner_id,title,description,created_at,category_id,visible,updated_at) VALUES ('shared-case','partner-1',?,?,'2026-09-05','technical-1',0,'2026-09-05')",(metadata['title'],metadata['summary']))
            tag=conn.execute('SELECT id FROM capability_tags WHERE enabled=1 LIMIT 1').fetchone()[0]
        return {'source_id':'shared-case','published_version':1,'metadata':{**metadata,'capability_tag_ids':[tag]}}
    return service.save('resource','resource-test',service.ResourceSave(base_revision=0,metadata=metadata),admin['id'])


def grant(row,admin,kind='resource',flags=(True,True,True)):
    if kind=='case':
        with get_db() as conn: conn.execute('UPDATE cases SET visible=? WHERE id=?',(int(flags[0]),row['source_id']))
        return row
    return service.permissions(kind,row['source_id'],service.Permissions(base_revision=row['revision'],
        system_visible=flags[0],model_allowed=flags[1],partner_allowed=flags[2],reason='测试授权'),admin['id'])


def reviewed(row,admin,kind='resource'):
    return row


def published(row,admin,kind='resource'):
    if kind=='case': return row
    reviewed(row,admin,kind)
    return service.publish(kind,row['source_id'],service.Revision(base_revision=row['revision']),admin['id'])


def resolve(row,kind='resource',purpose='system',version=None):
    with get_db() as conn:
        return service.resolve_reference(conn,'case' if kind=='case' else row['metadata']['resource_type'],row['source_id'],version or row['published_version'],purpose)


@pytest.mark.parametrize('kind',['resource'])
@pytest.mark.parametrize('flags',list(itertools.product((False,True),repeat=3)))
def test_permissions_are_independent_and_whitelisted(admin,metadata,kind,flags):
    row=published(grant(create(admin,metadata,kind),admin,kind,flags),admin,kind)
    for purpose,expected in [('system',flags[0]),('model',flags[0] and flags[1]),('partner',flags[0] and flags[2])]:
        if not expected:
            with pytest.raises(HTTPException) as e: resolve(row,kind,purpose)
            assert e.value.status_code==403
        else:
            result=resolve(row,kind,purpose)
            assert 'INTERNAL' not in json.dumps(result)
            assert 'reviewer_id' not in result and '_permissions' not in result
            if purpose=='model': assert 'source_url' not in result
            if purpose=='partner':
                assert not {'source_id','source_type','source_version','contributor_id','capability_tag_ids'} & result.keys()


@pytest.mark.parametrize('resource_type',['course','lab'])
def test_resource_lifecycle_review_and_conflicts(client,admin,metadata,resource_type):
    metadata['resource_type']=resource_type
    headers=auth_headers(admin)
    response=client.post('/admin/enablement/resources',headers=headers,json={'base_revision':0,'metadata':metadata})
    assert response.status_code==201
    row=response.json(); path='/admin/enablement/resources/'+row['source_id']
    assert not row['system_visible'] and not row['model_allowed'] and not row['partner_allowed']
    assert client.post(path+'/review',headers=headers,json={'base_revision':1}).status_code==404
    assert client.put(path,headers=headers,json={'base_revision':99,'metadata':metadata}).status_code==409
    row=grant(row,admin)
    reviewed(row,admin)
    metadata['title']='编辑后的课程'
    row=client.put(path,headers=headers,json={'base_revision':row['revision'],'metadata':metadata}).json()
    row=published(row,admin)
    assert row['published_version']==1 and 'reviews' not in row
    metadata['title']='未发布草稿'
    draft=client.put(path,headers=headers,json={'base_revision':row['revision'],'metadata':metadata}).json()
    assert resolve(draft)['title']=='编辑后的课程'
    row=published(draft,admin)
    assert row['published_version']==2
    with pytest.raises(HTTPException): resolve(row,version=1)
    row=service.unpublish('resource',row['source_id'],service.Unpublish(base_revision=row['revision'],reason='普通下架'),admin['id'])
    with pytest.raises(HTTPException): resolve(row)
    assert len(row['versions'])==2 and row['status']=='unpublished'


@pytest.mark.parametrize('kind',['resource'])
def test_revocation_and_regrant_do_not_resurrect_old_content(admin,metadata,kind):
    row=published(grant(create(admin,metadata,kind),admin,kind),admin,kind)
    row=grant(row,admin,kind,(True,True,False))
    with pytest.raises(HTTPException): resolve(row,kind,'partner')
    row=grant(row,admin,kind)
    with pytest.raises(HTTPException): resolve(row,kind,'partner')
    row=published(row,admin,kind)
    assert resolve(row,kind,'partner')['title']=='合成课程'
    row=service.unpublish(kind,row['source_id'],service.Unpublish(base_revision=row['revision'],reason='发现敏感信息',sensitive=True),admin['id'])
    with pytest.raises(HTTPException): resolve(row,kind)
    assert row['status']=='revoked' and len(row['versions'])==2


def test_grant_needs_new_publication(admin,metadata):
    row=published(grant(create(admin,metadata),admin,flags=(True,False,False)),admin)
    row=grant(row,admin)
    with pytest.raises(HTTPException): resolve(row,purpose='model')
    row=published(row,admin)
    assert resolve(row,purpose='model')






@pytest.mark.parametrize('url',['javascript:alert(1)','https://secret:password@example.com','http://localhost:8000','http://127.0.0.1','http://192.168.1.1','https://example.com\\@evil.test','https://example.com:8100','http://[::1]','http://127.1','http://0x7f.0.0.1'])
def test_reject_unsafe_urls(client,admin,metadata,url):
    metadata['source_url']=url
    assert client.post('/admin/enablement/resources',headers=auth_headers(admin),json={'base_revision':0,'metadata':metadata}).status_code==422


def test_disabled_case_tags_and_invalid_resource_reference(admin,metadata):
    row=published(grant(create(admin,metadata),admin),admin)
    with get_db() as conn:
        with pytest.raises(HTTPException): service.resolve_reference(conn,'lab',row['source_id'],1)
        with pytest.raises(HTTPException): service.resolve_reference(conn,'course','invented',1)
    shared=published(grant(create(admin,metadata,'case'),admin,'case'),admin,'case')
    with get_db() as conn: conn.execute('UPDATE capability_tags SET enabled=0')
    assert resolve(shared,'case')['title']==metadata['title']
    assert resolve(row)['title']==metadata['title']




def test_concurrent_publish_only_one_version(admin,metadata):
    row=create(admin,metadata); reviewed(row,admin)
    barrier=threading.Barrier(2)
    def publish():
        barrier.wait()
        try:
            service.publish('resource',row['source_id'],service.Revision(base_revision=row['revision']),admin['id']); return 200
        except HTTPException as e: return e.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _:publish(),range(2)))==[200,409]
    assert len(service.detail('resource',row['source_id'])['versions'])==1


def test_publication_fault_rolls_back_version_and_pointer(admin,metadata):
    row=published(create(admin,metadata),admin); reviewed(row,admin)
    with get_db() as conn:
        install_failure(conn,'enablement_resources','UPDATE OF published_version',name='fail_publish')
    with pytest.raises(DBAPIError):
        service.publish('resource',row['source_id'],service.Revision(base_revision=row['revision']),admin['id'])
    after=service.detail('resource',row['source_id'])
    assert after['published_version']==1 and len(after['versions'])==1 and after['revision']==row['revision']
    with get_db() as conn: conn.execute('DROP TRIGGER fail_publish ON enablement_resources')
    assert service.publish('resource',row['source_id'],service.Revision(base_revision=row['revision']),admin['id'])['published_version']==2


@pytest.mark.parametrize('role',['anonymous','user'])
def test_all_new_api_operations_require_admin(client,metadata,role):
    from backend.app.main import app
    user=make_user('ordinary')
    headers=auth_headers(user) if role=='user' else {}
    expected={
        ('get','/admin/enablement/resource-categories'),('post','/admin/enablement/resource-categories'),
        ('patch','/admin/enablement/resource-categories/{category_id}'),
        ('get','/admin/enablement/resources'),('post','/admin/enablement/resources'),
        ('get','/admin/enablement/resources/export'),('get','/admin/enablement/resources/template'),
        ('post','/admin/enablement/resources/import'),('post','/admin/enablement/resources/batch'),
        ('get','/admin/enablement/resources/{source_id}'),('put','/admin/enablement/resources/{source_id}'),
        ('patch','/admin/enablement/resources/{source_id}/permissions'),
        ('post','/admin/enablement/resources/{source_id}/publish'),('post','/admin/enablement/resources/{source_id}/unpublish'),
    }
    operations=set()
    for path,item in app.openapi()['paths'].items():
        if not (path.startswith('/admin/enablement') or path.startswith('/admin/cases/')): continue
        for method in item:
            if method not in ('get','post','put','patch','delete'):continue
            operations.add((method,path))
            target=path.replace('{source_id}','unknown').replace('{category_id}','unknown')
            response=client.request(method,target,headers=headers,json={})
            assert response.status_code==(403 if role=='user' else 401),(method,path,response.text)
    assert operations==expected
