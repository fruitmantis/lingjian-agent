"""Shared private storage and cached native-text processing for partner/case files."""
import html
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from .database import get_db, UPLOADS_DIR
from .doc_extractor import extract_text, decode_text, clean_html, markdown_html
from .file_storage import save_upload_limited, validate_material
from .material_contract import file_type, CONTRACT

TABLES = {'document':('partner_documents','partner_id'), 'attachment':('deliverables','case_id')}
PROCESS_LOCK = threading.Lock()
logger=logging.getLogger(__name__)

def now(): return datetime.now(timezone.utc).isoformat()

def changed(conn, partner_id):
    conn.execute('UPDATE partners SET materials_revision=materials_revision+1 WHERE id=?',(partner_id,))
    from .profile_sources import sync
    sync(conn,partner_id)

def public_file(row, admin=True):
    result={k:row[k] for k in ('id','filename','file_type','processing_status','processed_at','created_at')}
    if admin:
        result.update({k:row[k] for k in ('processing_error','preview_error')})
    for k in ('partner_id','case_id','doc_category'):
        if k in dict(row): result[k]=row[k]
    return result

def get_file(conn, scope, parent_id, file_id):
    table,parent=TABLES[scope]
    row=conn.execute(f'SELECT * FROM {table} WHERE id=? AND {parent}=?',(file_id,parent_id)).fetchone()
    if not row: raise HTTPException(404,'文件不存在')
    return dict(row)

async def save(scope, parent_id, partner_id, upload, tasks, *, import_profile=False):
    name=Path((upload.filename or '').replace('\\','/')).name
    kind=file_type(name)
    if not kind: raise HTTPException(400,CONTRACT['unsupported_message'])
    if import_profile and kind!='docx': raise HTTPException(400,'初始化画像请上传 DOCX 文件')
    fid=str(uuid.uuid4()); path=UPLOADS_DIR/(fid+'.'+Path(name).suffix.lstrip('.').lower())
    table,parent=TABLES[scope]
    try:
        await save_upload_limited(upload,path)
        validate_material(path,kind)
        with get_db() as conn:
            conn.lock_writer()
            if scope=='attachment':
                parent_row=conn.execute('SELECT partner_id FROM cases WHERE id=?',(parent_id,)).fetchone()
                if not parent_row: raise HTTPException(404,'案例不存在')
                partner_id=parent_row['partner_id']
                conn.execute('UPDATE cases SET updated_at=? WHERE id=?',(now(),parent_id))
            conn.execute(f'INSERT INTO {table} (id,{parent},filename,file_path,file_type,created_at) VALUES (?,?,?,?,?,?)', (fid,parent_id,name,str(path),kind,now()))
            if import_profile: conn.execute('UPDATE partner_documents SET doc_category=? WHERE id=?',('profile_import',fid))
            changed(conn,partner_id)
            row=get_file(conn,scope,parent_id,fid)
    except Exception:
        path.unlink(missing_ok=True); raise
    tasks.add_task(process,scope,fid,import_profile)
    return public_file(row)

async def replace(scope, parent_id, file_id, upload, tasks):
    """Replace only after format validation; keep the existing attachment ID."""
    name=Path((upload.filename or '').replace('\\','/')).name
    kind=file_type(name)
    if not kind: raise HTTPException(400,CONTRACT['unsupported_message'])
    path=UPLOADS_DIR/(str(uuid.uuid4())+Path(name).suffix.lower())
    table,_=TABLES[scope]
    try:
        await save_upload_limited(upload,path)
        validate_material(path,kind)
        with get_db() as conn:
            conn.lock_writer()
            old=get_file(conn,scope,parent_id,file_id)
            if old.get('doc_category')=='profile_import':
                raise HTTPException(409,'请在伙伴画像区域重新导入画像')
            updated=conn.execute(f"UPDATE {table} SET filename=?,file_path=?,file_type=?,extracted_text=NULL,processing_status='processing',processing_error=NULL,preview_path=NULL,preview_error=NULL,processed_at=NULL WHERE id=? AND processing_status!='processing' RETURNING id",
                                 (name,str(path),kind,file_id)).fetchone()
            if not updated: raise HTTPException(409,'文件正在处理中，请稍后替换')
            partner_id=parent_id
            if scope=='attachment':
                partner_id=conn.execute('SELECT partner_id FROM cases WHERE id=?',(parent_id,)).fetchone()[0]
                conn.execute('UPDATE cases SET updated_at=? WHERE id=?',(now(),parent_id))
            changed(conn,partner_id)
            row=get_file(conn,scope,parent_id,file_id)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    for key in ('file_path','preview_path'):
        if old.get(key): Path(old[key]).unlink(missing_ok=True)
    tasks.add_task(process,scope,file_id)
    return public_file(row)

