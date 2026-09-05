import copy
import itertools
import json
import sqlite3
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
    return {'resource_type':'course','title':'合成课程','summary':'仅测试资源','target_capability':'数据库迁移',
            'source_platform':'合成平台','source_url':'https://example.com/course','capability_tag_ids':[tag]}


def create(admin, metadata, kind='resource'):
    if kind=='case':
        make_partner()
        with get_db() as conn:
            conn.execute("INSERT INTO cases VALUES ('shared-case','partner-1','INTERNAL TITLE','INTERNAL SECRET','2026-09-05')")
        metadata={k:v for k,v in metadata.items() if k not in ('resource_type','target_capability')}
        metadata.update(methods='可共享方法',contributor_role='仅承担迁移实施')
        return service.save('case','shared-case',service.ShareSave(base_revision=0,metadata=metadata),admin['id'])
    return service.save('resource','resource-test',service.ResourceSave(base_revision=0,metadata=metadata),admin['id'])


def grant(row,admin,kind='resource',flags=(True,True,True)):
    return service.permissions(kind,row['source_id'],service.Permissions(base_revision=row['revision'],
        system_visible=flags[0],model_allowed=flags[1],partner_allowed=flags[2],reason='测试授权'),admin['id'])


def reviewed(row,admin,kind='resource'):
    return service.review(kind,row['source_id'],service.Review(base_revision=row['revision'],link_status='available',content_checked=True,authorization_checked=True),admin['id'])


def published(row,admin,kind='resource'):
    reviewed(row,admin,kind)
    return service.publish(kind,row['source_id'],service.Revision(base_revision=row['revision']),admin['id'])


def resolve(row,kind='resource',purpose='system',version=None):
    with get_db() as conn:
        return service.resolve_reference(conn,'case' if kind=='case' else row['metadata']['resource_type'],row['source_id'],version or row['published_version'],purpose)


@pytest.mark.parametrize('kind',['resource','case'])
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
    assert client.post(path+'/publish',headers=headers,json={'base_revision':1}).status_code==409
    assert client.put(path,headers=headers,json={'base_revision':99,'metadata':metadata}).status_code==409
    row=grant(row,admin)
    reviewed(row,admin)
    metadata['title']='编辑后的课程'
    row=client.put(path,headers=headers,json={'base_revision':row['revision'],'metadata':metadata}).json()
    assert client.post(path+'/publish',headers=headers,json={'base_revision':row['revision']}).status_code==409
    row=published(row,admin)
    assert row['published_version']==1 and len(row['reviews'])==2
    metadata['title']='未发布草稿'
    draft=client.put(path,headers=headers,json={'base_revision':row['revision'],'metadata':metadata}).json()
    assert resolve(draft)['title']=='编辑后的课程'
    row=published(draft,admin)
    assert row['published_version']==2
    with pytest.raises(HTTPException): resolve(row,version=1)
    row=service.unpublish('resource',row['source_id'],service.Unpublish(base_revision=row['revision'],reason='普通下架'),admin['id'])
    with pytest.raises(HTTPException): resolve(row)
    assert len(row['versions'])==2 and row['status']=='unpublished'


@pytest.mark.parametrize('kind',['resource','case'])
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


def test_case_independent_version_ownership_and_deletion(client,admin,metadata):
    row=published(grant(create(admin,metadata,'case'),admin,'case'),admin,'case')
    with get_db() as conn:
        conn.execute("UPDATE cases SET title='NEW INTERNAL',description='NEW SECRET' WHERE id='shared-case'")
    assert resolve(row,'case','model')['title']=='合成课程'
    assert resolve(row,'case','partner')['contributor_role']=='仅承担迁移实施'
    response=client.delete('/cases/shared-case',headers=auth_headers(admin))
    assert response.status_code==409
    with get_db() as conn:
        assert conn.execute("SELECT partner_id FROM cases WHERE id='shared-case'").fetchone()[0]=='partner-1'
        assert conn.execute("SELECT ai_profile FROM partners WHERE id='partner-1'").fetchone()[0] is None
        conn.execute("UPDATE partners SET status='disabled' WHERE id='partner-1'")
    with pytest.raises(HTTPException): resolve(row,'case','partner')


