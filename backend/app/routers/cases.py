"""Cases and attachments share one visibility rule; all writes require an administrator."""
import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from ..auth import require_active_user, require_admin, record_audit
from ..database import get_db
from ..models import CaseCreate,CaseOut,DeliverableOut
from ..material_contract import CONTRACT,check_category
from .. import material_files as files
from ..case_content import visible_case

router=APIRouter(prefix='/cases',tags=['cases'],dependencies=[Depends(require_active_user)])

@router.get('/categories')
def categories(): return CONTRACT['categories']

@router.get('/by-partner/{partner_id}',response_model=list[CaseOut])
def list_cases_by_partner(partner_id: str,user=Depends(require_active_user)):
    with get_db() as conn:
        p=conn.execute('SELECT status FROM partners WHERE id=?',(partner_id,)).fetchone()
        if not p or (user['role']!='admin' and p['status']!='active'): raise HTTPException(404,'伙伴不存在')
        return [dict(r) for r in conn.execute('SELECT * FROM cases WHERE partner_id=?'+('' if user['role']=='admin' else ' AND visible=1')+' ORDER BY created_at DESC',(partner_id,))]

@router.post('',response_model=CaseOut,status_code=201)
def create_case(payload: CaseCreate,actor=Depends(require_admin)):
    check_category(payload.category_id)
    cid=str(uuid.uuid4());stamp=files.now()
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if not conn.execute('SELECT id FROM partners WHERE id=?',(payload.partner_id,)).fetchone(): raise HTTPException(404,'伙伴不存在')
        conn.execute('INSERT INTO cases (id,partner_id,title,description,category_id,visible,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',(cid,payload.partner_id,payload.title,payload.description,payload.category_id,int(payload.visible),stamp,stamp))
        files.changed(conn,payload.partner_id)
        record_audit(conn,'case_created',actor_user_id=actor['id'],summary={'case_id':cid,'visible':payload.visible})
        return visible_case(conn,cid,True)

@router.get('/{case_id}',response_model=CaseOut)
def get_case(case_id: str,user=Depends(require_active_user)):
    with get_db() as conn: return visible_case(conn,case_id,user['role']=='admin')

@router.put('/{case_id}',response_model=CaseOut)
def edit_case(case_id: str,payload: CaseCreate,actor=Depends(require_admin)):
    check_category(payload.category_id)
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE');old=visible_case(conn,case_id,True)
        if not conn.execute('SELECT id FROM partners WHERE id=?',(payload.partner_id,)).fetchone(): raise HTTPException(404,'伙伴不存在')
        conn.execute('UPDATE cases SET partner_id=?,title=?,description=?,category_id=?,visible=?,updated_at=? WHERE id=?',(payload.partner_id,payload.title,payload.description,payload.category_id,int(payload.visible),files.now(),case_id))
        for pid in {old['partner_id'],payload.partner_id}: files.changed(conn,pid)
        record_audit(conn,'case_updated',actor_user_id=actor['id'],summary={'case_id':case_id,'visible':payload.visible})
        return visible_case(conn,case_id,True)

class Visibility(BaseModel): visible: bool

@router.patch('/{case_id}/visibility',response_model=CaseOut)
def visibility(case_id: str,payload: Visibility,actor=Depends(require_admin)):
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE');visible_case(conn,case_id,True)
        conn.execute('UPDATE cases SET visible=?,updated_at=? WHERE id=?',(int(payload.visible),files.now(),case_id))
        record_audit(conn,'case_visibility_changed',actor_user_id=actor['id'],summary={'case_id':case_id,'visible':payload.visible})
        return visible_case(conn,case_id,True)

@router.get('/{case_id}/deliverables',response_model=list[DeliverableOut])
def list_deliverables(case_id: str,user=Depends(require_active_user)):
    with get_db() as conn:
        visible_case(conn,case_id,user['role']=='admin')
        return [files.public_file(r,user['role']=='admin') for r in conn.execute('SELECT * FROM deliverables WHERE case_id=? ORDER BY created_at DESC',(case_id,))]

@router.post('/{case_id}/deliverables',response_model=DeliverableOut,status_code=201)
async def upload_deliverable(case_id: str,background_tasks: BackgroundTasks,file: UploadFile=File(...),actor=Depends(require_admin)):
    with get_db() as conn: case=visible_case(conn,case_id,True)
    return await files.save('attachment',case_id,case['partner_id'],file,background_tasks)

@router.post('/{case_id}/deliverables/{file_id}/retry',dependencies=[Depends(require_admin)])
def retry(case_id: str,file_id: str,background_tasks: BackgroundTasks): return files.retry('attachment',case_id,file_id,background_tasks)

@router.get('/{case_id}/deliverables/{file_id}/file')
def download(case_id: str,file_id: str,user=Depends(require_active_user)):
    with get_db() as conn:
        visible_case(conn,case_id,user['role']=='admin');row=files.get_file(conn,'attachment',case_id,file_id)
    return files.respond(row)

@router.get('/{case_id}/deliverables/{file_id}/preview')
def preview(case_id: str,file_id: str,user=Depends(require_active_user)):
    with get_db() as conn:
        visible_case(conn,case_id,user['role']=='admin');row=files.get_file(conn,'attachment',case_id,file_id)
    return files.respond(row,True)

@router.delete('/{case_id}/deliverables/{file_id}',status_code=204,dependencies=[Depends(require_admin)])
def delete_deliverable(case_id: str,file_id: str):
    with get_db() as conn: case=visible_case(conn,case_id,True)
    files.remove('attachment',case_id,file_id,case['partner_id'])

@router.delete('/{case_id}',status_code=204)
def delete_case(case_id: str,actor=Depends(require_admin)):
    from pathlib import Path
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE');case=visible_case(conn,case_id,True)
        paths=[dict(r) for r in conn.execute('SELECT file_path,preview_path FROM deliverables WHERE case_id=?',(case_id,))]
        conn.execute('DELETE FROM deliverables WHERE case_id=?',(case_id,));conn.execute('DELETE FROM cases WHERE id=?',(case_id,))
        files.changed(conn,case['partner_id'])
        record_audit(conn,'case_deleted',actor_user_id=actor['id'],summary={'case_id':case_id})
    for row in paths:
        for path in row.values():
            if path: Path(path).unlink(missing_ok=True)

@router.put('/{case_id}/deliverables/{file_id}',response_model=DeliverableOut)
async def replace_deliverable(case_id: str,file_id: str,background_tasks: BackgroundTasks,file: UploadFile=File(...),actor=Depends(require_admin)):
    with get_db() as conn: visible_case(conn,case_id,True)
    return await files.replace('attachment',case_id,file_id,file,background_tasks)
