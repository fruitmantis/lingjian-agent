"""Partner CRUD router - requires authentication."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel

from ..auth import require_auth
from ..database import get_db
from ..models import PartnerCreate, PartnerOut


class PartnerUpdate(BaseModel):
    name: str | None = None
    intro: str | None = None
    capabilities: str | None = None
    service_areas: str | None = None
    industries: str | None = None


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
    healthScore: int
    healthLevel: str
    healthReason: str


def calculate_partner_health(ai_profile, capabilities, service_areas, industries, case_count, deliverable_count):
    """Lightweight rule-based partner health score (0-100)."""
    score = 60
    reasons = []
    if ai_profile:
        score += 15; reasons.append("已生成AI画像(+15)")
    if capabilities and capabilities.strip():
        score += 10; reasons.append("有能力标签(+10)")
    if industries and industries.strip():
        score += 5; reasons.append("有行业经验(+5)")
    if service_areas and service_areas.strip():
        score += 5; reasons.append("有覆盖区域(+5)")
    if case_count > 0:
        score += 5; reasons.append(f"有案例{case_count}个(+5)")
    if deliverable_count > 0:
        score += 5; reasons.append(f"有交付物{deliverable_count}个(+5)")
    score = min(score, 100)
    if score >= 80:
        level = "healthy"
    elif score >= 60:
        level = "normal"
    else:
        level = "risk"
    reason = "; ".join(reasons) if reasons else "仅有基础信息"
    return score, level, reason


@router.get("/profiles", response_model=list[PartnerProfileCard])
def list_profiles() -> list[PartnerProfileCard]:
    with get_db() as conn:
        partners = conn.execute(f"SELECT {_COLUMNS} FROM partners ORDER BY created_at DESC").fetchall()
        result = []
        for p in partners:
            pd = dict(p)
            case_count = conn.execute("SELECT COUNT(*) as cnt FROM cases WHERE partner_id = ?", (pd["id"],)).fetchone()["cnt"]
            deliverable_count = conn.execute("SELECT COUNT(*) as cnt FROM deliverables WHERE case_id IN (SELECT id FROM cases WHERE partner_id = ?)", (pd["id"],)).fetchone()["cnt"]
            hs, hl, hr = calculate_partner_health(pd.get("ai_profile"), pd.get("capabilities"), pd.get("service_areas"), pd.get("industries"), case_count, deliverable_count)
            result.append(PartnerProfileCard(id=pd["id"], name=pd["name"], capabilities=pd.get("capabilities"), service_areas=pd.get("service_areas"), industries=pd.get("industries"), ai_profile=pd.get("ai_profile"), case_count=case_count, deliverable_count=deliverable_count, healthScore=hs, healthLevel=hl, healthReason=hr))
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



@router.put("/{partner_id}", response_model=PartnerOut)
def update_partner(partner_id: str, payload: PartnerUpdate) -> PartnerOut:
    with get_db() as conn:
        row = conn.execute(f"SELECT {_COLUMNS} FROM partners WHERE id = ?", (partner_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="伙伴不存在")
        updates = []
        params = []
        if payload.name is not None:
            updates.append("name = ?"); params.append(payload.name)
        if payload.intro is not None:
            updates.append("intro = ?"); params.append(payload.intro)
        if payload.capabilities is not None:
            updates.append("capabilities = ?"); params.append(payload.capabilities)
        if payload.service_areas is not None:
            updates.append("service_areas = ?"); params.append(payload.service_areas)
        if payload.industries is not None:
            updates.append("industries = ?"); params.append(payload.industries)
        if updates:
            params.append(partner_id)
            conn.execute(f"UPDATE partners SET {', '.join(updates)} WHERE id = ?", params)
        row = conn.execute(f"SELECT {_COLUMNS} FROM partners WHERE id = ?", (partner_id,)).fetchone()
    return PartnerOut(**dict(row))


@router.delete("/{partner_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_partner(partner_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT id FROM partners WHERE id = ?", (partner_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="伙伴不存在")
        # Delete related data first
        case_ids = [r[0] for r in conn.execute("SELECT id FROM cases WHERE partner_id = ?", (partner_id,)).fetchall()]
        if case_ids:
            placeholders = ",".join("?" * len(case_ids))
            conn.execute(f"DELETE FROM deliverables WHERE case_id IN ({placeholders})", case_ids)
            conn.execute(f"DELETE FROM cases WHERE partner_id = ?", (partner_id,))
        conn.execute("DELETE FROM partner_documents WHERE partner_id = ?", (partner_id,))
        conn.execute("DELETE FROM partners WHERE id = ?", (partner_id,))
