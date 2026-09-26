"""Course/lab simplification against the dedicated PostgreSQL validation schema."""
import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from backend.app import enablement as service, resource_categories as categories, development_engine as engine
from backend.app.database import get_db
from backend.tests.conftest import make_user, auth_headers
from backend.tests.test_enablement import admin, metadata, create, grant, published, resolve


def test_categories_admin_only_add_rename_sort_and_preserve_snapshots(client, admin, metadata):
    path='/admin/enablement/resource-categories';h=auth_headers(admin)
    assert client.get(path).status_code==401
    ordinary=auth_headers(make_user('reader'))
    for method,url,body in [('POST',path,{'kind':'role','name':'新增'}),('PATCH',path+'/role-1',{'name':'改名','sort_order':1})]:
        assert client.request(method,url,headers=ordinary,json=body).status_code==403
    assert len(client.get(path,headers=h).json())==11
    new=client.post(path,headers=h,json={'kind':'role','name':'新岗位','sort_order':0})
    assert new.status_code==201
    cid=new.json()['id'];metadata['role_ids'].append(cid)
    row=published(grant(create(admin,metadata),admin),admin)
    with get_db() as conn: before=tuple(conn.execute('SELECT * FROM enablement_resource_versions').fetchone())
    assert client.patch(path+'/'+cid,headers=h,json={'name':'新岗位改名','sort_order':999}).status_code==200
    assert client.get(path,headers=h).json()[7]['name']=='新岗位改名'
    assert any(c['name']=='新岗位改名' for c in resolve(row)['roles'])
    with get_db() as conn: assert tuple(conn.execute('SELECT * FROM enablement_resource_versions').fetchone())==before
    assert client.post(path,headers=h,json={'kind':'role','name':'新岗位改名'}).status_code==409
    assert client.patch(path+'/'+cid,headers=h,json={'name':'有效名称','sort_order':-1}).status_code==422
    assert client.post(path,headers=h,json={'kind':'zone','name':'   '}).status_code==422
    # Seed is idempotent and must not restore edited names/order.
    with get_db() as conn: categories.initialize(conn)
    assert categories.listing()[7]['name']=='新岗位改名'


@pytest.mark.parametrize('kind',['course','lab'])
def test_multi_classification_one_resource_and_no_review(client,admin,metadata,kind):
    metadata.update(resource_type=kind,role_ids=['role-1','role-4'],zone_ids=['zone-1','zone-2'],level='advanced',duration_minutes=45)
    metadata.update({'course_goals':'迁移目标','outline':'备份与回退'} if kind=='course' else {'lab_goals':'验证回退','lab_requirements':'了解备份步骤'})
    row=published(grant(create(admin,metadata),admin),admin);h=auth_headers(make_user('reader'))
    for filters in [{},{'role_id':'role-1'},{'role_id':'role-4'},{'zone_id':'zone-1'},{'zone_id':'zone-2'},{'role_id':'role-4','zone_id':'zone-2','level':'advanced'}]:
        result=client.get('/enablement/resources',headers=h,params={'source_type':kind,**filters}).json()
        assert result['total']==1 and result['items'][0]['source_id']==row['source_id']
    detail=client.get(f'/enablement/resources/{kind}/{row["source_id"]}',headers=h).json()
    assert not {'difficulty','cost','source_platform','review','target_capability','account_requirement'} & detail.keys()
    assert client.post('/admin/enablement/resources/'+row['source_id']+'/review',headers=auth_headers(admin),json={'base_revision':row['revision']}).status_code==404
    with get_db() as conn:
        assert conn.execute('SELECT count(*) FROM enablement_resources').fetchone()[0]==1
        assert 'enablement_reviews' not in __import__('backend.app.storage_models',fromlist=['metadata']).metadata.tables
    redirect=client.post(f'/enablement/resources/{kind}/{row["source_id"]}/redirect',headers=h,json={'source_version':1})
    assert redirect.status_code==200 and redirect.json()['url']==metadata['source_url']


@pytest.mark.parametrize('field,value',[('cost','free'),('difficulty','advanced'),('source_platform','平台'),('target_capability','AI'),('capability_tag_ids',[]),('account_requirement','账号'),('language','中文'),('site','站点'),('prerequisites','无'),('product_direction','AI')])
def test_old_resource_editor_fields_rejected(client,admin,metadata,field,value):
    assert client.post('/admin/enablement/resources',headers=auth_headers(admin),json={'base_revision':0,'metadata':{**metadata,field:value}}).status_code==422


