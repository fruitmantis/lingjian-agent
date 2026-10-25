"""The global and partner shortcuts read one catalogue, without new storage."""
from pathlib import Path
import pytest
from backend.app.database import get_db
from backend.app.routers import partner_materials
from .conftest import auth_headers,make_partner,make_user

@pytest.fixture
def access(client,monkeypatch):
    from backend.app import profile_sources
    monkeypatch.setattr(profile_sources,'resolve_model_record',lambda _: {'api_key':'synthetic-only','base_url':'http://127.0.0.1:1/v1','model_name':'synthetic','max_tokens':4096,'temperature':0.3,'top_p':1.0})
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
        if 'blocks' not in data:return json.dumps(merge_result(data))
        return json.dumps({'sections':[{'chapter':5,'summary':''.join(block['text'] for block in data['blocks']),'block_ids':[block['id'] for block in data['blocks']]}]})
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
        blocks=json.loads(messages[-1]['content'])['blocks']
        material=''.join(block['text'] for block in blocks)
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
        return json.dumps({'sections':[{'chapter':5,'summary':material,'block_ids':[block['id'] for block in blocks]}]})
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


def _catalogue_native(conn, pid, cid, fid, *, native='ready', source='ready', preview=None, stale=False, document=False, text='合成资料正文'):
    """Synthetic native rows and contributions; no parser, files or model calls."""
    from backend.app.profile_sources import source as current_source, put
    if document:
        conn.execute("INSERT INTO partner_documents (id,partner_id,filename,file_path,file_type,created_at,extracted_text,processing_status,preview_error) VALUES (?,?,?,?,?,?,?,?,?)",
                     (fid,pid,fid+'.txt','/tmp/'+fid+'.txt','txt','2026-10-24T00:00:00+00:00',text,native,preview))
        kind='document'
    else:
        conn.execute("INSERT INTO deliverables (id,case_id,filename,file_path,file_type,created_at,extracted_text,processing_status,preview_error) VALUES (?,?,?,?,?,?,?,?,?)",
                     (fid,cid,fid+'.txt','/tmp/'+fid+'.txt','txt','2026-10-24T00:00:00+00:00',text,native,preview))
        kind='attachment'
    if source is not None:
        put(conn,current_source(conn,pid,kind,fid),source)
        if stale:
            conn.execute("UPDATE partner_profile_sources SET source_fingerprint='outdated' WHERE partner_id=? AND source_kind=? AND source_id=?",(pid,kind,fid))


def test_catalogue_failed_filter_uses_current_file_states_and_processing_priority(client,access):
    from backend.app import material_files, profile_sources
    admin,user,pid=access
    definitions={
        'parse': [('failed','ready',None,False)],
        'preview': [('ready','ready','synthetic preview error',False)],
        'source': [('ready','failed',None,False)],
        'mixed-parse': [('failed','ready',None,False),('processing',None,None,False)],
        'mixed-source': [('ready','failed',None,False),('ready','pending',None,False)],
        'preview-pending': [('ready','pending','synthetic preview error',False)],
        'source-processing': [('ready','processing',None,False)],
        'missing-source': [('ready',None,None,False)],
        'stale-failure': [('ready','failed',None,True)],
        'empty': [('empty','failed',None,False)],
        'source-empty': [('ready','empty',None,False)],
        'ready': [('ready','ready',None,False)],
        'no-files': [],
    }
    ids={name:add_case(client,admin,pid,name) for name in definitions}
    with get_db() as conn:
        for name,files in definitions.items():
            for i,(native,source,preview,stale) in enumerate(files):
                _catalogue_native(conn,pid,ids[name],f'{name}-{i}',native=native,source=source,preview=preview,stale=stale)
        # A case-description failure and stale partner profile are not file failure.
        profile_sources.put(conn,{'kind':'case','id':ids['no-files'],'partner_id':pid,'text':'','processing_status':'ready'},'failed')
        conn.execute("UPDATE partners SET materials_revision=materials_revision+1 WHERE id=?",(pid,))
        for name,native,source,preview,stale in [
            ('doc-parse','failed','ready',None,False),
            ('doc-preview','ready','ready','preview failed',False),
            ('doc-source','ready','failed',None,False),
            ('doc-stale','ready','failed',None,True),
            ('doc-empty','empty',None,None,False),
            ('doc-processing','processing',None,None,False),
        ]:
            _catalogue_native(conn,pid,None,name,native=native,source=source,preview=preview,stale=stale,document=True)
        _catalogue_native(conn,pid,None,'private-profile',native='failed',document=True)
        conn.execute("UPDATE partner_documents SET doc_category='profile_import' WHERE id='private-profile'")
    response=client.get('/admin/partner-materials',headers=admin,params={'partner_id':pid,'page_size':50})
    assert response.status_code==200,response.text
    entries={r['title']:r for r in response.json()['items']}
    expected={'parse':'failed','preview':'failed','source':'failed','mixed-parse':'processing','mixed-source':'processing','preview-pending':'processing','source-processing':'processing','missing-source':'processing','stale-failure':'processing','empty':'empty','source-empty':'empty','ready':'ready','no-files':'no_files'}
    for title,state in expected.items():assert entries[title]['processing_status']==state
    assert response.json()['total']==19
    assert all(r['profile_needs_update'] for r in entries.values())
    failed=client.get('/admin/partner-materials',headers=admin,params={'partner_id':pid,'status':'failed','page_size':50}).json()
    assert failed['total']==6
    assert {r['title'] for r in failed['items']}=={'parse','preview','source','doc-parse.txt','doc-preview.txt','doc-source.txt'}
    assert all(r['processing_status']=='failed' for r in failed['items'])
    assert client.get('/admin/partner-materials',headers=user,params={'status':'failed'}).status_code==403
    assert client.get('/admin/partner-materials',headers=admin,params={'status':'processing'}).status_code==422
    # Compare the unified query to the existing authorized file projection.
    with get_db() as conn:
        for name,cid in ids.items():
            states=[]
            for row in conn.execute('SELECT * FROM deliverables WHERE case_id=?',(cid,)):
                f=material_files.public_file(row,conn=conn)
                states.append('processing' if f['processing_status']=='processing' or f.get('source_state') in ('pending','processing') else 'failed' if f['processing_status']=='failed' or f.get('preview_error') or f.get('source_state')=='failed' else 'empty' if f['processing_status']=='empty' or f.get('source_state')=='empty' else f['processing_status'])
            actual=next((s for s in ('processing','failed','empty') if s in states),'ready' if states else 'no_files')
            assert entries[name]['processing_status']==actual


