"""Rule-based partner matching router."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..database import get_db


router = APIRouter(prefix="/agent", tags=["agent"])

_P_COLS = "id, name, intro, capabilities, service_areas, industries, ai_profile, created_at"
_CASE_COLS = "id, partner_id, title, description, created_at"


class MatchRequest(BaseModel):
    requirement: str = Field(..., min_length=1, description="项目需求描述")


class PartnerRecommendation(BaseModel):
    partnerId: str
    partnerName: str
    matchScore: int
    matchedCapabilities: str
    matchedIndustries: str
    matchedRegions: str
    recommendationReason: str
    evidenceCases: str
    evidenceDeliverables: str
    riskNotes: str


class MatchResponse(BaseModel):
    requirement: str
    recommendations: list[PartnerRecommendation]


def _split_tags(val: str | None) -> list[str]:
    if not val:
        return []
    return [t.strip() for t in val.replace("，", ",").split(",") if t.strip()]


def _keyword_match(requirement_lower: str, tags: list[str]) -> list[str]:
    """Return tags that appear in the requirement text."""
    matched = []
    for tag in tags:
        if tag and tag.lower() in requirement_lower:
            matched.append(tag)
    return matched


@router.post("/match", response_model=MatchResponse)
def match_partners(req: MatchRequest) -> MatchResponse:
    requirement_lower = req.requirement.lower()

    with get_db() as conn:
        partners = conn.execute(f"SELECT {_P_COLS} FROM partners").fetchall()
        if not partners:
            return MatchResponse(requirement=req.requirement, recommendations=[])

        results: list[PartnerRecommendation] = []
        for p in partners:
            pd = dict(p)
            pid = pd["id"]

            # Get case count and deliverable count
            case_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM cases WHERE partner_id = ?", (pid,)
            ).fetchone()["cnt"]
            deliverable_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM deliverables WHERE case_id IN (SELECT id FROM cases WHERE partner_id = ?)",
                (pid,),
            ).fetchone()["cnt"]

            # Get case titles for evidence
            cases = conn.execute(
                f"SELECT {_CASE_COLS} FROM cases WHERE partner_id = ?", (pid,)
            ).fetchall()
            case_titles = [c["title"] for c in cases]

            # Parse tags
            cap_tags = _split_tags(pd.get("capabilities"))
            ind_tags = _split_tags(pd.get("industries"))
            area_tags = _split_tags(pd.get("service_areas"))

            # Keyword matching
            matched_caps = _keyword_match(requirement_lower, cap_tags)
            matched_inds = _keyword_match(requirement_lower, ind_tags)
            matched_areas = _keyword_match(requirement_lower, area_tags)

            has_ai_profile = bool(pd.get("ai_profile"))

            # Scoring (0-100)
            # Tag matching: 40% (capabilities 20%, industries 10%, regions 10%)
            cap_score = min(20, len(matched_caps) * 10)
            ind_score = min(10, len(matched_inds) * 5)
            area_score = min(10, len(matched_areas) * 5)

            # Case count: 20% (up to 20 points)
            case_score = min(20, case_count * 5)

            # Deliverable count: 15%
            deliv_score = min(15, deliverable_count * 3)

            # AI profile: 15%
            ai_score = 15 if has_ai_profile else 0

            total = cap_score + ind_score + area_score + case_score + deliv_score + ai_score

            # Build reason
            reason_parts = []
            if matched_caps:
                reason_parts.append(f"能力匹配({', '.join(matched_caps)})")
            if matched_inds:
                reason_parts.append(f"行业匹配({', '.join(matched_inds)})")
            if matched_areas:
                reason_parts.append(f"区域匹配({', '.join(matched_areas)})")
            if case_count > 0:
                reason_parts.append(f"有{case_count}个案例")
            if deliverable_count > 0:
                reason_parts.append(f"有{deliverable_count}个交付物")
            if has_ai_profile:
                reason_parts.append("AI画像已生成")
            if not reason_parts:
                reason_parts.append("无直接匹配项")

            # Risk notes
            risks = []
            if not has_ai_profile:
                risks.append("AI画像未生成")
            if case_count == 0:
                risks.append("无案例数据")
            if deliverable_count == 0:
                risks.append("无交付物")
            if not matched_caps and cap_tags:
                risks.append("能力标签未匹配需求")
            risk_text = "；".join(risks) if risks else "暂无明显风险"

            results.append(PartnerRecommendation(
                partnerId=pid,
                partnerName=pd["name"],
                matchScore=total,
                matchedCapabilities=", ".join(matched_caps) if matched_caps else "",
                matchedIndustries=", ".join(matched_inds) if matched_inds else "",
                matchedRegions=", ".join(matched_areas) if matched_areas else "",
                recommendationReason="；".join(reason_parts),
                evidenceCases=", ".join(case_titles) if case_titles else "",
                evidenceDeliverables=f"{deliverable_count}个交付物" if deliverable_count else "",
                riskNotes=risk_text,
            ))

    # Sort by score descending
    results.sort(key=lambda x: x.matchScore, reverse=True)
    return MatchResponse(requirement=req.requirement, recommendations=results)