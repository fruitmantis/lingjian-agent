"""Failure visibility and one-file recovery; all model work is explicitly stubbed."""
import json,os
from contextlib import contextmanager
from pathlib import Path
import pytest
from backend.app import material_files as files,profile_sources as sources,profile_report
from backend.app.database import get_db
from .test_partner_materials import access,upload
from .support.profile_report_fixture import document

def original(pid):
 report=profile_report.empty_report();report.chapters[0]=profile_report.heading(1)+'\n\n已有有效公司正文。\n\n'
 with get_db() as conn:conn.execute('UPDATE partners SET ai_profile=? WHERE id=?',(report.text,pid))
 return report.text

def listed(client,access):
 response=client.get(f'/partners/{access[2]}/documents',headers=access[0]);assert response.status_code==200,response.text
 return {row['id']:row for row in response.json()}

def source_row(pid,fid):
 with get_db() as conn:return dict(conn.execute('SELECT * FROM partner_profile_sources WHERE partner_id=? AND source_id=?',(pid,fid)).fetchone())

def body(pid):
 with get_db() as conn:return conn.execute('SELECT ai_profile FROM partners WHERE id=?',(pid,)).fetchone()[0]

def diagnostics(fid):
 return [row for row in (json.loads(line) for line in Path(os.environ['BANFEI_ERROR_LOG_PATH']).read_text().splitlines()) if row.get('request_id')==fid]

def test_native_failure_has_reason_retry_and_retains_old_profile(client,access,monkeypatch):
 before=original(access[2])
 def fail(*_):raise RuntimeError('native extraction unavailable token=INTERNAL_SECRET_TEST')
 monkeypatch.setattr(files,'extract_text',fail)
 native=upload(client,access,'native.txt',b'original retained')
 file=listed(client,access)[native['id']]
 assert file['processing_status']=='failed' and 'unavailable' in file['processing_error']
 assert 'INTERNAL_SECRET_TEST' not in file['processing_error'] and Path(native['file_path']).exists()
 assert body(access[2])==before
 assert any(row['stage']=='document_extract' for row in diagnostics(native['id']))

@pytest.mark.parametrize('empty_reason',[False,True])
def test_contribution_failure_visible_despite_native_ready(client,access,monkeypatch,empty_reason):
 before=original(access[2])
 def fail(*_):raise RuntimeError('' if empty_reason else 'provider unavailable token=INTERNAL_SECRET_TEST')
 monkeypatch.setattr(sources.development_model,'completion',fail)
 native=upload(client,access,'contribution.txt',b'original extracted text')
 file=listed(client,access)[native['id']]
 assert native['processing_status']=='ready' and native['extracted_text']=='original extracted text'
 assert file['source_state']=='failed' and file['source_error']
 assert 'INTERNAL_SECRET_TEST' not in file['source_error'] and body(access[2])==before
 assert source_row(access[2],native['id'])['state']=='failed'

def test_native_ready_before_claim_keeps_pollable_current_pending_state(client,access,monkeypatch):
 captured=[];run=files.process_contribution
 monkeypatch.setattr(files,'process_contribution',lambda *args,**kwargs:captured.append((args,kwargs)))
 native=upload(client,access,'queued.txt',b'queued native text')
 assert listed(client,access)[native['id']]['source_state']=='pending'
 assert len(captured)==1
 args,kwargs=captured[0];run(*args,**kwargs)
 assert listed(client,access)[native['id']]['source_state']=='ready' and len(captured)==1

@pytest.mark.parametrize('word',[False,True])
def test_native_result_save_exception_reaches_failed_terminal_and_diagnostic(client,access,monkeypatch,word):
 before=original(access[2]);real=files.get_db;faults=[]
 class Proxy:
  def __init__(self,conn):self.conn=conn
  def __getattr__(self,key):return getattr(self.conn,key)
  def execute(self,sql,*args,**kwargs):
   if sql.startswith('UPDATE partner_documents SET extracted_text=') and not faults:
    faults.append(sql);raise RuntimeError('native save transaction fault')
   return self.conn.execute(sql,*args,**kwargs)
 @contextmanager
 def fault_db():
  with real() as conn:yield Proxy(conn)
 monkeypatch.setattr(files,'get_db',fault_db)
 monkeypatch.setattr(files,'office_preview',lambda *_:None)
 native=upload(client,access,'save.docx' if word else 'save.txt',document() if word else b'cached text',word)
 file=listed(client,access)[native['id']]
 assert len(faults)==1 and file['processing_status']=='failed'
 assert file['processing_error']=='处理结果保存失败，请重试。' and body(access[2])==before
 partner=client.get(f'/partners/{access[2]}',headers=access[0]).json()
 shown=next(row for row in partner['profile_sources'] if row['source_id']==native['id'])
 assert shown['state']=='failed' and shown['error']=='处理结果保存失败，请重试。'
 assert any(row['stage']=='document_result_persistence' for row in diagnostics(native['id']))

@pytest.mark.parametrize('stage',['claim','result'])
def test_contribution_save_exception_does_not_leave_pending_or_processing(client,access,monkeypatch,stage):
 before=original(access[2]);put=sources.put;faults=[]
 def fail(conn,source,state,*args,**kwargs):
  if state==('processing' if stage=='claim' else 'ready') and not faults:
   faults.append(state);raise RuntimeError('contribution transaction fault')
  return put(conn,source,state,*args,**kwargs)
 monkeypatch.setattr(sources,'put',fail)
 native=upload(client,access,'save-contribution.txt',b'cached native text')
 file=listed(client,access)[native['id']]
 assert len(faults)==1 and native['processing_status']=='ready'
 assert file['source_state']=='failed' and '结果保存失败' in file['source_error']
 assert body(access[2])==before
 assert any(row['stage']=='profile_contribution_background' for row in diagnostics(native['id']))

