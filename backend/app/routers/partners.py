"""Partner CRUD router - requires authentication."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, status

from ..auth import require_auth
from ..database import get_db
from ..models import PartnerCreate, PartnerOut


router = APIRouter(prefix="/partners", tags=["partners"], dependencies=[Depends(require_auth)])
_COLUMNS = "id, name, intro, capabilities, service_areas, industries, ai_profile, created_at"


@router.get("", response_model=list[PartnerOut])
def list_partners() -> list[PartnerOut]:
    with get_db() as conn:
        rows = conn.execute(f"SELECT {_COLUMNS} FROM partners ORDER BY created_at DESC").fetchall()
    return [PartnerOut(**dict(r)) for r in rows]


@router.get("/{partner_id}", response_model=PartnerOut)
def get_partner(partner_id: str) -> PartnerOut:
    with get_db() as conn:
        row = conn.execute(f"SELECT {_COLUMNS} FROM partners WHERE id = ?", (partner_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Partner not found")
    return PartnerOut(**dict(row))


@router.post("", response_model=PartnerOut, status_code=status.HTTP_201_CREATED)
def create_partner(payload: PartnerCreate) -> PartnerOut:
    partner = PartnerOut(id=str(uuid.uuid4()), name=payload.name, intro=payload.intro, capabilities=payload.capabilities, service_areas=payload.service_areas, industries=payload.industries, ai_profile=None, created_at=datetime.now(timezone.utc).isoformat())
    with get_db() as conn:
        conn.execute(f"INSERT INTO partners ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (partner.id, partner.name, partner.intro, partner.capabilities, partner.service_areas, partner.industries, partner.ai_profile, partner.created_at))
    return partner
