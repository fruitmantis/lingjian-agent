"""The global and partner shortcuts read one catalogue, without new storage."""
from pathlib import Path
import pytest
from backend.app.database import get_db
from backend.app.routers import partner_materials
from .conftest import auth_headers,make_partner,make_user

@pytest.fixture
def access(client,monkeypatch):
    from backend.app import profile_sources
    monkeypatch.setattr(profile_sources,'resolve_model_record',lambda _: {})
    monkeypatch.setattr(profile_sources.development_model,'completion',lambda *_:'{"sections":[]}')
    return auth_headers(make_user('catalogue-admin',role='admin')), auth_headers(make_user('catalogue-user')), make_partner()['id']

def add_case(client,admin,pid,title='资料条目',category='technical-1'):
    r=client.post('/cases',headers=admin,json={'partner_id':pid,'title':title,'category_id':category})
    assert r.status_code==201,r.text
    return r.json()['id']

def add_document(client,admin,pid,name='旧资料.txt',body=b'original text'):
    r=client.post(f'/partners/{pid}/documents',headers=admin,files={'file':(name,body)})
    assert r.status_code==201,r.text
    return r.json()['id']

def test_catalogue_filters_pagination_and_single_entry_for_multiple_files(client,access):
    admin,user,pid=access;other=make_partner(partner_id='partner-other',name='另一个伙伴')['id']
    cid=add_case(client,admin,pid,'技术_100%')
    for name in ('a.txt','b.txt'):
        assert client.post(f'/cases/{cid}/deliverables',headers=admin,files={'file':(name,b'native')}).status_code==201
    add_case(client,admin,other,'营销资料','marketing-1')
    did=add_document(client,admin,pid)
    profile=add_document(client,admin,pid,'画像原件.txt')
    with get_db() as conn: conn.execute("UPDATE partner_documents SET doc_category='profile_import' WHERE id=?",(profile,))
    assert client.get('/admin/partner-materials',headers=user).status_code==403
    all_rows=client.get('/admin/partner-materials',headers=admin).json()
    assert all_rows['total']==3
    assert set(all_rows['partners'][0])=={'id','name'}
    assert all(profile!=r['id'] for r in all_rows['items'])
    rows=client.get('/admin/partner-materials',headers=admin,params={'partner_id':pid}).json()
    assert rows['total']==2
    entry=next(r for r in rows['items'] if r['id']==cid)
    assert entry['file_count']==2 and entry['processing_status']=='ready' and not entry['visible']
    assert not {'file_path','extracted_text','ai_profile'}&entry.keys()
    assert client.get('/admin/partner-materials',headers=admin,params={'category_group':'technical','category_id':'technical-1','q':'_100%'}).json()['total']==1
    assert client.get('/admin/partner-materials',headers=admin,params={'q':"' OR 1=1 --"}).json()['total']==0
    assert client.get('/admin/partner-materials',headers=admin,params={'category_group':'unclassified'}).json()['items'][0]['id']==did
    pages=[client.get('/admin/partner-materials',headers=admin,params={'page_size':1,'page':p}).json()['items'][0]['id'] for p in (1,2,3)]
    assert len(set(pages))==3
    assert client.get('/admin/partner-materials',headers=admin,params={'category_group':'invalid'}).status_code==422
    assert client.get('/admin/partner-materials',headers=admin,params={'partner_id':'missing'}).status_code==404


def test_classify_preserves_file_id_original_and_cached_text(client,access):
    admin,user,pid=access;did=add_document(client,admin,pid)
    with get_db() as conn: old=dict(conn.execute('SELECT * FROM partner_documents WHERE id=?',(did,)).fetchone())
    payload={'partner_id':pid,'title':'整理后的资料','category_id':'delivery-2'}
    url=f'/admin/partner-materials/documents/{did}/classify'
    assert client.put(url,headers=user,json=payload).status_code==403
    result=client.put(url,headers=admin,json=payload)
    assert result.status_code==200,result.text
    assert result.json()['id']==did and result.json()['visible'] is False
    with get_db() as conn:
        assert not conn.execute('SELECT id FROM partner_documents WHERE id=?',(did,)).fetchone()
        new=dict(conn.execute('SELECT * FROM deliverables WHERE id=?',(did,)).fetchone())
        for key in ('id','file_path','preview_path','extracted_text','created_at','processed_at'): assert new[key]==old[key]
        assert conn.execute('SELECT COUNT(*) FROM cases WHERE id=?',(did,)).fetchone()[0]==1
    assert Path(new['file_path']).read_bytes()==b'original text'
    assert client.get('/admin/partner-materials',headers=admin,params={'partner_id':pid}).json()['total']==1
    assert client.get(f'/cases/{did}/deliverables/{did}/file',headers=admin).content==b'original text'
    assert client.get(f'/cases/{did}/deliverables/{did}/file',headers=user).status_code==404
    assert client.put(url,headers=admin,json=payload).status_code==404