def test_retry_B_marks_only_B_pending_and_reuses_native_cache(client,access,monkeypatch):
 before=original(access[2])
 def fail(*_):raise RuntimeError('contribution failed')
 monkeypatch.setattr(sources.development_model,'completion',fail)
 a=upload(client,access,'A.txt',b'original A');b=upload(client,access,'B.txt',b'original B')
 a_before=source_row(access[2],a['id']);run=files.process_contribution;queued=[];model_calls=[]
 monkeypatch.setattr(files,'process_contribution',lambda *args,**kwargs:queued.append((args,kwargs)))
 def no_extract(*_):raise AssertionError('Contribution retry must reuse native cache')
 monkeypatch.setattr(files,'extract_text',no_extract)
 monkeypatch.setattr(sources.development_model,'completion',lambda *args:(model_calls.append(args) or '{"sections":[]}'))
 response=client.post(f'/partners/{access[2]}/documents/{b["id"]}/retry',headers=access[0])
 assert response.status_code==200,response.text
 assert len(queued)==1 and queued[0][0][2]==b['id'] and model_calls==[]
 assert listed(client,access)[b['id']]['source_state']=='pending'
 assert source_row(access[2],a['id'])==a_before
 args,kwargs=queued[0];run(*args,**kwargs)
 assert len(model_calls)==1 and listed(client,access)[b['id']]['source_state']=='ready'
 assert source_row(access[2],a['id'])==a_before and body(access[2])==before

def test_saved_failure_fallback_cannot_overwrite_a_newly_queued_retry(client,access,monkeypatch):
 run=sources.process_source;queued=[]
 def fail(*_):raise RuntimeError('first attempt failed')
 monkeypatch.setattr(sources.development_model,'completion',fail)
 def new_retry_after_saved_failure(pid,kind,fid,fingerprint,**kwargs):
  try:run(pid,kind,fid,fingerprint,**kwargs)
  except ValueError:
   # A user retry can queue after the failed transaction commits and before
   # its background callback unwinds. This is a new attempt of the same version.
   with get_db() as conn:
    conn.execute("UPDATE partner_profile_sources SET state='pending',error=NULL WHERE partner_id=? AND source_id=?",(pid,fid))
   queued.append(fid)
   raise
 monkeypatch.setattr(sources,'process_source',new_retry_after_saved_failure)
 native=upload(client,access,'new-retry.txt',b'original text')
 assert queued==[native['id']] and source_row(access[2],native['id'])['state']=='pending'

def test_stale_source_error_and_late_failure_cannot_replace_current_version(client,access,monkeypatch):
 def fail(*_,**kwargs):raise RuntimeError('old version failure')
 monkeypatch.setattr(sources.development_model,'completion',fail)
 native=upload(client,access,'stale.txt',b'original');cached=source_row(access[2],native['id'])
 with get_db() as conn:conn.execute('UPDATE partner_documents SET extracted_text=? WHERE id=?',('new current text',native['id']))
 file=listed(client,access)[native['id']]
 assert file['source_state']=='pending' and file['source_error'] is None
 partner=client.get(f'/partners/{access[2]}',headers=access[0]).json()
 shown=next(row for row in partner['profile_sources'] if row['source_id']==native['id'])
 assert shown['state']=='pending' and shown['error'] is None
 monkeypatch.setattr(sources,'process_source',fail)
 files.process_contribution(access[2],'document',native['id'],cached['source_fingerprint'])
 assert source_row(access[2],native['id'])==cached

def test_file_projection_does_not_mix_errors_from_another_file_version(client,access):
 native=upload(client,access,'version.txt',b'first version')
 with get_db() as conn:
  conn.execute('UPDATE partner_documents SET extracted_text=? WHERE id=?',('second version',native['id']))
  current=sources.source(conn,access[2],'document',native['id'])
  sources.put(conn,current,'failed',error='second version failure')
  previous_projection=files.public_file(native,conn=conn)
  assert previous_projection['source_state']=='pending' and previous_projection['source_error'] is None
 assert listed(client,access)[native['id']]['source_error']=='second version failure'

def test_ordinary_attachment_response_does_not_expose_source_error(client,access,monkeypatch):
 case=client.post('/cases',headers=access[0],json={'partner_id':access[2],'title':'公开资料','category_id':'delivery-1','visible':True}).json()
 def fail(*_):raise RuntimeError('internal source failure')
 monkeypatch.setattr(sources.development_model,'completion',fail)
 response=client.post(f'/cases/{case["id"]}/deliverables',headers=access[0],files={'file':('private.txt',b'original')})
 assert response.status_code==201,response.text
 admin=client.get(f'/cases/{case["id"]}/deliverables',headers=access[0]).json()[0]
 ordinary=client.get(f'/cases/{case["id"]}/deliverables',headers=access[1]).json()[0]
 assert admin['source_state']=='failed' and admin['source_error']
 assert ordinary['source_state'] is None and ordinary['source_error'] is None and ordinary['processing_error'] is None