def office_preview(path):
    executable=os.getenv('LIBREOFFICE_BIN') or shutil.which('libreoffice')
    if not executable: raise RuntimeError('未安装 LibreOffice，无法生成 PDF 预览')
    target=UPLOADS_DIR/'previews';target.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='banfei-office-') as temp:
        folder=Path(temp); profile=folder/'profile'
        # Each conversion has an isolated user profile; macros and link updates are disabled.
        user=profile/'user';user.mkdir(parents=True)
        (user/'registrymodifications.xcu').write_text('''<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry"><item oor:path="/org.openoffice.Office.Common/Security/Scripting"><prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop></item><item oor:path="/org.openoffice.Office.Common/Load"><prop oor:name="UpdateLinkMode" oor:op="fuse"><value>0</value></prop></item></oor:items>''')
        command=[executable,'-env:UserInstallation='+profile.as_uri(),'--headless','--nologo','--nodefault','--norestore','--convert-to','pdf','--outdir',str(folder),str(path.resolve())]
        result=subprocess.run(command,capture_output=True,timeout=120,check=False)
        pdf=folder/(path.stem+'.pdf')
        if result.returncode or not pdf.is_file():
            detail=(result.stderr or result.stdout).decode('utf-8',errors='replace')[-1500:]
            raise RuntimeError('LibreOffice PDF 转换失败，退出码 '+str(result.returncode)+'：'+detail)
        final=target/(path.stem+'.pdf');os.replace(pdf,final)
        return str(final)

def text_preview(path,kind):
    raw=decode_text(path.read_bytes())
    body=raw if kind=='txt' else (markdown_html(raw) if kind=='markdown' else clean_html(raw))
    if kind!='txt':
        body='<!doctype html><meta charset="utf-8"><style>body{font:16px/1.8 sans-serif;max-width:900px;margin:24px auto;padding:0 20px;overflow-wrap:anywhere}pre{white-space:pre-wrap}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px}</style>'+body
    folder=UPLOADS_DIR/'previews';folder.mkdir(parents=True,exist_ok=True)
    target=folder/(path.stem+('.txt' if kind=='txt' else '.html'))
    temp=target.with_suffix(target.suffix+'.tmp');temp.write_text(body,encoding='utf-8');os.replace(temp,target)
    return str(target)


def process(scope,file_id,import_profile=False):
    table,parent=TABLES[scope]
    with PROCESS_LOCK:
        with get_db() as conn:
            row=conn.execute(f'SELECT * FROM {table} WHERE id=?',(file_id,)).fetchone()
            if not row: return
            row=dict(row)
            partner_id=row[parent] if scope=='document' else conn.execute('SELECT partner_id FROM cases WHERE id=?',(row[parent],)).fetchone()[0]
        text=None; error=None; preview_error=None; preview=row['preview_path']
        try: text=extract_text(row['file_path'],row['file_type'])
        except Exception as exc:
            from .error_diagnostics import record_error
            from .error_diagnostics import redact
            error=redact(f'{type(exc).__name__}: {exc}')
            record_error(exc,stage='document_extract', request_id=file_id)
        if row['file_type'] in ('docx','pptx','txt','markdown','html'):
            try: preview=office_preview(Path(row['file_path'])) if row['file_type'] in ('docx','pptx') else text_preview(Path(row['file_path']),row['file_type'])
            except Exception as exc:
                from .error_diagnostics import redact,record_error
                preview_error=redact(f'{type(exc).__name__}: {exc}')
                record_error(exc,stage='document_preview',request_id=file_id)
        state='failed' if error else ('ready' if text and text.strip() else 'empty')
        if import_profile and state=='ready':
            try:
                from .profile_report import from_docx
                from_docx(row['file_path'])
            except Exception as exc:
                from .error_diagnostics import redact,record_error
                error=redact(f'{type(exc).__name__}: {exc}')
                state='failed'
                record_error(exc,stage='profile_structure',request_id=file_id)
        try:
            with get_db() as conn:
                conn.lock_writer()
                exists=conn.execute(f'SELECT file_path FROM {table} WHERE id=?',(file_id,)).fetchone()
                if not exists or exists['file_path']!=row['file_path']:
                    if preview: Path(preview).unlink(missing_ok=True)
                    return
                conn.execute(f'UPDATE {table} SET extracted_text=?,processing_status=?,processing_error=?,preview_path=?,preview_error=?,processed_at=? WHERE id=?',(text,state,error,preview,preview_error,now(),file_id))
                from .profile_sources import sync
                sync(conn,partner_id)
        except Exception as exc:
            from .error_diagnostics import record_error
            record_error(exc,stage='document_result_persistence',request_id=file_id)
        from .profile_sources import process_partner
    try: process_partner(partner_id)
    except Exception:
        # Contribution errors persist separately; native text/preview remain usable.
        logger.warning('Source contribution failed for material %s',file_id)

