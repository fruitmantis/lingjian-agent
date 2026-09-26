"""Private partner materials. Originals and complete cached text stay admin-only."""
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from ..auth import require_admin
from ..database import get_db
from .. import material_files as files
from ..models import PartnerDocumentOut

router=APIRouter(prefix='/partners',tags=['documents'],dependencies=[Depends(require_admin)])

def partner_exists(partner_id):
    with get_db() as conn:
        if not conn.execute('SELECT id FROM partners WHERE id=?',(partner_id,)).fetchone(): raise HTTPException(404,'伙伴不存在')

@router.get('/{partner_id}/documents',response_model=list[PartnerDocumentOut])
def list_documents(partner_id: str):
    partner_exists(partner_id)
    with get_db() as conn:
        return [files.public_file(r) for r in conn.execute('SELECT * FROM partner_documents WHERE partner_id=? ORDER BY created_at DESC',(partner_id,))]

@router.post('/{partner_id}/documents',response_model=PartnerDocumentOut,status_code=201)
async def upload_document(partner_id: str,background_tasks: BackgroundTasks,file: UploadFile=File(...),initialize_profile: bool=Form(False)):
    partner_exists(partner_id)
    return await files.save('document',partner_id,partner_id,file,background_tasks,import_profile=initialize_profile)

@router.post('/{partner_id}/documents/{doc_id}/retry')
def retry_document(partner_id: str,doc_id: str,background_tasks: BackgroundTasks):
    return files.retry('document',partner_id,doc_id,background_tasks)

@router.get('/{partner_id}/documents/{doc_id}/text')
def text_document(partner_id: str,doc_id: str):
    with get_db() as conn: row=files.get_file(conn,'document',partner_id,doc_id)
    return {'text':row['extracted_text'],'processing_status':row['processing_status']}

@router.get('/{partner_id}/documents/{doc_id}/preview')
def preview_document(partner_id: str,doc_id: str):
    with get_db() as conn: row=files.get_file(conn,'document',partner_id,doc_id)
    return files.respond(row,True)

@router.get('/{partner_id}/documents/{doc_id}/file')
def download_document(partner_id: str,doc_id: str):
    with get_db() as conn: row=files.get_file(conn,'document',partner_id,doc_id)
    return files.respond(row)

@router.delete('/{partner_id}/documents/{doc_id}',status_code=204)
def delete_document(partner_id: str,doc_id: str):
    files.remove('document',partner_id,doc_id,partner_id)

@router.put('/{partner_id}/documents/{doc_id}',response_model=PartnerDocumentOut)
async def replace_document(partner_id: str,doc_id: str,background_tasks: BackgroundTasks,file: UploadFile=File(...)):
    return await files.replace('document',partner_id,doc_id,file,background_tasks)
