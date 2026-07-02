"""Demand profile operations router."""

from fastapi import APIRouter
from pydantic import BaseModel
from ..database import get_db


router = APIRouter(prefix="/agent", tags=["demand"])


class DemandProfileOut(BaseModel):
    id: str
    matchRecordId: str | None
    requirementText: str
    industryTags: str | None
    capabilityTags: str | None
    deliveryTypeTags: str | None
    regionTags: str | None
    complexityLevel: str | None
    urgencyLevel: str | None
    projectKeywords: str | None
    matchedPartnerCount: int
    topPartnerNames: str | None
    supplyStatus: str | None
    gapAnalysis: str | None
    createdAt: str


class DemandOverview(BaseModel):
    totalDemands: int
    thisMonthDemands: int
    topCapabilityTags: str
    gapDemandCount: int
    avgPartnerCount: float


class DemandOverviewResponse(BaseModel):
    overview: DemandOverview
    profiles: list[DemandProfileOut]
    industryDistribution: dict[str, int]
    capabilityDistribution: dict[str, int]
    regionDistribution: dict[str, int]
    deliveryTypeDistribution: dict[str, int]


def _count_tags(rows, col) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rows:
        val = r[col] or ""
        for tag in val.split(","):
            tag = tag.strip()
            if tag:
                counts[tag] = counts.get(tag, 0) + 1
    return counts


@router.get("/demand-profiles", response_model=DemandOverviewResponse)
def list_demand_profiles() -> DemandOverviewResponse:
    with get_db() as conn:
        rows = conn.execute("SELECT id, match_record_id, requirement_text, industry_tags, capability_tags, delivery_type_tags, region_tags, complexity_level, urgency_level, project_keywords, matched_partner_count, top_partner_names, supply_status, gap_analysis, created_at FROM demand_profiles ORDER BY created_at DESC").fetchall()

    profiles = [DemandProfileOut(
        id=r["id"], matchRecordId=r["match_record_id"], requirementText=r["requirement_text"],
        industryTags=r["industry_tags"], capabilityTags=r["capability_tags"], deliveryTypeTags=r["delivery_type_tags"],
        regionTags=r["region_tags"], complexityLevel=r["complexity_level"], urgencyLevel=r["urgency_level"],
        projectKeywords=r["project_keywords"], matchedPartnerCount=r["matched_partner_count"],
        topPartnerNames=r["top_partner_names"], supplyStatus=r["supply_status"], gapAnalysis=r["gap_analysis"],
        createdAt=r["created_at"]
    ) for r in rows]

    # Overview metrics
    total = len(rows)
    this_month = sum(1 for r in rows if r["created_at"][:7] == __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m"))
    gap_count = sum(1 for r in rows if r["supply_status"] == "gap")
    avg_count = sum(r["matched_partner_count"] for r in rows) / total if total else 0

    # Top capability tags (top 3)
    cap_dist = _count_tags(rows, "capability_tags")
    top_caps = ", ".join(sorted(cap_dist, key=cap_dist.get, reverse=True)[:3]) if cap_dist else "暂无"

    overview = DemandOverview(
        totalDemands=total, thisMonthDemands=this_month, topCapabilityTags=top_caps,
        gapDemandCount=gap_count, avgPartnerCount=round(avg_count, 1)
    )

    return DemandOverviewResponse(
        overview=overview, profiles=profiles,
        industryDistribution=_count_tags(rows, "industry_tags"),
        capabilityDistribution=cap_dist,
        regionDistribution=_count_tags(rows, "region_tags"),
        deliveryTypeDistribution=_count_tags(rows, "delivery_type_tags"),
    )