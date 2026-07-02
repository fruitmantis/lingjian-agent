"""LLM-based partner matching router with match record history."""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..ai_client import chat_completion
from ..database import get_db


router = APIRouter(prefix="/agent", tags=["agent"])

_P_COLS = "id, name, intro, capabilities, service_areas, industries, ai_profile, created_at"
_CASE_COLS = "id, partner_id, title, description, created_at"


def _to_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val)


class MatchRequest(BaseModel):
    requirement: str = Field(..., min_length=1, description="项目需求描述")


class PartnerRecommendation(BaseModel):
    partnerId: str
    partnerName: str
    matchScore: str
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
    recordId: str | None = None


class MatchRecordSummary(BaseModel):
    id: str
    requirement: str
    topPartner: str
    partnerCount: int
    createdAt: str


class MatchRecordDetail(BaseModel):
    id: str
    requirement: str
    recommendations: list[PartnerRecommendation]
    createdAt: str
    createdBy: str | None


@router.get("/match-records", response_model=list[MatchRecordSummary])
def list_match_records() -> list[MatchRecordSummary]:
    with get_db() as conn:
        rows = conn.execute("SELECT id, requirement, recommendations_json, created_at FROM match_records ORDER BY created_at DESC LIMIT 20").fetchall()
    result = []
    for r in rows:
        recs = json.loads(r["recommendations_json"])
        top = recs[0]["partnerName"] if recs else "无"
        result.append(MatchRecordSummary(id=r["id"], requirement=r["requirement"], topPartner=top, partnerCount=len(recs), createdAt=r["created_at"]))
    return result