def test_catalogue_failure_filter_counts_cards_before_paging_and_combines_all_filters(client,access):
    admin,_,pid=access
    other=make_partner(partner_id='other-catalogue-filter',name='合成其他伙伴')['id']
    expected=set()
    with get_db() as conn:
        for i in range(95):
            cid=f'catalogue-page-{i:03}';failed=i%2==0 or i>=80
            owner=pid if i<90 else other
            category='technical-1' if i<85 else 'delivery-1'
            conn.execute("INSERT INTO cases (id,partner_id,title,category_id,visible,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                         (cid,owner,f'目标_100% {i:03}',category,0,'2026-10-24','2026-10-24'))
            _catalogue_native(conn,owner,cid,cid+'-file',source='failed' if failed else 'ready')
            if owner==pid and category=='technical-1' and failed:expected.add(cid)
        # Several failed attachments still constitute one result card.
        _catalogue_native(conn,pid,'catalogue-page-000','extra-file-1',native='failed')
        _catalogue_native(conn,pid,'catalogue-page-000','extra-file-2',source='failed')
    filters={'partner_id':pid,'category_group':'technical','category_id':'technical-1','q':'目标_100%','status':'failed'}
    assert len(expected)==45
    first=client.get('/admin/partner-materials',headers=admin,params=filters).json()
    assert first['total']==45 and len(first['items'])==10
    for size in (10,20,50):
        seen=[]
        for page in range(1,(len(expected)+size-1)//size+1):
            response=client.get('/admin/partner-materials',headers=admin,params={**filters,'page_size':size,'page':page})
            assert response.status_code==200,response.text
            result=response.json();assert result['total']==45
            assert len(result['items'])==min(size,len(expected)-(page-1)*size)
            assert all(r['processing_status']=='failed' for r in result['items'])
            seen.extend(r['id'] for r in result['items'])
        assert set(seen)==expected and len(seen)==len(set(seen))==45
    all_rows=client.get('/admin/partner-materials',headers=admin,params={k:v for k,v in filters.items() if k!='status'}).json()
    assert all_rows['total']==85
    assert client.get('/admin/partner-materials',headers=admin,params={**filters,'q':'unmatched'}).json()['total']==0
    assert client.get('/admin/partner-materials',headers=admin,params={'page_size':61}).status_code==422


def test_catalogue_source_fingerprint_matches_existing_canonical_json(client):
    from backend.app.profile_sources import stamp
    from backend.app.routers.partner_materials import _SOURCE_FINGERPRINT_SQL
    texts=['中文资料 🚀', '引号 " 与反斜杠 \\ 路径', '换行\n回车\r制表\t退格\b换页\f', 'é e\u0301 \u2028\u2029', '', None]
    with get_db() as conn:
        for kind in ('attachment','document'):
            for text in texts:
                source={'kind':kind,'id':'source-id','partner_id':'partner-id','file_path':'/tmp/资料 "一".txt','created_at':'2026-10-24T00:00:00+00:00','processing_status':'ready','text':text or ''}
                actual=conn.execute('SELECT '+_SOURCE_FINGERPRINT_SQL+' FROM (SELECT CAST(? AS TEXT) AS kind,CAST(? AS TEXT) AS id,CAST(? AS TEXT) AS partner_id,CAST(? AS TEXT) AS file_path,CAST(? AS TEXT) AS created_at,CAST(? AS TEXT) AS processing_status,CAST(? AS TEXT) AS native_text) n',
                                    tuple(source[k] for k in ('kind','id','partner_id','file_path','created_at','processing_status','text'))).fetchone()[0]
                assert actual==stamp(source)


@pytest.mark.parametrize('document',[False,True],ids=['attachments','documents'])
def test_catalogue_empty_preview_error_preserves_native_status(client,access,document):
    admin,_,pid=access
    with get_db() as conn:
        for state in ('empty','processing','failed'):
            ident='empty-preview-'+state
            if not document:
                conn.execute("INSERT INTO cases (id,partner_id,title,category_id,visible,created_at,updated_at) VALUES (?,?,?,'technical-1',0,'2026-10-25','2026-10-25')",(ident,pid,ident))
            _catalogue_native(conn,pid,None if document else ident,ident if document else ident+'-file',native=state,source=None,preview='',document=document)
    entries=client.get('/admin/partner-materials',headers=admin,params={'partner_id':pid}).json()
    assert entries['total']==3
    assert {row['processing_status'] for row in entries['items']}=={'empty','processing','failed'}
    by_id={row['id']:row['processing_status'] for row in entries['items']}
    assert by_id=={'empty-preview-empty':'empty','empty-preview-processing':'processing','empty-preview-failed':'failed'}
    failed=client.get('/admin/partner-materials',headers=admin,params={'partner_id':pid,'status':'failed'}).json()
    assert failed['total']==1
    assert [row['id'] for row in failed['items']]==['empty-preview-failed']
