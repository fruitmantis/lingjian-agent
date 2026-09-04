"""Case and deliverable router."""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status

from ..auth import require_active_user, require_admin
from ..database import get_db, UPLOADS_DIR
from ..file_storage import save_upload_limited
from ..models import CaseCreate, CaseOut, DeliverableOut


router = APIRouter(prefix="/cases", tags=["cases"], dependencies=[Depends(require_active_user)])

_CASE_COLS = "id, partner_id, title, description, created_at"
_DELIV_COLS = "id, case_id, filename, file_path, created_at"


@router.get("/by-partner/{partner_id}", response_model=list[CaseOut])
def list_cases_by_partner(partner_id: str, user: dict = Depends(require_active_user)) -> list[CaseOut]:
    with get_db() as conn:
        partner = conn.execute("SELECT status FROM partners WHERE id = ?", (partner_id,)).fetchone()
        if partner is None or (partner["status"] != "active" and user["role"] != "admin"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Partner not found")
        rows = conn.execute(
            f"SELECT {_CASE_COLS} FROM cases WHERE partner_id = ? ORDER BY created_at DESC",
            (partner_id,),
        ).fetchall()
    return [CaseOut(**dict(r)) for r in rows]


@router.post("", response_model=CaseOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
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
def list_deliverables(case_id: str, user: dict = Depends(require_active_user)) -> list[DeliverableOut]:
    with get_db() as conn:
        case = conn.execute("SELECT p.status FROM cases c JOIN partners p ON p.id = c.partner_id WHERE c.id = ?", (case_id,)).fetchone()
        if case is None or (case["status"] != "active" and user["role"] != "admin"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Case not found")
        rows = conn.execute(
            f"SELECT {_DELIV_COLS} FROM deliverables WHERE case_id = ? ORDER BY created_at DESC",
            (case_id,),
        ).fetchall()
    return [DeliverableOut(**dict(r)) for r in rows]


@router.post("/{case_id}/deliverables", response_model=DeliverableOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
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
    try:
        await save_upload_limited(file, file_path)
        deliv = DeliverableOut(
            id=deliverable_id,
            case_id=case_id,
            filename=file.filename,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with get_db() as conn:
            conn.execute(
                f"INSERT INTO deliverables ({_DELIV_COLS}) VALUES (?, ?, ?, ?, ?)",
                (deliv.id, deliv.case_id, deliv.filename, str(file_path), deliv.created_at),
            )
    except Exception:
        file_path.unlink(missing_ok=True)
        raise
    return deliv


@router.delete("/{case_id}/deliverables/{deliverable_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
def delete_deliverable(case_id: str, deliverable_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT file_path FROM deliverables WHERE id = ? AND case_id = ?", (deliverable_id, case_id)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="交付物不存在")
        conn.execute("DELETE FROM deliverables WHERE id = ? AND case_id = ?", (deliverable_id, case_id))
    try:
        Path(row["file_path"]).unlink(missing_ok=True)
    except OSError:
        pass


@router.delete("/{case_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_admin)])
def delete_case(case_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT id FROM cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="案例不存在")
        files = [row["file_path"] for row in conn.execute("SELECT file_path FROM deliverables WHERE case_id = ?", (case_id,)).fetchall()]
        conn.execute("DELETE FROM deliverables WHERE case_id = ?", (case_id,))
        conn.execute("DELETE FROM cases WHERE id = ?", (case_id,))
    for file_path in files:
        try:
            Path(file_path).unlink(missing_ok=True)
        except OSError:
            pass
