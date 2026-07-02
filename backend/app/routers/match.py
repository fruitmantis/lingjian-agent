"""LLM-based partner matching router."""

import json

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
    return MatchResponse(requirement=req.requirement, recommendations=recs)