@pytest.mark.parametrize('blocked',['profile_import','processing','rollback','commit_failure'])
def test_classification_guards_and_transaction(client,access,monkeypatch,blocked):
    admin,_,pid=access;did=add_document(client,admin,pid)
    with get_db() as conn:
        if blocked=='profile_import':conn.execute("UPDATE partner_documents SET doc_category='profile_import' WHERE id=?",(did,))
        elif blocked=='processing':conn.execute("UPDATE partner_documents SET processing_status='processing' WHERE id=?",(did,))
    if blocked=='rollback':monkeypatch.setattr(partner_materials,'record_audit',lambda *_a,**_k:(_ for _ in ()).throw(RuntimeError('synthetic audit failure')))
    if blocked=='commit_failure':
        from contextlib import contextmanager
        original_get_db=partner_materials.get_db
        @contextmanager
        def failed_commit():
            with original_get_db() as conn:
                yield conn
                raise RuntimeError('synthetic commit failure')
        monkeypatch.setattr(partner_materials,'get_db',failed_commit)
    callbacks=[]
    monkeypatch.setattr(partner_materials,'_process_profile',lambda p:callbacks.append(p))
    call=lambda:client.put(f'/admin/partner-materials/documents/{did}/classify',headers=admin,json={'partner_id':pid,'title':'资料','category_id':'delivery-1'})
    assert call().status_code==(500 if blocked in ('rollback','commit_failure') else 409)
    assert callbacks==[]
    with get_db() as conn:
        row=conn.execute('SELECT file_path FROM partner_documents WHERE id=?',(did,)).fetchone()
        assert row and Path(row['file_path']).exists()
        assert not conn.execute('SELECT id FROM cases WHERE id=?',(did,)).fetchone()
        assert not conn.execute('SELECT id FROM deliverables WHERE id=?',(did,)).fetchone()


@pytest.mark.parametrize('kind',['case','document'])
def test_file_replacement_keeps_id_validates_first_and_withdraws_legacy_profile(client,access,monkeypatch,kind):
    import json
    from backend.app import profile_sources
    from .test_profile_report import merge_result
    def completed(_config,messages,_schema):
        data=json.loads(messages[-1]['content'])
        if 'material' not in data:return json.dumps(merge_result(data))
        return json.dumps({'sections':[{'chapter':5,'summary':data['material'],'quotes':[data['material']]}]})
    monkeypatch.setattr(profile_sources.development_model,'completion',completed)
    admin,user,pid=access
    if kind=='case':
        cid=add_case(client,admin,pid);endpoint=f'/cases/{cid}/deliverables'
        did=client.post(endpoint,headers=admin,files={'file':('old.txt',b'old text')}).json()['id']
    else:
        did=add_document(client,admin,pid,body=b'old text');endpoint=f'/partners/{pid}/documents'
    organized=client.post(f'/partners/{pid}/profile',headers=admin)
    assert organized.status_code==200
    before_profile=organized.json()['ai_profile']
    assert 'old text' in before_profile
    url=endpoint+'/'+did
    assert client.put(url,headers=user,files={'file':('new.txt',b'new text')}).status_code==403
    assert client.put(url,headers=admin,files={'file':('fake.pdf',b'invalid PDF')}).status_code==400
    assert client.get(url+'/file',headers=admin).content==b'old text'
    response=client.put(url,headers=admin,files={'file':('new.txt',b'new text')})
    assert response.status_code==200 and response.json()['id']==did
    assert client.get(url+'/file',headers=admin).content==b'new text'
    assert client.get(url+'/preview',headers=admin).text=='new text'
    assert len(client.get(endpoint,headers=admin).json())==1
    with get_db() as conn:
        after_profile=conn.execute('SELECT ai_profile FROM partners WHERE id=?',(pid,)).fetchone()[0]
        assert after_profile!=before_profile
        assert 'old text' not in after_profile and profile_sources.CHANGED in after_profile



