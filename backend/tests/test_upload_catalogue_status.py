"""UF-QA-01: page-only, read-only aggregation of current file contributions."""
import pytest
from backend.app import profile_sources as sources,material_files as files
from backend.app.database import get_db
from .test_partner_materials_admin import access,add_case,add_document

def seed(client,access,kind):
 admin,_,pid=access
 if kind=='document':
  fid=add_document(client,admin,pid);return fid,fid,'document'
 cid=add_case(client,admin,pid)
 response=client.post(f'/cases/{cid}/deliverables',headers=admin,files={'file':('file.txt',b'complete native text')})
 assert response.status_code==201,response.text
 return cid,response.json()['id'],'attachment'

def state(pid,kind,fid,value):
 with get_db() as conn:
  native=sources.source(conn,pid,kind,fid)
  sources.put(conn,native,value,error='current contribution failure' if value=='failed' else None)

def snapshot(pid):
 with get_db() as conn:
  return {
   'partner':dict(conn.execute('SELECT * FROM partners WHERE id=?',(pid,)).fetchone()),
   'documents':[dict(row) for row in conn.execute('SELECT * FROM partner_documents WHERE partner_id=? ORDER BY id',(pid,))],
   'attachments':[dict(row) for row in conn.execute('SELECT d.* FROM deliverables d JOIN cases c ON c.id=d.case_id WHERE c.partner_id=? ORDER BY d.id',(pid,))],
   'sources':[dict(row) for row in conn.execute('SELECT * FROM partner_profile_sources WHERE partner_id=? ORDER BY source_kind,source_id',(pid,))]}

def entry(client,access,eid,**params):
 response=client.get('/admin/partner-materials',headers=access[0],params={'partner_id':access[2],**params})
 assert response.status_code==200,response.text
 return next(row for row in response.json()['items'] if row['id']==eid)

@pytest.mark.parametrize('kind',['case','document'])
@pytest.mark.parametrize('contribution,expected',[('pending','processing'),('processing','processing'),('failed','failed'),('ready','ready')])
def test_catalogue_uses_current_contribution_and_does_not_process_files(client,access,monkeypatch,kind,contribution,expected):
 eid,fid,source_kind=seed(client,access,kind);state(access[2],source_kind,fid,contribution)
 before=snapshot(access[2])
 def forbidden(*args,**kwargs):raise AssertionError('Catalogue must be read-only and never dispatch work')
 monkeypatch.setattr(files,'process',forbidden);monkeypatch.setattr(files,'process_contribution',forbidden)
 monkeypatch.setattr(sources.development_model,'completion',forbidden)
 result=entry(client,access,eid)
 assert result['processing_status']==expected
 assert not {'source_error','source_fingerprint','extracted_text','file_path'}&result.keys()
 assert snapshot(access[2])==before

@pytest.mark.parametrize('kind',['case','document'])
def test_catalogue_keeps_delayed_unclaimed_file_processing(client,access,kind):
 eid,fid,source_kind=seed(client,access,kind)
 with get_db() as conn:conn.execute('DELETE FROM partner_profile_sources WHERE partner_id=? AND source_kind=? AND source_id=?',(access[2],source_kind,fid))
 before=snapshot(access[2])
 assert entry(client,access,eid)['processing_status']=='processing'
 assert snapshot(access[2])==before

@pytest.mark.parametrize('kind',['case','document'])
def test_catalogue_ignores_old_version_failure_until_current_result(client,access,kind):
 eid,fid,source_kind=seed(client,access,kind);state(access[2],source_kind,fid,'failed')
 table='partner_documents' if kind=='document' else 'deliverables'
 with get_db() as conn:conn.execute(f'UPDATE {table} SET extracted_text=? WHERE id=?',('new current version',fid))
 before=snapshot(access[2])
 assert entry(client,access,eid)['processing_status']=='processing'
 assert snapshot(access[2])==before
 state(access[2],source_kind,fid,'ready');before=snapshot(access[2])
 assert entry(client,access,eid)['processing_status']=='ready' and snapshot(access[2])==before

def test_case_waits_for_B_then_retains_failed_A_without_touching_either(client,access):
 cid,a,kind=seed(client,access,'case')
 response=client.post(f'/cases/{cid}/deliverables',headers=access[0],files={'file':('B.txt',b'original B')});assert response.status_code==201
 b=response.json()['id'];state(access[2],kind,a,'failed');state(access[2],kind,b,'pending')
 before=snapshot(access[2]);assert entry(client,access,cid)['processing_status']=='processing';assert snapshot(access[2])==before
 state(access[2],kind,b,'ready');before=snapshot(access[2])
 assert entry(client,access,cid)['processing_status']=='failed' and snapshot(access[2])==before

def test_additional_source_projection_is_limited_to_returned_page(client,access,monkeypatch):
 eid,fid,_=seed(client,access,'case');other=add_document(client,access[0],access[2]);seen=[];project=files.public_file
 def spy(row,*args,**kwargs):
  seen.append(row['id']);return project(row,*args,**kwargs)
 monkeypatch.setattr(files,'public_file',spy)
 before=snapshot(access[2]);result=entry(client,access,eid,page_size=1)
 assert result['id']==eid and seen==[fid] and other not in seen
 assert snapshot(access[2])==before