@router.get("/match-records/{record_id}", response_model=MatchRecordDetail)
def get_match_record(record_id: str) -> MatchRecordDetail:
    with get_db() as conn:
        row = conn.execute("SELECT id, requirement, recommendations_json, created_at, created_by FROM match_records WHERE id = ?", (record_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="记录不存在")
    recs = json.loads(row["recommendations_json"])
    return MatchRecordDetail(id=row["id"], requirement=row["requirement"], recommendations=recs, createdAt=row["created_at"], createdBy=row["created_by"])


@router.post("/match", response_model=MatchResponse)
def match_partners(req: MatchRequest) -> MatchResponse:
    with get_db() as conn:
        partners = conn.execute(f"SELECT {_P_COLS} FROM partners").fetchall()
        if not partners:
            return MatchResponse(requirement=req.requirement, recommendations=[])

        partner_cases: dict[str, list] = {}
        partner_deliv_counts: dict[str, int] = {}
        for p in partners:
            pid = p["id"]
            cases = conn.execute(f"SELECT {_CASE_COLS} FROM cases WHERE partner_id = ?", (pid,)).fetchall()
            partner_cases[pid] = [dict(c) for c in cases]
            deliv_count = conn.execute(
                "SELECT COUNT(*) as cnt FROM deliverables WHERE case_id IN (SELECT id FROM cases WHERE partner_id = ?)",
                (pid,),
            ).fetchone()["cnt"]
            partner_deliv_counts[pid] = deliv_count

    partner_summaries = []
    for p in partners:
        pd = dict(p)
        cases = partner_cases.get(pd["id"], [])
        deliv_count = partner_deliv_counts.get(pd["id"], 0)
        case_text = "; ".join(f"{c['title']}({c.get('description') or ''})" for c in cases) or "无案例"
        summary = (
            f"[伙伴ID: {pd['id']}] 名称: {pd['name']}, "
            f"能力标签: {pd.get('capabilities') or '未提供'}, "
            f"覆盖区域: {pd.get('service_areas') or '未提供'}, "
            f"行业经验: {pd.get('industries') or '未提供'}, "
            f"案例数: {len(cases)}, 交付物数: {deliv_count}, "
            f"案例: {case_text}, "
            f"AI画像: {'已生成' if pd.get('ai_profile') else '未生成'}"
        )
        partner_summaries.append(summary)

    context = "\n".join(partner_summaries)

    messages = [
        {
            "role": "system",
            "content": (
                "你是交付伙伴匹配专家。根据用户的项目需求，从候选伙伴中推荐最合适的伙伴。"
                "请对每个伙伴给出以下信息，严格基于已有资料，不要编造：\n"
                "1. matchScore: 匹配评分(0-100数字)\n"
                "2. matchedCapabilities: 匹配的能力标签\n"
                "3. matchedIndustries: 匹配的行业经验\n"
                "4. matchedRegions: 匹配的覆盖区域\n"
                "5. recommendationReason: 推荐理由\n"
                "6. evidenceCases: 支撑案例\n"
                "7. evidenceDeliverables: 支撑交付物\n"
                "8. riskNotes: 风险或缺口提示\n\n"
                "请以JSON数组格式返回，每个元素包含 partnerId, partnerName, matchScore, "
                "matchedCapabilities, matchedIndustries, matchedRegions, recommendationReason, "
                "evidenceCases, evidenceDeliverables, riskNotes。所有值必须是字符串。只返回JSON。"
            ),
        },
        {
            "role": "user",
            "content": f"项目需求: {req.requirement}\n\n候选伙伴:\n{context}",
        },
    ]

    try:
        raw = chat_completion(messages, timeout=90)
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"LLM 调用失败: {e}")

    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()
        if clean.startswith("json"):
            clean = clean[4:].strip()
        items = json.loads(clean)
        recs = [
            PartnerRecommendation(
                partnerId=str(item.get("partnerId", item.get("partner_id", ""))),
                partnerName=str(item.get("partnerName", item.get("partner_name", ""))),
                matchScore=_to_str(item.get("matchScore", item.get("match_score", ""))),
                matchedCapabilities=_to_str(item.get("matchedCapabilities", item.get("matched_capabilities", ""))),
                matchedIndustries=_to_str(item.get("matchedIndustries", item.get("matched_industries", ""))),
                matchedRegions=_to_str(item.get("matchedRegions", item.get("matched_regions", ""))),
                recommendationReason=_to_str(item.get("recommendationReason", item.get("recommendation_reason", ""))),
                evidenceCases=_to_str(item.get("evidenceCases", item.get("evidence_cases", ""))),
                evidenceDeliverables=_to_str(item.get("evidenceDeliverables", item.get("evidence_deliverables", ""))),
                riskNotes=_to_str(item.get("riskNotes", item.get("risk_notes", ""))),
            )
            for item in items
        ]
    except (json.JSONDecodeError, KeyError) as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"LLM 返回解析失败: {e}, 原始内容: {raw[:500]}")

    # Sort by matchScore descending (handle string scores)
    def _score_key(r: PartnerRecommendation) -> int:
        try:
            return int(r.matchScore)
        except (ValueError, TypeError):
            return 0
    recs.sort(key=_score_key, reverse=True)

    # Save match record
    record_id = str(uuid.uuid4())
    record_json = json.dumps([r.model_dump() for r in recs], ensure_ascii=False)
    now = datetime.now(timezone.utc).isoformat()
    try:
        with get_db() as conn:
            conn.execute("INSERT INTO match_records (id, requirement, recommendations_json, created_at, created_by) VALUES (?, ?, ?, ?, ?)", (record_id, req.requirement, record_json, now, "admin"))
    except Exception:
        pass  # Save failure doesn't affect response

    # Auto-generate demand profile
    try:
        _generate_demand_profile(record_id, req.requirement, recs, now)
    except Exception:
        pass  # Profile generation failure doesn't affect response

    return MatchResponse(requirement=req.requirement, recommendations=recs, recordId=record_id)


