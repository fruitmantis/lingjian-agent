"""Demand profile operations router."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from ..database import get_db
from ..auth import require_active_user, require_admin


router = APIRouter(prefix="/agent", tags=["demand"], dependencies=[Depends(require_active_user)])
admin_router = APIRouter(prefix="/admin", tags=["admin-demand"], dependencies=[Depends(require_admin)])


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


@admin_router.get("/demand-profiles", response_model=DemandOverviewResponse)
def list_demand_profiles() -> DemandOverviewResponse:
    with get_db() as conn:
        rows = conn.execute("""SELECT dp.id, dp.match_record_id, dp.requirement_text, dp.industry_tags, dp.capability_tags,
                                      dp.delivery_type_tags, dp.region_tags, dp.complexity_level, dp.urgency_level,
                                      dp.project_keywords, dp.matched_partner_count, dp.top_partner_names,
                                      dp.supply_status, dp.gap_analysis, dp.created_at
                               FROM demand_profiles dp
                               LEFT JOIN match_records mr ON mr.id = dp.match_record_id
                               WHERE dp.match_record_id IS NULL OR mr.archived_at IS NULL
                               ORDER BY dp.created_at DESC""").fetchall()

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

# ============ Operations Report ============

class ReportOverview(BaseModel):
    totalDemands: int
    thisMonthDemands: int
    totalPartners: int
    partnersWithProfile: int
    activePartners: int
    noPartnerDemands: int
    partialDemands: int
    pendingSuggestions: int

class ReportDist(BaseModel):
    label: str
    count: int

class SupplyGapItem(BaseModel):
    capability: str
    demandCount: int
    partnerCount: int
    supplyStatus: str
    gapNote: str

class PartnerActivity(BaseModel):
    partnerName: str
    recommendCount: int
    lastUpdated: str

class ReportResponse(BaseModel):
    overview: ReportOverview
    capabilityDist: list[ReportDist]
    industryDist: list[ReportDist]
    regionDist: list[ReportDist]
    deliveryTypeDist: list[ReportDist]
    supplyGaps: list[SupplyGapItem]
    activePartnerCount: int
    activePartnerRatio: float
    topRecommendedPartners: list[PartnerActivity]
    inactivePartners: list[PartnerActivity]
    pendingSuggestions: int
    uncoveredClues: int
    topFormalTags: list[ReportDist]


@admin_router.get("/reports", response_model=ReportResponse)
def get_report(days: int = 0, industry: str | None = None, region: str | None = None, capability: str | None = None):
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat() if days > 0 else "1970-01-01"
    with get_db() as conn:
        q = """SELECT dp.*, mr.recommendations_json AS task_recommendations FROM demand_profiles dp
               LEFT JOIN match_records mr ON mr.id = dp.match_record_id
               WHERE dp.created_at >= ? AND (dp.match_record_id IS NULL OR mr.archived_at IS NULL)"""
        params = [cutoff]
        if industry:
            q += " AND industry_tags LIKE ?"
            params.append(f"%{industry}%")
        if region:
            q += " AND region_tags LIKE ?"
            params.append(f"%{region}%")
        if capability:
            q += " AND capability_tags LIKE ?"
            params.append(f"%{capability}%")
        q += " ORDER BY created_at DESC"
        rows = conn.execute(q, params).fetchall()

        now_str = datetime.now(timezone.utc).strftime("%Y-%m")
        total = len(rows)
        this_month = sum(1 for r in rows if r["created_at"][:7] == now_str)
        no_partner = sum(1 for r in rows if r["supply_status"] == "gap")
        partial = sum(1 for r in rows if r["supply_status"] == "partial")

        partners = conn.execute("SELECT id, name, ai_profile, created_at, updated_at FROM partners").fetchall()
        total_partners = len(partners)
        with_profile = sum(1 for p in partners if p["ai_profile"])

        # Activity uses the same filtered, unarchived demand population as the charts.
        # Keep inventory totals global; count each partner at most once per task.
        import json as _j
        partners_by_id = {p["id"]: p for p in partners}
        ids_by_name: dict[str, list[str]] = {}
        for partner in partners:
            ids_by_name.setdefault(partner["name"], []).append(partner["id"])
        rec_counts: dict[str, int] = {}
        last_recommended: dict[str, str] = {}
        seen_tasks = set()
        for rr in rows:
            task_id = rr["match_record_id"]
            if not task_id or task_id in seen_tasks:
                continue
            seen_tasks.add(task_id)
            try:
                recs = _j.loads(rr["task_recommendations"] or "[]")
            except (TypeError, ValueError):
                continue
            if not isinstance(recs, list):
                continue
            task_partners = set()
            for rec in recs:
                if not isinstance(rec, dict):
                    continue
                partner_id = rec.get("partnerId")
                if not isinstance(partner_id, str) or partner_id not in partners_by_id:
                    # Older records may contain only a name; use it only if unambiguous.
                    name = rec.get("partnerName")
                    candidates = ids_by_name.get(name, []) if isinstance(name, str) else []
                    if len(candidates) != 1:
                        continue
                    partner_id = candidates[0]
                task_partners.add(partner_id)
            for partner_id in task_partners:
                rec_counts[partner_id] = rec_counts.get(partner_id, 0) + 1
                last_recommended[partner_id] = max(last_recommended.get(partner_id, ""), rr["created_at"])

        active_count = len(rec_counts)
        active_ratio = round(active_count / total_partners * 100, 1) if total_partners else 0

        # Top recommended partners
        top_recs = sorted(rec_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        top_rec_list = [PartnerActivity(partnerName=partners_by_id[pid]["name"], recommendCount=c, lastUpdated=last_recommended[pid][:10]) for pid, c in top_recs]

        # Inactive partners (not in active_set)
        inactive = [PartnerActivity(partnerName=p["name"], recommendCount=0, lastUpdated=(p["updated_at"] or p["created_at"])[:10]) for p in partners if p["id"] not in rec_counts][:10]

        # Pending suggestions
        pending = conn.execute("SELECT COUNT(*) as cnt FROM capability_tag_suggestions WHERE status = 'pending'").fetchone()["cnt"]
        total_sugs = conn.execute("SELECT COUNT(*) as cnt FROM capability_tag_suggestions").fetchone()["cnt"]

        # Formal tags distribution from partners
        partner_rows = conn.execute("SELECT id, capabilities, status FROM partners WHERE capabilities IS NOT NULL AND capabilities != ''").fetchall()
        formal_counts = {}
        for pr in partner_rows:
            for tag in {value.strip() for value in (pr["capabilities"] or "").split(",")}:
                if tag:
                    formal_counts[tag] = formal_counts.get(tag, 0) + 1
        top_formal = sorted([ReportDist(label=k, count=v) for k, v in formal_counts.items()], key=lambda x: x.count, reverse=True)[:10]

        # Supply gaps: aggregate by capability tag
        cap_demand = {}
        for r in rows:
            for tag in (r["capability_tags"] or "").split(","):
                tag = tag.strip()
                if tag:
                    if tag not in cap_demand:
                        cap_demand[tag] = {"demand": 0, "partners": set()}
                    cap_demand[tag]["demand"] += 1

        # Available supply includes only enabled partners, distinct by their real ID.
        for pr in partner_rows:
            if pr["status"] != "active":
                continue
            for tag in (pr["capabilities"] or "").split(","):
                tag = tag.strip()
                if tag in cap_demand:
                    cap_demand[tag]["partners"].add(pr["id"])

        supply_gaps = []
        for cap, data in cap_demand.items():
            pcount = len(data["partners"])
            if pcount == 0:
                status = "gap"
                note = "无伙伴覆盖此能力"
            elif pcount <= 2:
                status = "partial"
                note = f"仅{pcount}个伙伴覆盖"
            else:
                status = "sufficient"
                note = f"{pcount}个伙伴可覆盖"
            supply_gaps.append(SupplyGapItem(capability=cap, demandCount=data["demand"], partnerCount=pcount, supplyStatus=status, gapNote=note))
        supply_gaps.sort(key=lambda x: (-1 if x.supplyStatus == "gap" else 0, x.demandCount), reverse=True)

        # Distributions
        def count_tags(col):
            counts = {}
            for r in rows:
                for tag in (r[col] or "").split(","):
                    tag = tag.strip()
                    if tag:
                        counts[tag] = counts.get(tag, 0) + 1
            return sorted([ReportDist(label=k, count=v) for k, v in counts.items()], key=lambda x: x.count, reverse=True)[:10]

    return ReportResponse(
        overview=ReportOverview(totalDemands=total, thisMonthDemands=this_month, totalPartners=total_partners,
            partnersWithProfile=with_profile, activePartners=active_count, noPartnerDemands=no_partner,
            partialDemands=partial, pendingSuggestions=pending),
        capabilityDist=count_tags("capability_tags"),
        industryDist=count_tags("industry_tags"),
        regionDist=count_tags("region_tags"),
        deliveryTypeDist=count_tags("delivery_type_tags"),
        supplyGaps=supply_gaps[:15],
        activePartnerCount=active_count,
        activePartnerRatio=active_ratio,
        topRecommendedPartners=top_rec_list,
        inactivePartners=inactive,
        pendingSuggestions=pending,
        uncoveredClues=total_sugs,
        topFormalTags=top_formal,
    )


# ============ Project Opportunities ============

class OpportunityOut(BaseModel):
    id: str
    matchRecordId: str | None
    requirementText: str
    customerName: str | None
    projectName: str | None
    industry: str | None
    region: str | None
    projectStage: str | None
    businessNeeds: str | None
    technicalNeeds: str | None
    deliveryNeeds: str | None
    qualificationRequirements: str | None
    caseRequirements: str | None
    onsiteRequirement: str | None
    timelineRequirement: str | None
    cloudPlatformPreference: str | None
    matchedCapabilityTags: str | None
    unmatchedCapabilitySignals: str | None
    recommendedPartnerNames: str | None
    supplyStatus: str | None
    completenessScore: float
    missingFields: str | None
    followUpQuestions: str | None
    createdAt: str
    updatedAt: str


class OpportunityUpdate(BaseModel):
    customerName: str | None = None
    projectName: str | None = None
    industry: str | None = None
    region: str | None = None
    projectStage: str | None = None
    businessNeeds: str | None = None


_OPPORTUNITY_FIELDS = (
    ("customerName", "customer_name"), ("projectName", "project_name"),
    ("industry", "industry"), ("region", "region"),
    ("projectStage", "project_stage"), ("businessNeeds", "business_needs"),
)


def calculate_opportunity_completeness(values: dict) -> tuple[int, list[str]]:
    """Use the same six business fields for model extraction and manual updates."""
    missing = []
    for field, _ in _OPPORTUNITY_FIELDS:
        value = values.get(field)
        if not isinstance(value, str) or not value.strip() or value.strip() == "未识别":
            missing.append(field)
    return round((len(_OPPORTUNITY_FIELDS) - len(missing)) / len(_OPPORTUNITY_FIELDS) * 100), missing


def _save_opportunity_fields(conn, row, payload: OpportunityUpdate, now: str) -> None:
    values = {field: row[column] for field, column in _OPPORTUNITY_FIELDS}
    updates = []
    params = []
    for field, column in _OPPORTUNITY_FIELDS:
        value = getattr(payload, field)
        if value is not None:
            updates.append(f"{column} = ?")
            params.append(value)
            values[field] = value
    if updates:
        completeness, missing = calculate_opportunity_completeness(values)
        updates.extend(["completeness_score = ?", "missing_fields = ?", "updated_at = ?"])
        params.extend([completeness, ",".join(missing), now, row["id"]])
        conn.execute(f"UPDATE project_opportunities SET {', '.join(updates)} WHERE id = ?", params)


_OPP_COLS = "id, match_record_id, requirement_text, customer_name, project_name, industry, region, project_stage, business_needs, technical_needs, delivery_needs, qualification_requirements, case_requirements, onsite_requirement, timeline_requirement, cloud_platform_preference, matched_capability_tags, unmatched_capability_signals, recommended_partner_names, supply_status, completeness_score, missing_fields, follow_up_questions, created_at, updated_at"


def _opp_to_out(r) -> OpportunityOut:
    return OpportunityOut(
        id=r["id"], matchRecordId=r["match_record_id"], requirementText=r["requirement_text"],
        customerName=r["customer_name"], projectName=r["project_name"], industry=r["industry"],
        region=r["region"], projectStage=r["project_stage"], businessNeeds=r["business_needs"],
        technicalNeeds=r["technical_needs"], deliveryNeeds=r["delivery_needs"],
        qualificationRequirements=r["qualification_requirements"], caseRequirements=r["case_requirements"],
        onsiteRequirement=r["onsite_requirement"], timelineRequirement=r["timeline_requirement"],
        cloudPlatformPreference=r["cloud_platform_preference"],
        matchedCapabilityTags=r["matched_capability_tags"], unmatchedCapabilitySignals=r["unmatched_capability_signals"],
        recommendedPartnerNames=r["recommended_partner_names"], supplyStatus=r["supply_status"],
        completenessScore=r["completeness_score"] or 0, missingFields=r["missing_fields"],
        followUpQuestions=r["follow_up_questions"], createdAt=r["created_at"], updatedAt=r["updated_at"]
    )


@admin_router.get("/opportunities", response_model=list[OpportunityOut])
def list_opportunities(keyword: str | None = None, industry: str | None = None, region: str | None = None, stage: str | None = None, supplyStatus: str | None = None):
    with get_db() as conn:
        q = f"SELECT {_OPP_COLS} FROM project_opportunities"
        conditions = ["(match_record_id IS NULL OR match_record_id IN (SELECT id FROM match_records WHERE archived_at IS NULL))"]
        params = []
        if keyword:
            conditions.append("(project_name LIKE ? OR customer_name LIKE ? OR requirement_text LIKE ?)")
            params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
        if industry:
            conditions.append("industry LIKE ?"); params.append(f"%{industry}%")
        if region:
            conditions.append("region LIKE ?"); params.append(f"%{region}%")
        if stage:
            conditions.append("project_stage LIKE ?"); params.append(f"%{stage}%")
        if supplyStatus:
            conditions.append("supply_status = ?"); params.append(supplyStatus)
        if conditions:
            q += " WHERE " + " AND ".join(conditions)
        q += " ORDER BY created_at DESC"
        rows = conn.execute(q, params).fetchall()
    return [_opp_to_out(r) for r in rows]


@admin_router.get("/opportunities/{opp_id}", response_model=OpportunityOut)
def get_opportunity(opp_id: str) -> OpportunityOut:
    with get_db() as conn:
        row = conn.execute(f"SELECT {_OPP_COLS} FROM project_opportunities WHERE id = ?", (opp_id,)).fetchone()
    if row is None:
        from fastapi import HTTPException, status as _st
        raise HTTPException(_st.HTTP_404_NOT_FOUND, detail="项目机会不存在")
    return _opp_to_out(row)


@admin_router.put("/opportunities/{opp_id}", response_model=OpportunityOut)
def update_opportunity(opp_id: str, payload: OpportunityUpdate) -> OpportunityOut:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(f"SELECT {_OPP_COLS} FROM project_opportunities WHERE id = ?", (opp_id,)).fetchone()
        if row is None:
            from fastapi import HTTPException, status as _st
            raise HTTPException(_st.HTTP_404_NOT_FOUND, detail="项目机会不存在")
        _save_opportunity_fields(conn, row, payload, now)
        row = conn.execute(f"SELECT {_OPP_COLS} FROM project_opportunities WHERE id = ?", (opp_id,)).fetchone()
    return _opp_to_out(row)


@router.patch("/tasks/{record_id}/opportunity", response_model=OpportunityOut)
def update_own_opportunity(record_id: str, payload: OpportunityUpdate, user: dict = Depends(require_active_user)) -> OpportunityOut:
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        task = conn.execute("SELECT owner_user_id FROM match_records WHERE id = ?", (record_id,)).fetchone()
        if task is None or (task["owner_user_id"] != user["id"] and user["role"] != "admin"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="任务不存在")
        row = conn.execute(f"SELECT {_OPP_COLS} FROM project_opportunities WHERE match_record_id = ? ORDER BY created_at DESC LIMIT 1", (record_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="项目机会不存在")
        _save_opportunity_fields(conn, row, payload, now)
        fresh = conn.execute(f"SELECT {_OPP_COLS} FROM project_opportunities WHERE id = ?", (row["id"],)).fetchone()
    return _opp_to_out(fresh)