def test_orphan_case_cannot_share(admin,metadata):
    payload=service.ShareSave(base_revision=0,metadata={'title':'shared','summary':'summary','methods':'method','contributor_role':'role','source_platform':'platform','source_url':'https://example.com'})
    with get_db() as conn:
        conn.execute('PRAGMA foreign_keys=OFF')
        conn.execute("INSERT INTO cases VALUES ('orphan','missing','internal','private','2026')")
    with pytest.raises(HTTPException) as e: service.save('case','orphan',payload,admin['id'])
    assert e.value.status_code==409
    with get_db() as conn: assert conn.execute('SELECT COUNT(*) FROM case_share_configs').fetchone()[0]==0


@pytest.mark.parametrize('url',['javascript:alert(1)','https://secret:password@example.com','http://localhost:8000','http://127.0.0.1','http://192.168.1.1','https://example.com\\@evil.test','https://example.com:8100','http://[::1]'])
def test_reject_unsafe_urls(client,admin,metadata,url):
    metadata['source_url']=url
    assert client.post('/admin/enablement/resources',headers=auth_headers(admin),json={'base_revision':0,'metadata':metadata}).status_code==422


def test_tags_missing_disabled_and_invalid_reference(admin,metadata):
    metadata['capability_tag_ids']=['missing']
    with pytest.raises(HTTPException): create(admin,metadata)
    with get_db() as conn: metadata['capability_tag_ids']=[conn.execute('SELECT id FROM capability_tags LIMIT 1').fetchone()[0]]
    row=published(grant(create(admin,metadata),admin),admin)
    with get_db() as conn:
        with pytest.raises(HTTPException): service.resolve_reference(conn,'lab',row['source_id'],1)
        with pytest.raises(HTTPException): service.resolve_reference(conn,'course','invented',1)
        conn.execute('UPDATE capability_tags SET enabled=0 WHERE id=?',(metadata['capability_tag_ids'][0],))
    with pytest.raises(HTTPException): resolve(row)


@pytest.mark.parametrize('link_status,content,authorization',[('unknown',True,True),('unavailable',True,True),('available',False,True),('available',True,False)])
def test_publish_requires_latest_complete_review(admin,metadata,link_status,content,authorization):
    row=create(admin,metadata); reviewed(row,admin)
    service.review('resource',row['source_id'],service.Review(base_revision=row['revision'],link_status=link_status,content_checked=content,authorization_checked=authorization),admin['id'])
    with pytest.raises(HTTPException): service.publish('resource',row['source_id'],service.Revision(base_revision=row['revision']),admin['id'])


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
        conn.execute("CREATE TRIGGER fail_publish BEFORE UPDATE OF published_version ON enablement_resources BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
    with pytest.raises(sqlite3.DatabaseError):
        service.publish('resource',row['source_id'],service.Revision(base_revision=row['revision']),admin['id'])
    after=service.detail('resource',row['source_id'])
    assert after['published_version']==1 and len(after['versions'])==1 and after['revision']==row['revision']
    with get_db() as conn: conn.execute('DROP TRIGGER fail_publish')
    assert service.publish('resource',row['source_id'],service.Revision(base_revision=row['revision']),admin['id'])['published_version']==2


@pytest.mark.parametrize('role',['anonymous','user'])
def test_all_new_api_operations_require_admin(client,metadata,role):
    from backend.app.main import app
    user=make_user('ordinary')
    headers=auth_headers(user) if role=='user' else {}
    operations=0
    for path,item in app.openapi()['paths'].items():
        if not (path.startswith('/admin/enablement') or path.startswith('/admin/cases/')): continue
        for method in item:
            if method not in ('get','post','put','patch'):continue
            path=path.replace('{source_id}','unknown')
            response=client.request(method,path,headers=headers,json={})
            assert response.status_code==(403 if role=='user' else 401),(method,path,response.text)
            operations+=1
    assert operations==14


def test_case_delete_and_initial_share_are_serialized(client,admin,metadata):
    make_partner()
    with get_db() as conn:
        conn.execute("INSERT INTO cases VALUES ('race-case','partner-1','internal','private','2026')")
    payload=service.ShareSave(base_revision=0,metadata={'title':'shared','summary':'summary','methods':'method','contributor_role':'role','source_platform':'platform','source_url':'https://example.com'})
    barrier=threading.Barrier(2)
    def share():
        barrier.wait()
        try: service.save('case','race-case',payload,admin['id']); return 200
        except HTTPException as e:return e.status_code
    def delete():
        barrier.wait()
        return client.delete('/cases/race-case',headers=auth_headers(admin)).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        a=pool.submit(share);b=pool.submit(delete);outcomes=(a.result(),b.result())
    assert outcomes in ((200,409),(409,204))
    with get_db() as conn: assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
