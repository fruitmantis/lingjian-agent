"""AI profile generation and partner profile listing router."""

import json
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

@router.post("/{partner_id}/profile", response_model=ProfileOut, dependencies=[Depends(require_auth)])
def generate_profile(partner_id: str) -> ProfileOut:
    with get_db() as conn:
        partner = conn.execute(f"SELECT {_P_COLS} FROM partners WHERE id = ?", (partner_id,)).fetchone()
        if partner is None: raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Partner not found")
        cases = conn.execute(f"SELECT {_CASE_COLS} FROM cases WHERE partner_id = ?", (partner_id,)).fetchall()
        docs = conn.execute(f"SELECT {_DOC_COLS} FROM partner_documents WHERE partner_id = ?", (partner_id,)).fetchall()
    p = dict(partner)
    parts = [f"伙伴名称: {p['name']}"]
    case_list = [dict(c) for c in cases]
    if case_list: parts.append("项目案例:\n" + "\n".join(f"- {c['title']}: {c.get('description') or '无描述'}" for c in case_list))
    else: parts.append("项目案例: 暂无")
    doc_list = [dict(d) for d in docs]
    if doc_list:
        doc_text_parts = []
        for d in doc_list:
            text = (d.get('extracted_text') or '').strip()
            if text: doc_text_parts.append(f"=== 文档: {d['filename']} ===\n{text[:5000]}")
        if doc_text_parts: parts.append("上传文档内容:\n" + "\n\n".join(doc_text_parts))
        else: parts.append("上传文档: 有文档但未提取到文本内容")
    else: parts.append("上传文档: 暂无")
    context = "\n".join(parts)
    # Get enabled standard capability tags for LLM constraint
    with get_db() as conn:
        std_tags = [r["name"] for r in conn.execute("SELECT name FROM capability_tags WHERE enabled = 1").fetchall()]
    std_tags_str = ", ".join(std_tags) if std_tags else "无标准标签"

    try:
        struct_raw = chat_completion([
            {"role": "system", "content": f"根据资料提取结构化标签。返回JSON含三个字段：capabilities(能力标签，只能从以下标准标签中选择：[{std_tags_str}]，选择3-4个匹配的，逗号分隔，不允许创造新标签，无匹配则返回空字符串)，service_areas(覆盖区域，3-4个，每个不超过10字，逗号分隔)，industries(行业经验，3-4个，每个不超过10字，逗号分隔)。只返回JSON。"},
            {"role": "user", "content": context}
        ], timeout=60)
        clean = struct_raw.strip()
        if clean.startswith("```"): clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"): clean = clean[:-3]
        clean = clean.strip()
        if clean.startswith("json"): clean = clean[4:].strip()
        sd = json.loads(clean)
        capabilities = sd.get("capabilities", "")
        # Post-filter: only keep tags that exist in standard dictionary
        if capabilities and std_tags:
            cap_list = [t.strip() for t in capabilities.split(",") if t.strip()]
            capabilities = ", ".join(t for t in cap_list if t in std_tags)
        service_areas = sd.get("service_areas", "")
        industries = sd.get("industries", "")
    except Exception:
        capabilities = None; service_areas = None; industries = None
    try:
        ai_profile = chat_completion([
            {"role": "system", "content": "你是交付伙伴能力分析专家。根据资料和文档生成能力画像摘要：优势领域、核心技术能力、行业经验总结、交付能力评估、潜在风险或缺口。用中文分点描述，不编造，证据不足时说明。"},
            {"role": "user", "content": context}
        ], timeout=90)
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"LLM 调用失败: {e}")
    with get_db() as conn:
        conn.execute("UPDATE partners SET ai_profile=?, capabilities=?, service_areas=?, industries=? WHERE id=?", (ai_profile, capabilities, service_areas, industries, partner_id))
    return ProfileOut(partner_id=partner_id, ai_profile=ai_profile)


class BatchProfileResult(BaseModel):
    partner_id: str
    partner_name: str
    success: bool
    error: str | None = None


class BatchProfileResponse(BaseModel):
    total: int
    success: int
    failed: int
    results: list[BatchProfileResult]


@router.post("/batch-profile", response_model=BatchProfileResponse, dependencies=[Depends(require_auth)])
def batch_generate_profiles() -> BatchProfileResponse:
    """Generate AI profiles for all partners sequentially."""
    with get_db() as conn:
        partner_ids = conn.execute("SELECT id, name FROM partners ORDER BY created_at ASC").fetchall()
    
    results: list[BatchProfileResult] = []
    success_count = 0
    for p in partner_ids:
        try:
            generate_profile(p["id"])
            results.append(BatchProfileResult(partner_id=p["id"], partner_name=p["name"], success=True))
            success_count += 1
        except Exception as e:
            results.append(BatchProfileResult(partner_id=p["id"], partner_name=p["name"], success=False, error=str(e)))
    
    return BatchProfileResponse(
        total=len(partner_ids),
        success=success_count,
        failed=len(partner_ids) - success_count,
        results=results
    )