def test_pending_classification_processes_committed_cached_source_once(client,access,monkeypatch):
    import json
    from backend.app import profile_sources
    admin,_,pid=access
    did=add_document(client,admin,pid,body=b'synthetic pending capability')
    with get_db() as conn:
        old=dict(conn.execute('SELECT * FROM partner_documents WHERE id=?',(did,)).fetchone())
        source=next(s for s in profile_sources.sources(conn,pid) if s['id']==did)
        profile_sources.put(conn,source,'pending')
    calls=[]
    def complete(config,messages,schema):
        material=json.loads(messages[-1]['content'])['material']
        calls.append(material)
        # A fresh connection can see the committed conversion before model work.
        with get_db() as conn:
            assert not conn.execute('SELECT id FROM partner_documents WHERE id=?',(did,)).fetchone()
            assert conn.execute('SELECT id FROM cases WHERE id=?',(did,)).fetchone()
            attachment=dict(conn.execute('SELECT * FROM deliverables WHERE id=?',(did,)).fetchone())
            assert attachment['file_path']==old['file_path']
            assert attachment['processed_at']==old['processed_at']
            assert conn.execute("SELECT state FROM partner_profile_sources WHERE source_kind='attachment' AND source_id=?",(did,)).fetchone()['state']=='processing'
        # An overlapping callback sees the processing claim, so it sends nothing.
        profile_sources.process_source(pid,'attachment',did)
        return json.dumps({'sections':[{'chapter':5,'summary':material,'quotes':[material]}]})
    monkeypatch.setattr(profile_sources.development_model,'completion',complete)
    url=f'/admin/partner-materials/documents/{did}/classify'
    payload={'partner_id':pid,'title':'合成分类资料','category_id':'marketing-3'}
    response=client.put(url,headers=admin,json=payload)
    assert response.status_code==200,response.text
    assert client.put(url,headers=admin,json=payload).status_code==404
    profile_sources.process_source(pid,'attachment',did)
    assert calls==['synthetic pending capability']
    with get_db() as conn:
        source=conn.execute("SELECT state,sections_json FROM partner_profile_sources WHERE source_kind='attachment' AND source_id=?",(did,)).fetchone()
        assert source['state']=='ready' and 'synthetic pending capability' in source['sections_json']
    assert Path(old['file_path']).read_bytes()==b'synthetic pending capability'


def test_ready_classification_migrates_valid_contribution_without_callback(client,access,monkeypatch):
    import json
    from backend.app import profile_sources
    admin,_,pid=access
    did=add_document(client,admin,pid,body=b'validated original capability')
    sections=[{'chapter':5,'quotes':['validated original capability']}]
    with get_db() as conn:
        source=next(s for s in profile_sources.sources(conn,pid) if s['id']==did)
        profile_sources.put(conn,source,'ready',sections,'synthetic validated partial-source note')
    callbacks=[]
    monkeypatch.setattr(partner_materials,'_process_profile',lambda p:callbacks.append(p))
    response=client.put(f'/admin/partner-materials/documents/{did}/classify',headers=admin,
                        json={'partner_id':pid,'title':'合成已完成资料','category_id':'marketing-3'})
    assert response.status_code==200 and callbacks==[]
    with get_db() as conn:
        migrated=conn.execute("SELECT state,sections_json,error FROM partner_profile_sources WHERE source_kind='attachment' AND source_id=?",(did,)).fetchone()
        assert migrated['state']=='ready' and json.loads(migrated['sections_json'])==sections
        assert migrated['error']=='synthetic validated partial-source note'


def test_processing_contribution_cannot_be_moved_and_submitted_twice(client,access,monkeypatch):
    from backend.app import profile_sources
    admin,_,pid=access
    did=add_document(client,admin,pid)
    with get_db() as conn:
        source=next(s for s in profile_sources.sources(conn,pid) if s['id']==did)
        profile_sources.put(conn,source,'processing')
    callbacks=[]
    monkeypatch.setattr(partner_materials,'_process_profile',lambda p:callbacks.append(p))
    response=client.put(f'/admin/partner-materials/documents/{did}/classify',headers=admin,
                        json={'partner_id':pid,'title':'合成在途资料','category_id':'marketing-3'})
    assert response.status_code==409 and callbacks==[]
    with get_db() as conn:
        assert conn.execute('SELECT id FROM partner_documents WHERE id=?',(did,)).fetchone()
        assert not conn.execute('SELECT id FROM deliverables WHERE id=?',(did,)).fetchone()
