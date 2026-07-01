"""Partner matching router using LLM."""

import json

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..ai_client import chat_completion
from ..database import get_db


router = APIRouter(prefix="/match", tags=["match"])

_P_COLS = "id, name, intro, capabilities, service_areas, industries, ai_profile, created_at"
_CASE_COLS = "id, partner_id, title, description, created_at"


def _to_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, list):
        return "; ".join(str(v) for v in val)
    return str(val)


class MatchRequest(BaseModel):
    requirement: str = Field(..., min_length=1, description="项目需求描述")


class PartnerRecommendation(BaseModel):
    partner_id: str
    partner_name: str
    match_score: str
    recommendation_reason: str
    supporting_cases: str
    supporting_deliverables: str
    risk_or_gap_notes: str


class MatchResponse(BaseModel):
    requirement: str
    recommendations: list[PartnerRecommendation]


@router.post("", response_model=MatchResponse)
def match_partners(req: MatchRequest) -> MatchResponse:
    with get_db() as conn:
        partners = conn.execute(f"SELECT {_P_COLS} FROM partners").fetchall()
        if not partners:
            return MatchResponse(requirement=req.requirement, recommendations=[])
        partner_cases: dict[str, list] = {}
        for p in partners:
            cases = conn.execute(f"SELECT {_CASE_COLS} FROM cases WHERE partner_id = ?", (p["id"],)).fetchall()
            partner_cases[p["id"]] = [dict(c) for c in cases]

    partner_summaries = []
    for p in partners:
        pd = dict(p)
        cases = partner_cases.get(pd["id"], [])
        case_text = "; ".join(f"{c['title']}({c.get('description') or ''})" for c in cases) or "无案例"
        summary = f"[伙伴ID: {pd['id']}] 名称: {pd['name']}, 简介: {pd.get('intro') or '未提供'}, 能力: {pd.get('capabilities') or '未提供'}, 服务区域: {pd.get('service_areas') or '未提供'}, 行业: {pd.get('industries') or '未提供'}, 案例: {case_text}, AI画像: {pd.get('ai_profile') or '未生成'}"
        partner_summaries.append(summary)

    context = "\n".join(partner_summaries)
    messages = [
        {"role": "system", "content": "你是交付伙伴匹配专家。根据用户的项目需求，从候选伙伴中推荐最合适的伙伴。请对每个伙伴给出以下信息，严格基于已有资料，不要编造：1. match_score 2. recommendation_reason 3. supporting_cases 4. supporting_deliverables 5. risk_or_gap_notes。以JSON数组格式返回，每个元素含 partner_id, partner_name, match_score, recommendation_reason, supporting_cases, supporting_deliverables, risk_or_gap_notes。所有值必须是字符串。只返回JSON。"},
        {"role": "user", "content": f"项目需求: {req.requirement}\n\n候选伙伴:\n{context}"},
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
        recs = [PartnerRecommendation(partner_id=str(item.get("partner_id","")), partner_name=str(item.get("partner_name","")), match_score=_to_str(item.get("match_score","")), recommendation_reason=_to_str(item.get("recommendation_reason","")), supporting_cases=_to_str(item.get("supporting_cases","")), supporting_deliverables=_to_str(item.get("supporting_deliverables","")), risk_or_gap_notes=_to_str(item.get("risk_or_gap_notes",""))) for item in items]
    except (json.JSONDecodeError, KeyError) as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"LLM 返回解析失败: {e}, 原始内容: {raw[:500]}")

    return MatchResponse(requirement=req.requirement, recommendations=recs)
