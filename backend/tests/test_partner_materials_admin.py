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


@pytest.mark.parametrize('blocked',['profile_import','processing','rollback'])
def test_classification_guards_and_transaction(client,access,monkeypatch,blocked):
    admin,_,pid=access;did=add_document(client,admin,pid)
    with get_db() as conn:
        if blocked=='profile_import':conn.execute("UPDATE partner_documents SET doc_category='profile_import' WHERE id=?",(did,))
        elif blocked=='processing':conn.execute("UPDATE partner_documents SET processing_status='processing' WHERE id=?",(did,))
    if blocked=='rollback':monkeypatch.setattr(partner_materials,'record_audit',lambda *_a,**_k:(_ for _ in ()).throw(RuntimeError('synthetic audit failure')))
    call=lambda:client.put(f'/admin/partner-materials/documents/{did}/classify',headers=admin,json={'partner_id':pid,'title':'资料','category_id':'delivery-1'})
    assert call().status_code==(500 if blocked=='rollback' else 409)
    with get_db() as conn:
        row=conn.execute('SELECT file_path FROM partner_documents WHERE id=?',(did,)).fetchone()
        assert row and Path(row['file_path']).exists()
        assert not conn.execute('SELECT id FROM cases WHERE id=?',(did,)).fetchone()
        assert not conn.execute('SELECT id FROM deliverables WHERE id=?',(did,)).fetchone()


@pytest.mark.parametrize('kind',['case','document'])
def test_file_replacement_keeps_id_validates_first_and_withdraws_legacy_profile(client,access,kind):
    admin,user,pid=access
    if kind=='case':
        cid=add_case(client,admin,pid);endpoint=f'/cases/{cid}/deliverables'
        did=client.post(endpoint,headers=admin,files={'file':('old.txt',b'old text')}).json()['id']
    else:
        did=add_document(client,admin,pid,body=b'old text');endpoint=f'/partners/{pid}/documents'
    with get_db() as conn: conn.execute('UPDATE partners SET ai_profile=? WHERE id=?',('existing profile',pid))
    url=endpoint+'/'+did
    assert client.put(url,headers=user,files={'file':('new.txt',b'new text')}).status_code==403
    assert client.put(url,headers=admin,files={'file':('fake.pdf',b'invalid PDF')}).status_code==400
    assert client.get(url+'/file',headers=admin).content==b'old text'
    response=client.put(url,headers=admin,files={'file':('new.txt',b'new text')})
    assert response.status_code==200 and response.json()['id']==did
    assert client.get(url+'/file',headers=admin).content==b'new text'
    assert client.get(url+'/preview',headers=admin).text=='new text'
    assert len(client.get(endpoint,headers=admin).json())==1
    with get_db() as conn: assert conn.execute('SELECT ai_profile FROM partners WHERE id=?',(pid,)).fetchone()[0]!='existing profile'