def retry(scope,parent_id,file_id,tasks):
    table,_=TABLES[scope]
    with get_db() as conn:
        conn.lock_writer();row=get_file(conn,scope,parent_id,file_id)
        if row['processing_status']=='processing': raise HTTPException(409,'文件正在处理中')
        partner_id=parent_id if scope=='document' else conn.execute('SELECT partner_id FROM cases WHERE id=?',(parent_id,)).fetchone()[0]
        changed(conn,partner_id)
        if not file_type(row['filename']): raise HTTPException(400,CONTRACT['unsupported_message'])
        conn.execute(f"UPDATE {table} SET processing_status='processing',processing_error=NULL,preview_error=NULL WHERE id=?",(file_id,))
    retry_import=scope=='document' and row.get('doc_category')=='profile_import' and row['processing_status'] in ('failed','empty')
    if retry_import:
        with get_db() as conn:
            current=conn.execute('SELECT profile_updated_at FROM partners WHERE id=?',(partner_id,)).fetchone()[0]
        # A retry of an old failed import must not overwrite a newer manual profile.
        retry_import=not current or current<row['created_at']
    tasks.add_task(process,scope,file_id,retry_import)
    return {'processing_status':'processing'}

def respond(row,preview=False):
    path=Path(row['file_path'])
    if not path.is_file(): raise HTTPException(404,'原文件不存在')
    headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
    if not preview: return FileResponse(path,filename=row['filename'],media_type='application/octet-stream',headers=headers)
    kind=row['file_type']
    if kind in ('pdf','docx','pptx'):
        if kind!='pdf':
            if not row['preview_path']: raise HTTPException(409,'PDF 预览尚未生成，请稍后查看或重试')
            path=Path(row['preview_path'])
        if not path.is_file(): raise HTTPException(404,'预览文件不存在，请重试')
        return FileResponse(path,media_type='application/pdf',headers=headers)
    if kind in ('txt','markdown','html'):
        if not row['preview_path'] or not Path(row['preview_path']).is_file():
            raise HTTPException(409,'预览尚未生成，请稍后查看或重试')
        content=Path(row['preview_path']).read_text(encoding='utf-8')
        if kind=='txt': return PlainTextResponse(content,headers=headers)
        headers['Content-Security-Policy']="sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; base-uri 'none'; form-action 'none'"
        return HTMLResponse(content,headers=headers)
    raise HTTPException(400,CONTRACT['unsupported_message'])

def remove(scope,parent_id,file_id,partner_id):
    table,parent=TABLES[scope]
    with get_db() as conn:
        conn.lock_writer();row=get_file(conn,scope,parent_id,file_id)
        if scope=='attachment':
            partner_id=conn.execute('SELECT partner_id FROM cases WHERE id=?',(parent_id,)).fetchone()[0]
            conn.execute('UPDATE cases SET updated_at=? WHERE id=?',(now(),parent_id))
        conn.execute(f'DELETE FROM {table} WHERE id=? AND {parent}=?',(file_id,parent_id));changed(conn,partner_id)
    for key in ('file_path','preview_path'):
        if row.get(key): Path(row[key]).unlink(missing_ok=True)

def recover_processing():
    with get_db() as conn:
        conn.execute("UPDATE partner_profile_sources SET state='failed',error='处理被中断，请重试。' WHERE state='processing'")
        for table,_ in TABLES.values():
            conn.execute(f"UPDATE {table} SET processing_status='failed',processing_error='处理被中断，请点击重试。' WHERE processing_status='processing'")
