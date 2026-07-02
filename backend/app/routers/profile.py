"""AI profile generation and partner profile listing router."""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from ..ai_client import chat_completion
from ..auth import require_auth
from ..database import get_db

router = APIRouter(prefix="/partners", tags=["ai"])
_P_COLS = "id, name, intro, capabilities, service_areas, industries, ai_profile, created_at"
_CASE_COLS = "id, partner_id, title, description, created_at"
_DOC_COLS = "id, partner_id, filename, file_type, doc_category, extracted_text, created_at"


class ProfileOut(BaseModel):
    partner_id: str
    ai_profile: str


class PartnerProfileCard(BaseModel):
    id: str
    name: str
    capabilities: str | None
    service_areas: str | None
    industries: str | None
    ai_profile: str | None
    case_count: int
    deliverable_count: int


@router.get("/profiles", response_model=list[PartnerProfileCard], dependencies=[Depends(require_auth)])
def list_profiles() -> list[PartnerProfileCard]:
    with get_db() as conn:
        partners = conn.execute(f"SELECT {_P_COLS} FROM partners ORDER BY created_at DESC").fetchall()
        result = []
        for p in partners:
            pd = dict(p)
            case_count = conn.execute("SELECT COUNT(*) as cnt FROM cases WHERE partner_id = ?", (pd["id"],)).fetchone()["cnt"]
            deliverable_count = conn.execute("SELECT COUNT(*) as cnt FROM deliverables WHERE case_id IN (SELECT id FROM cases WHERE partner_id = ?)", (pd["id"],)).fetchone()["cnt"]
            result.append(PartnerProfileCard(id=pd["id"], name=pd["name"], capabilities=pd.get("capabilities"), service_areas=pd.get("service_areas"), industries=pd.get("industries"), ai_profile=pd.get("ai_profile"), case_count=case_count, deliverable_count=deliverable_count))
    return result


@router.post("/{partner_id}/profile", response_model=ProfileOut, dependencies=[Depends(require_auth)])
def generate_profile(partner_id: str) -> ProfileOut:
    with get_db() as conn:
        partner = conn.execute(f"SELECT {_P_COLS} FROM partners WHERE id = ?", (partner_id,)).fetchone()
        if partner is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Partner not found")
        cases = conn.execute(f"SELECT {_CASE_COLS} FROM cases WHERE partner_id = ?", (partner_id,)).fetchall()
        docs = conn.execute(f"SELECT {_DOC_COLS} FROM partner_documents WHERE partner_id = ?", (partner_id,)).fetchall()
    p = dict(partner)
    case_list = [dict(c) for c in cases]
    doc_list = [dict(d) for d in docs]
    parts = [f"伙伴名称: {p['name']}", f"简介: {p.get('intro') or '未提供'}", f"能力标签: {p.get('capabilities') or '未提供'}", f"服务区域: {p.get('service_areas') or '未提供'}", f"行业经验: {p.get('industries') or '未提供'}"]
    if case_list:
        parts.append("项目案例:\n" + "\n".join(f"- {c['title']}: {c.get('description') or '无描述'}" for c in case_list))
    else:
        parts.append("项目案例: 暂无")
    if doc_list:
        doc_text_parts = []
        for d in doc_list:
            text = (d.get('extracted_text') or '').strip()
            if text:
                doc_text_parts.append(f"=== 文档: {d['filename']} (类型:{d['file_type']}) ===\n{text[:5000]}")
        if doc_text_parts:
            parts.append("上传文档内容:\n" + "\n\n".join(doc_text_parts))
        else:
            parts.append("上传文档: 有文档但未提取到文本内容")
    else:
        parts.append("上传文档: 暂无")
    context = "\n".join(parts)
    messages = [
        {"role": "system", "content": "你是交付伙伴能力分析专家。请根据以下伙伴资料、案例和上传文档内容，生成一份能力画像摘要，包括：优势领域、核心技术能力、行业经验总结、交付能力评估、潜在风险或缺口。用简洁的中文分点描述，不要编造资料中没有的信息，证据不足时明确说明。如果上传了文档，优先从文档内容中提取和分析信息。"},
        {"role": "user", "content": context},
    ]
    try:
        ai_profile = chat_completion(messages, timeout=90)
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"LLM 调用失败: {e}")
    with get_db() as conn:
        conn.execute("UPDATE partners SET ai_profile = ? WHERE id = ?", (ai_profile, partner_id))
    return ProfileOut(partner_id=partner_id, ai_profile=ai_profile)
