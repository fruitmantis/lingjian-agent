"""AI profile generation and partner profile listing router."""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from ..ai_client import model_error_message
from ..model_resolver import ModelConfigurationError
from ..auth import require_admin
from ..database import get_db

router = APIRouter(prefix="/partners", tags=["ai"])
class ProfileOut(BaseModel):
    partner_id: str
    ai_profile: str
    profile_status: str = "ready"

@router.post("/{partner_id}/profile", response_model=ProfileOut, dependencies=[Depends(require_admin)])
def generate_profile(partner_id: str) -> ProfileOut:
    from ..profile_sources import process_partner
    with get_db() as conn:
        if not conn.execute('SELECT id FROM partners WHERE id=?',(partner_id,)).fetchone():
            raise HTTPException(404,'伙伴不存在')
    try:
        result=process_partner(partner_id)
        return ProfileOut(partner_id=partner_id, ai_profile=result['ai_profile'], profile_status=result['profile_status'])
    except ModelConfigurationError as exc:
        from ..error_diagnostics import record_error
        record_error(exc,stage='partner_profile')
        raise HTTPException(503,model_error_message(exc)) from None
    except Exception as exc:
        raise HTTPException(502,'来源贡献处理失败，请查看资料状态并重试。') from None



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


@router.post("/batch-profile", response_model=BatchProfileResponse, dependencies=[Depends(require_admin)])
def batch_generate_profiles() -> BatchProfileResponse:
    """Generate AI profiles for all partners sequentially."""
    with get_db() as conn:
        partner_ids = conn.execute("SELECT id, name FROM partners WHERE status = 'active' ORDER BY created_at ASC").fetchall()

    results: list[BatchProfileResult] = []
    success_count = 0
    for p in partner_ids:
        try:
            generate_profile(p["id"])
            results.append(BatchProfileResult(partner_id=p["id"], partner_name=p["name"], success=True))
            success_count += 1
        except Exception:
            results.append(BatchProfileResult(
                partner_id=p["id"], partner_name=p["name"], success=False,
                error="画像生成失败，请在伙伴详情中重试或检查模型配置",
            ))

    return BatchProfileResponse(
        total=len(partner_ids),
        success=success_count,
        failed=len(partner_ids) - success_count,
        results=results
    )
