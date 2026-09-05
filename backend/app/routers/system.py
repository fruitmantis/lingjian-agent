"""System status monitoring router."""

import math
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..database import get_readonly_db
from ..ai_client import model_error_message
from ..model_resolver import ModelConfigurationError, resolve_model_config
from ..auth import require_admin


router = APIRouter(prefix="/admin/system", tags=["system"], dependencies=[Depends(require_admin)])


class AbnormalModule(BaseModel):
    module: str
    status: str
    message: str
    impact: str
    suggestion: str


class StatusSummary(BaseModel):
    normalCount: int
    warningCount: int
    errorCount: int
    unknownCount: int
    abnormalModules: list[AbnormalModule]


class ServiceStatus(BaseModel):
    name: str
    status: str  # normal / warning / error / unknown
    message: str
    detail: str | None = None


class SystemStatusResponse(BaseModel):
    overallStatus: str  # normal / partial / error / unknown
    checkedAt: str
    summary: StatusSummary
    services: list[ServiceStatus]
    database: list[ServiceStatus]
    llm: list[ServiceStatus]
    businessCapabilities: list[ServiceStatus]
    recentErrors: list[str]


def _check_services() -> list[ServiceStatus]:
    return [
        ServiceStatus(name="后端服务", status="normal", message="本次请求已响应"),
        ServiceStatus(name="API 连通性", status="normal", message="管理状态接口可访问"),
        ServiceStatus(name="前端访问", status="unknown", message="未执行独立可用性探测"),
        ServiceStatus(name="健康检查", status="unknown", message="未执行独立健康探测"),
    ]


def _check_database() -> tuple[list[ServiceStatus], bool]:
    try:
        with get_readonly_db() as conn:
            conn.execute("SELECT id FROM partners LIMIT 1").fetchone()
        return [
            ServiceStatus(name="数据库连接", status="normal", message="只读查询成功"),
            ServiceStatus(name="数据库写入", status="unknown", message="本页不执行写入测试"),
        ], False
    except Exception:
        return [
            ServiceStatus(name="数据库连接", status="error", message="数据库读取失败，请检查存储与访问权限"),
            ServiceStatus(name="数据库写入", status="unknown", message="本页不执行写入测试"),
        ], True


def _safe_endpoint(base_url: str) -> str | None:
    try:
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        return f"{parsed.scheme}://{host}" + (f":{parsed.port}" if parsed.port else "")
    except (TypeError, ValueError):
        return None


def _inspect_configuration(scene: str):
    try:
        cfg = resolve_model_config(scene, read_only=True)
    except ModelConfigurationError as exc:
        return None, model_error_message(exc)
    except Exception:
        return None, "模型配置读取失败，请管理员检查存储与配置"
    if not cfg.api_key:
        return cfg, "模型 API Key 未配置，请管理员检查模型配置"
    if not cfg.model or not _safe_endpoint(cfg.base_url):
        return cfg, "模型名称或接口地址无效，请管理员检查模型配置"
    try:
        valid_parameters = (math.isfinite(cfg.temperature) and cfg.temperature >= 0
                            and math.isfinite(cfg.top_p) and 0 <= cfg.top_p <= 1
                            and isinstance(cfg.max_tokens, int) and cfg.max_tokens > 0
                            and isinstance(cfg.timeout_seconds, int) and cfg.timeout_seconds > 0)
    except (TypeError, ValueError, OverflowError):
        valid_parameters = False
    if not valid_parameters:
        return cfg, "模型参数无效，请管理员检查模型配置"
    return cfg, ""


def _check_llm() -> tuple[list[ServiceStatus], bool, str]:
    cfg, error_msg = _inspect_configuration("default")
    if cfg is None:
        return [ServiceStatus(name="模型配置", status="error", message=error_msg)], True, error_msg
    source = "数据库配置" if cfg.source == "db" else "环境变量配置"
    items = [
        ServiceStatus(name="API Key", status="normal" if cfg.api_key else "error", message="已配置" if cfg.api_key else "未配置"),
        ServiceStatus(name="当前模型", status="normal" if cfg.model else "error", message=f"{cfg.model or '未配置'}（{source}）"),
        ServiceStatus(name="模型接口地址", status="normal" if _safe_endpoint(cfg.base_url) else "error", message=_safe_endpoint(cfg.base_url) or "地址无效"),
        ServiceStatus(name="模型配置", status="error" if error_msg else "normal", message=error_msg or "基础配置已具备，实际调用尚未验证"),
        ServiceStatus(name="模型调用状态", status="unknown", message="本页不调用模型；可在模型配置页手动测试连接"),
        ServiceStatus(name="最近调用耗时", status="unknown", message="未采集调用耗时"),
        ServiceStatus(name="最近错误信息", status="unknown", message="未采集模型调用日志"),
    ]
    return items, bool(error_msg), error_msg


def _check_business() -> tuple[list[ServiceStatus], list[AbnormalModule]]:
    items = []
    abnormals = []
    for scene, name in (("partner_profile", "伙伴画像生成"), ("partner_match", "智能匹配"),
                        ("demand_profile", "需求画像与项目机会"), ("tag_suggestion", "标签建议")):
        _, error_msg = _inspect_configuration(scene)
        items.append(ServiceStatus(
            name=name, status="error" if error_msg else "unknown",
            message=error_msg or "场景配置已具备，实际调用尚未验证",
        ))
        if error_msg:
            abnormals.append(AbnormalModule(
                module=name, status="error", message=error_msg,
                impact=f"可能影响{name}", suggestion="请在模型配置页检查该业务场景绑定及模型参数",
            ))
    return items, abnormals


@router.get("/status", response_model=SystemStatusResponse)
def get_system_status() -> SystemStatusResponse:
    now = datetime.now(timezone.utc).isoformat()

    services = _check_services()
    db_items, db_error = _check_database()
    llm_items, llm_error, llm_err_msg = _check_llm()
    biz_items, biz_abnormals = _check_business()

    # Collect all abnormals
    all_abnormals = list(biz_abnormals)
    if db_error:
        all_abnormals.append(AbnormalModule(
            module="数据库", status="error", message="数据库连接异常",
            impact="可能影响伙伴资料、标签配置、匹配历史读取",
            suggestion="请检查数据库连接"
        ))
    if llm_error:
        all_abnormals.append(AbnormalModule(
            module="LLM 模型", status="error", message=llm_err_msg or "LLM 服务异常",
            impact="可能影响 AI 画像生成、智能匹配和需求画像生成",
            suggestion="请检查模型 API Key 和模型接口配置"
        ))

    # Count statuses
    all_items = services + db_items + llm_items + biz_items
    normal_count = sum(1 for i in all_items if i.status == "normal")
    warning_count = sum(1 for i in all_items if i.status == "warning")
    error_count = sum(1 for i in all_items if i.status == "error")
    unknown_count = sum(1 for i in all_items if i.status == "unknown")

    # Determine overall status
    if db_error:
        overall = "error"
    elif error_count or warning_count:
        overall = "partial"
    elif unknown_count:
        overall = "unknown"
    else:
        overall = "normal"

    return SystemStatusResponse(
        overallStatus=overall,
        checkedAt=now,
        summary=StatusSummary(
            normalCount=normal_count,
            warningCount=warning_count,
            errorCount=error_count,
            unknownCount=unknown_count,
            abnormalModules=all_abnormals[:5],
        ),
        services=services,
        database=db_items,
        llm=llm_items,
        businessCapabilities=biz_items,
        recentErrors=[a.message for a in all_abnormals[:3]],
    )
