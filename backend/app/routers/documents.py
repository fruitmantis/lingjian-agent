"""Partner document upload and management router."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, status

from ..database import get_db, UPLOADS_DIR
from ..doc_extractor import extract_text, get_file_type
from ..models import PartnerDocumentOut


router = APIRouter(prefix="/partners", tags=["documents"])
_DOC_COLS = "id, partner_id, filename, file_type, doc_category, extracted_text, created_at"
_ALLOWED_TYPES = {"pdf", "docx", "pptx", "xlsx"}


@router.get("/{partner_id}/documents", response_model=list[PartnerDocumentOut])
def list_documents(partner_id: str) -> list[PartnerDocumentOut]:
    with get_db() as conn:
        rows = conn.execute(f"SELECT {_DOC_COLS} FROM partner_documents WHERE partner_id = ? ORDER BY created_at DESC", (partner_id,)).fetchall()
    return [PartnerDocumentOut(**dict(r)) for r in rows]


@router.post("/{partner_id}/documents", response_model=PartnerDocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(partner_id: str, file: UploadFile = File(...)) -> PartnerDocumentOut:
    if not file.filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No filename")
    file_type = get_file_type(file.filename)
    if file_type not in _ALLOWED_TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unsupported file type. Allowed: {', '.join(_ALLOWED_TYPES)}")
    with get_db() as conn:
        partner = conn.execute("SELECT id FROM partners WHERE id = ?", (partner_id,)).fetchone()
        if partner is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Partner not found")
    doc_id = str(uuid.uuid4())
    safe_name = Path(file.filename).name
    stored_name = f"{doc_id}_{safe_name}"
    file_path = UPLOADS_DIR / stored_name
    content = await file.read()
    file_path.write_bytes(content)
    extracted = extract_text(str(file_path), file_type)
    doc = PartnerDocumentOut(id=doc_id, partner_id=partner_id, filename=file.filename, file_type=file_type, doc_category=None, extracted_text=extracted, created_at=datetime.now(timezone.utc).isoformat())
    with get_db() as conn:
        conn.execute(f"INSERT INTO partner_documents ({_DOC_COLS}) VALUES (?, ?, ?, ?, ?, ?, ?)", (doc.id, doc.partner_id, doc.filename, doc.file_type, doc.doc_category, doc.extracted_text, doc.created_at))
    return doc


@router.delete("/{partner_id}/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(partner_id: str, doc_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT file_path FROM partner_documents WHERE id = ? AND partner_id = ?", (doc_id, partner_id)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Document not found")
        try:
            Path(row["file_path"]).unlink(missing_ok=True)
        except Exception:
            pass
        conn.execute("DELETE FROM partner_documents WHERE id = ? AND partner_id = ?", (doc_id, partner_id))
    return None
