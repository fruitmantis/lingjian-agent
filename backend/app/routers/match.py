"""LLM-based partner matching router with match record history."""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..ai_client import chat_completion
from ..database import get_db


router = APIRouter(prefix="/agent", tags=["agent"])

MAX_RECOMMENDATIONS = 5

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

    partner_dicts = [dict(partner) for partner in partners]

    partner_summaries = []
    for pd in partner_dicts:
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
                f"请从全部候选伙伴中最多推荐{MAX_RECOMMENDATIONS}家，不要逐一评价所有候选。"
                "严格基于已有资料，不要编造。每个推荐伙伴给出以下信息：\n"
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
                "evidenceCases, evidenceDeliverables, riskNotes。所有值必须是字符串。"
                f"数组最多包含{MAX_RECOMMENDATIONS}个元素，只返回JSON，不要输出分析过程。"
            ),
        },
        {
            "role": "user",
            "content": f"项目需求: {req.requirement}\n\n候选伙伴:\n{context}",
        },
    ]

    try:
        raw = chat_completion(messages, timeout=90, scene="partner_match")
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
        if isinstance(items, dict):
            items = items.get("recommendations")
        if not isinstance(items, list):
            raise ValueError("返回内容不是推荐数组")

        allowed_by_id = {partner["id"]: partner for partner in partner_dicts}
        allowed_by_name = {partner["name"]: partner for partner in partner_dicts}
        recs = []
        for item in items:
            if not isinstance(item, dict):
                continue
            partner_id = str(item.get("partnerId", item.get("partner_id", "")))
            partner_name = str(item.get("partnerName", item.get("partner_name", "")))
            partner = allowed_by_id.get(partner_id) or allowed_by_name.get(partner_name)
            if not partner:
                continue
            recs.append(PartnerRecommendation(
                partnerId=partner["id"],
                partnerName=partner["name"],
                matchScore=_to_str(item.get("matchScore", item.get("match_score", ""))),
                matchedCapabilities=_to_str(item.get("matchedCapabilities", item.get("matched_capabilities", ""))),
                matchedIndustries=_to_str(item.get("matchedIndustries", item.get("matched_industries", ""))),
                matchedRegions=_to_str(item.get("matchedRegions", item.get("matched_regions", ""))),
                recommendationReason=_to_str(item.get("recommendationReason", item.get("recommendation_reason", ""))),
                evidenceCases=_to_str(item.get("evidenceCases", item.get("evidence_cases", ""))),
                evidenceDeliverables=_to_str(item.get("evidenceDeliverables", item.get("evidence_deliverables", ""))),
                riskNotes=_to_str(item.get("riskNotes", item.get("risk_notes", ""))),
            ))
        if not recs:
            raise ValueError("返回内容未包含有效候选伙伴")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"LLM 返回解析失败: {e}, 原始内容: {raw[:500]}")

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

    # Auto-generate AI tag suggestions
    try:
        _generate_tag_suggestions(req.requirement, record_id)
    except Exception:
        pass  # Suggestion failure doesn't affect response

    # Auto-extract project opportunity info
    try:
        _extract_project_opportunity(req.requirement, record_id, recs)
    except Exception as e:
        print(f"[WARN] opportunity extraction failed: {e}", flush=True)

    return MatchResponse(requirement=req.requirement, recommendations=recs, recordId=record_id)


