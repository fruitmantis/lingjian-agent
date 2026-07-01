"""Case and deliverable router."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, status

from ..database import get_db, UPLOADS_DIR
from ..models import CaseCreate, CaseOut, DeliverableOut


router = APIRouter(prefix="/cases", tags=["cases"])

_CASE_COLS = "id, partner_id, title, description, created_at"
_DELIV_COLS = "id, case_id, filename, file_path, created_at"


@router.get("/by-partner/{partner_id}", response_model=list[CaseOut])
def list_cases_by_partner(partner_id: str) -> list[CaseOut]:
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT {_CASE_COLS} FROM cases WHERE partner_id = ? ORDER BY created_at DESC",
            (partner_id,),
        ).fetchall()
    return [CaseOut(**dict(r)) for r in rows]


@router.post("", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(payload: CaseCreate) -> CaseOut:
    case = CaseOut(
        id=str(uuid.uuid4()),
        partner_id=payload.partner_id,
        title=payload.title,
        description=payload.description,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    with get_db() as conn:
        partner = conn.execute("SELECT id FROM partners WHERE id = ?", (payload.partner_id,)).fetchone()
        if partner is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Partner not found")
        conn.execute(
            f"INSERT INTO cases ({_CASE_COLS}) VALUES (?, ?, ?, ?, ?)",
            (case.id, case.partner_id, case.title, case.description, case.created_at),
        )
    return case


@router.get("/{case_id}/deliverables", response_model=list[DeliverableOut])
def list_deliverables(case_id: str) -> list[DeliverableOut]:
    with get_db() as conn:
        rows = conn.execute(
            f"SELECT {_DELIV_COLS} FROM deliverables WHERE case_id = ? ORDER BY created_at DESC",
            (case_id,),
        ).fetchall()
    return [DeliverableOut(**dict(r)) for r in rows]


@router.post("/{case_id}/deliverables", response_model=DeliverableOut, status_code=status.HTTP_201_CREATED)
async def upload_deliverable(case_id: str, file: UploadFile = File(...)) -> DeliverableOut:
    if not file.filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No filename")
    with get_db() as conn:
        case = conn.execute("SELECT id FROM cases WHERE id = ?", (case_id,)).fetchone()
        if case is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Case not found")

    deliverable_id = str(uuid.uuid4())
    safe_name = Path(file.filename).name
    stored_name = f"{deliverable_id}_{safe_name}"
    file_path = UPLOADS_DIR / stored_name
    content = await file.read()
    file_path.write_bytes(content)

    deliv = DeliverableOut(
        id=deliverable_id,
        case_id=case_id,
        filename=file.filename,
        file_path=str(file_path),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    with get_db() as conn:
        conn.execute(
            f"INSERT INTO deliverables ({_DELIV_COLS}) VALUES (?, ?, ?, ?, ?)",
            (deliv.id, deliv.case_id, deliv.filename, deliv.file_path, deliv.created_at),
        )
    return deliv