def _generate_demand_profile(match_record_id: str, requirement: str, recs: list[PartnerRecommendation], created_at: str):
    """Generate demand profile using LLM, with fallback to rule-based extraction."""
    partner_count = len(recs)
    top_names = ", ".join(r.partnerName for r in recs[:3])

    # Rule-based supply status
    if partner_count == 0:
        supply_status = "gap"
    elif partner_count <= 2:
        supply_status = "partial"
    else:
        supply_status = "sufficient"

    # Try LLM classification
    industry_tags = ""
    capability_tags = ""
    delivery_type_tags = ""
    region_tags = ""
    complexity_level = "中"
    urgency_level = "中"
    project_keywords = ""
    gap_analysis = ""
    llm_supply_status = supply_status

    # Get enabled standard capability tags for LLM constraint
    with get_db() as conn:
        std_tags = [r["name"] for r in conn.execute("SELECT name FROM capability_tags WHERE enabled = 1").fetchall()]
    std_tags_str = ", ".join(std_tags) if std_tags else "无标准标签"

    try:
        llm_messages = [
            {"role": "system", "content": f"你是项目需求分析专家。根据项目需求文本，提取结构化标签。返回JSON含：industryTags(行业,逗号分隔), capabilityTags(能力标签，只能从以下标准标签中选择：[{std_tags_str}]，选择匹配的，逗号分隔，不允许创造新标签，无匹配则返回空字符串), deliveryTypeTags(交付类型如全栈/运维/咨询,逗号分隔), regionTags(区域,逗号分隔), complexityLevel(高/中/低), urgencyLevel(高/中/低), projectKeywords(关键词,逗号分隔), supplyStatus(sufficient/partial/gap), gapAnalysis(缺口分析一句话)。只返回JSON。"},
            {"role": "user", "content": f"项目需求: {requirement}\n推荐伙伴数: {partner_count}\n推荐伙伴: {top_names}"},
        ]
        raw = chat_completion(llm_messages, timeout=30)
        clean = raw.strip()
        if clean.startswith("```"): clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"): clean = clean[:-3]
        clean = clean.strip()
        if clean.startswith("json"): clean = clean[4:].strip()
        data = json.loads(clean)
        industry_tags = data.get("industryTags", "")
        capability_tags = data.get("capabilityTags", "")
        # Post-filter: only keep tags that exist in standard dictionary
        if capability_tags and std_tags:
            cap_list = [t.strip() for t in capability_tags.split(",") if t.strip()]
            capability_tags = ", ".join(t for t in cap_list if t in std_tags)
        delivery_type_tags = data.get("deliveryTypeTags", "")
        region_tags = data.get("regionTags", "")
        complexity_level = data.get("complexityLevel", "中")
        urgency_level = data.get("urgencyLevel", "中")
        project_keywords = data.get("projectKeywords", "")
        llm_supply_status = data.get("supplyStatus", supply_status)
        gap_analysis = data.get("gapAnalysis", "")
    except Exception:
        # Fallback: simple keyword extraction
        keywords = []
        for kw in ["Java", "Python", "AI", "数据治理", "云", "金融", "制造", "零售", "出海", "海外", "全栈", "运维", "安全", "大数据"]:
            if kw.lower() in requirement.lower():
                keywords.append(kw)
        project_keywords = ", ".join(keywords) if keywords else "未提取到关键词"
        gap_analysis = f"推荐伙伴{partner_count}个，{'供给不足' if partner_count <= 2 else '供给充足'}"
        capability_tags = ""

    profile_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO demand_profiles (id, match_record_id, requirement_text, industry_tags, capability_tags, delivery_type_tags, region_tags, complexity_level, urgency_level, project_keywords, matched_partner_count, top_partner_names, supply_status, gap_analysis, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (profile_id, match_record_id, requirement, industry_tags, capability_tags, delivery_type_tags, region_tags, complexity_level, urgency_level, project_keywords, partner_count, top_names, llm_supply_status, gap_analysis, created_at)
        )
