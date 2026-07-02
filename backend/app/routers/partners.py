"""Partner CRUD router - requires authentication."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel

from ..auth import require_auth
from ..database import get_db
from ..models import PartnerCreate, PartnerOut


router = APIRouter(prefix="/partners", tags=["partners"], dependencies=[Depends(require_auth)])
_COLUMNS = "id, name, intro, capabilities, service_areas, industries, ai_profile, created_at"


class PartnerProfileCard(BaseModel):
    id: str
    name: str
    capabilities: str | None
    service_areas: str | None
    industries: str | None
    ai_profile: str | None
    case_count: int
    deliverable_count: int


@router.get("/profiles", response_model=list[PartnerProfileCard])
def list_profiles() -> list[PartnerProfileCard]:
    with get_db() as conn:
        partners = conn.execute(f"SELECT {_COLUMNS} FROM partners ORDER BY created_at DESC").fetchall()
        result = []
        for p in partners:
            pd = dict(p)
            case_count = conn.execute("SELECT COUNT(*) as cnt FROM cases WHERE partner_id = ?", (pd["id"],)).fetchone()["cnt"]
            deliverable_count = conn.execute("SELECT COUNT(*) as cnt FROM deliverables WHERE case_id IN (SELECT id FROM cases WHERE partner_id = ?)", (pd["id"],)).fetchone()["cnt"]
            result.append(PartnerProfileCard(id=pd["id"], name=pd["name"], capabilities=pd.get("capabilities"), service_areas=pd.get("service_areas"), industries=pd.get("industries"), ai_profile=pd.get("ai_profile"), case_count=case_count, deliverable_count=deliverable_count))
    return result


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