def test_category_kind_validation_and_cover_url(client,admin,metadata):
    path='/admin/enablement/resources';h=auth_headers(admin)
    for extra in [{'role_ids':['zone-1']},{'zone_ids':['missing']},{'role_ids':['role-1','role-1']},{'level':'intermediate'},{'cover_url':'javascript:alert(1)'},{'cover_url':'http://127.0.0.1/image.png'},{'lab_goals':'混用字段'}]:
        assert client.post(path,headers=h,json={'base_revision':0,'metadata':{**metadata,**extra}}).status_code==422
    assert client.post(path,headers=h,json={'base_revision':0,'metadata':{**metadata,'cover_url':'https://example.com/cover.png'}}).status_code==201


def test_legacy_snapshot_and_internal_tags_are_read_only(admin,metadata):
    row=published(grant(create(admin,metadata),admin),admin)
    with get_db() as conn:
        tag=conn.execute('SELECT id FROM capability_tags WHERE enabled=1 LIMIT 1').fetchone()[0]
        payload=json.loads(conn.execute('SELECT payload_json FROM enablement_resource_versions').fetchone()[0])
        payload.pop('level');payload.update(difficulty='intermediate',target_capability='历史迁移目标',source_platform='old',cost='paid',capability_tag_ids=[tag])
        raw=json.dumps(payload)
        conn.execute('UPDATE enablement_resource_versions SET payload_json=?',(raw,))
        conn.execute('UPDATE enablement_resources SET draft_json=?',(raw,))
    data=resolve(row,purpose='model')
    assert data['level']=='advanced' and data['course_goals']=='历史迁移目标' and data['capability_tag_ids']==[tag]
    assert 'cost' not in data and 'source_platform' not in data
    # Editing uses new fields only, while valid old tags remain internal.
    edit=service.detail('resource',row['source_id'])
    assert 'capability_tag_ids' not in edit['metadata']
    service.save('resource',row['source_id'],service.ResourceSave(base_revision=edit['revision'],metadata=edit['metadata']),row['created_by'])
    with get_db() as conn:
        assert conn.execute('SELECT payload_json FROM enablement_resource_versions').fetchone()[0]==raw
        assert json.loads(conn.execute('SELECT draft_json FROM enablement_resources').fetchone()[0])['capability_tag_ids']==[tag]
        conn.execute('UPDATE capability_tags SET enabled=0 WHERE id=?',(tag,))
    assert resolve(row,purpose='model')['capability_tag_ids']==[]


def test_ai_uses_categories_goals_outline_without_hard_category_gate(admin,metadata):
    metadata.update(title='学习资源',summary='实践准备',course_goals='迁移校验',outline='数据回退验证',role_ids=['role-1'],zone_ids=['zone-1'],cover_url='https://example.com/cover.png')
    row=published(grant(create(admin,metadata),admin),admin)
    with get_db() as conn:
        for word in ['CodeArts','迁移工程师','回退']:
            pool=engine.candidates(conn,{'development_direction':word},{'priorities':[{'name':word,'search_terms':[word]}]})
            assert len(pool)==1 and pool[0]['source_id']==row['source_id']
            assert 'cover_url' not in pool[0] and 'source_url' not in pool[0]
        # Different requested job/zone do not exclude an otherwise relevant resource.
        pool=engine.candidates(conn,{'development_direction':'AI平台工程师 ModelArts 回退'},{'priorities':[{'name':'回退','search_terms':['回退','ModelArts']}]})
        assert len(pool)==1 and pool[0]['capability_tag_ids']==[]
        output=engine.direct_resource_output({'target_partner_id':'p'},{'priorities':[{'name':'回退'}]},pool)
        assert output['stages'][0]['items'][0]['capability_tag_id']==''


def test_concurrent_category_add_does_not_lose_updates(client):
    def add(i):return categories.save(categories.CategoryCreate(kind='zone',name=f'并发分类{i}'))
    with ThreadPoolExecutor(max_workers=2) as pool: rows=list(pool.map(add,range(2)))
    assert {r['id'] for r in rows} <= {r['id'] for r in categories.listing()}