def _extract_project_opportunity(requirement: str, match_record_id: str, recommendations: list):
    try:
        from ..ai_client import chat_completion
        rec_names = ", ".join([r.partnerName for r in recommendations[:5]])
        raw = chat_completion([
            {"role": "system", "content": "从项目需求中抽取结构化项目信息。返回JSON含: customerName(客户名称),projectName(项目名称),industry(行业),region(区域),projectStage(项目阶段如需求调研/方案设计/招投标/实施交付),businessNeeds(业务诉求),technicalNeeds(技术诉求),deliveryNeeds(交付诉求),qualificationRequirements(资质要求),caseRequirements(案例要求),onsiteRequirement(驻场要求),timelineRequirement(时间要求),cloudPlatformPreference(云平台偏好),followUpQuestions(建议补充问题,数组)。无法识别的字段填'未识别'。只返回JSON。"},
            {"role": "user", "content": f"项目需求: {requirement}\n推荐伙伴: {rec_names}"}
        ], timeout=60, scene="demand_profile")
        clean = raw.strip()
        if clean.startswith("```"): clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"): clean = clean[:-3]
        clean = clean.strip()
        if clean.startswith("json"): clean = clean[4:].strip()
        if not clean:
            print("[WARN] _extract_project_opportunity: LLM returned empty", flush=True)
            return
        data = json.loads(clean)

        # Calculate completeness
        key_fields = ["customerName", "projectName", "industry", "region", "projectStage", "businessNeeds"]
        identified = sum(1 for f in key_fields if data.get(f) and data.get(f) != "未识别")
        completeness = round(identified / len(key_fields) * 100)
        missing = [f for f in key_fields if not data.get(f) or data.get(f) == "未识别"]

        # Get matched capabilities from demand profile
        with get_db() as conn:
            dp = conn.execute("SELECT capability_tags, supply_status FROM demand_profiles WHERE match_record_id = ?", (match_record_id,)).fetchone()
            cap_tags = dp["capability_tags"] if dp else ""
            supply = dp["supply_status"] if dp else ""

        now = datetime.now(timezone.utc).isoformat()
        opp_id = str(uuid.uuid4())
        with get_db() as conn:
            conn.execute(
                "INSERT INTO project_opportunities (id, match_record_id, requirement_text, customer_name, project_name, industry, region, project_stage, business_needs, technical_needs, delivery_needs, qualification_requirements, case_requirements, onsite_requirement, timeline_requirement, cloud_platform_preference, matched_capability_tags, unmatched_capability_signals, recommended_partner_ids, recommended_partner_names, supply_status, completeness_score, missing_fields, follow_up_questions, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (opp_id, match_record_id, requirement, data.get("customerName","未识别"), data.get("projectName","未识别"), data.get("industry","未识别"), data.get("region","未识别"), data.get("projectStage","未识别"), data.get("businessNeeds","未识别"), data.get("technicalNeeds","未识别"), data.get("deliveryNeeds","未识别"), data.get("qualificationRequirements","未识别"), data.get("caseRequirements","未识别"), data.get("onsiteRequirement","未识别"), data.get("timelineRequirement","未识别"), data.get("cloudPlatformPreference","未识别"), cap_tags, "", "", rec_names, supply, completeness, ",".join(missing), json.dumps(data.get("followUpQuestions",[]), ensure_ascii=False), now, now)
            )
    except Exception as e:
        print(f"[WARN] _extract_project_opportunity inner error: {e}", flush=True)


def _generate_tag_suggestions(requirement: str, match_record_id: str):
    try:
        with get_db() as conn:
            std_tags = [r["name"] for r in conn.execute("SELECT name FROM capability_tags WHERE enabled = 1").fetchall()]
            existing_sugs = {r["suggested_name"] for r in conn.execute("SELECT suggested_name FROM capability_tag_suggestions WHERE status = 'pending'").fetchall()}
        std_tags_str = ", ".join(std_tags) if std_tags else "无标准标签"
        raw = chat_completion([
            {"role": "system", "content": f"分析项目需求，找出标准能力标签无法覆盖的新能力诉求。当前标准标签：[{std_tags_str}]。如果存在未覆盖的能力诉求，返回JSON数组，每项含suggestedName,suggestedCategoryName(从:AI与智能体,云平台与迁移,数据与数据库,应用开发与现代化,运维与安全,咨询与项目管理,其他),description,evidenceText,confidence(0-1)。不要把行业/区域误判为能力标签。无新诉求返回[]。只返回JSON。"},
            {"role": "user", "content": f"项目需求: {requirement}"}
        ], timeout=30, scene="demand_profile")
        clean = raw.strip()
        if clean.startswith("```"): clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"): clean = clean[:-3]
        clean = clean.strip()
        if clean.startswith("json"): clean = clean[4:].strip()
        items = json.loads(clean)
        now = datetime.now(timezone.utc).isoformat()
        for item in items:
            name = item.get("suggestedName", "").strip()
            if not name or name in std_tags or name in existing_sugs:
                continue
            with get_db() as conn:
                existing = conn.execute("SELECT id, occurrence_count FROM capability_tag_suggestions WHERE suggested_name = ? AND status = 'pending'", (name,)).fetchone()
                if existing:
                    conn.execute("UPDATE capability_tag_suggestions SET occurrence_count = occurrence_count + 1, updated_at = ? WHERE id = ?", (now, existing["id"]))
                else:
                    conn.execute(
                        "INSERT INTO capability_tag_suggestions (id, suggested_name, suggested_category_id, suggested_category_name, description, evidence_text, source_requirement, source_match_record_id, confidence, occurrence_count, status, created_at, updated_at, adopted_at) VALUES (?,?,?,?,?,?,?,?,?,1,'pending',?,?,NULL)",
                        (str(uuid.uuid4()), name, None, item.get("suggestedCategoryName", "其他"), item.get("description", ""), item.get("evidenceText", ""), requirement, match_record_id, float(item.get("confidence", 0.5)), now, now)
                    )
            existing_sugs.add(name)
    except Exception:
        pass


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
