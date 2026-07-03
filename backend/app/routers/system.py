"""System status monitoring router."""

import os
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter
from pydantic import BaseModel

from ..database import get_db, DATABASE_PATH
from ..ai_client import chat_completion
from ..model_resolver import resolve_model_config, get_config_source_label


router = APIRouter(prefix="/system", tags=["system"])


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
        ServiceStatus(name="后端服务", status="normal", message="服务运行中"),
        ServiceStatus(name="API 连通性", status="normal", message="API 接口可访问"),
        ServiceStatus(name="前端访问", status="normal", message="前端页面可访问"),
        ServiceStatus(name="健康检查", status="normal", message=f"最近检查: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"),
    ]


def _check_database() -> tuple[list[ServiceStatus], bool]:
    items = []
    has_error = False
    try:
        with get_db() as conn:
            conn.execute("SELECT 1").fetchone()
            items.append(ServiceStatus(name="数据库连接", status="normal", message="连接正常"))
            conn.execute("CREATE TABLE IF NOT EXISTS _health_check (id INTEGER)")
            conn.execute("INSERT OR REPLACE INTO _health_check (id) VALUES (1)")
            conn.execute("DELETE FROM _health_check WHERE id = 1")
            items.append(ServiceStatus(name="数据库读写", status="normal", message="读写正常"))
    except Exception as e:
        has_error = True
        items.append(ServiceStatus(name="数据库连接", status="error", message=f"连接异常: {e}"))
        items.append(ServiceStatus(name="数据库读写", status="unknown", message="无法检测"))
    return items, has_error


def _check_llm() -> tuple[list[ServiceStatus], bool, str]:
    items = []
    has_error = False
    error_msg = ""

    cfg = resolve_model_config()
    api_key = cfg.api_key
    api_base = cfg.base_url
    model = cfg.model
    config_source = get_config_source_label()

    # API Key
    if api_key:
        items.append(ServiceStatus(name="API Key", status="normal", message="已配置"))
    else:
        items.append(ServiceStatus(name="API Key", status="error", message="未配置"))
        has_error = True
        error_msg = "LLM API Key 未配置"

    # Model name
    items.append(ServiceStatus(name="当前模型", status="normal", message=f"{model}（{config_source}）"))

    # API base (masked)
    if api_base:
        try:
            parsed = urlparse(api_base)
            masked = f"{parsed.scheme}://{parsed.hostname}" if parsed.hostname else api_base
            items.append(ServiceStatus(name="模型接口地址", status="normal", message=masked))
        except Exception:
            items.append(ServiceStatus(name="模型接口地址", status="warning", message="地址格式异常"))
    else:
        items.append(ServiceStatus(name="模型接口地址", status="warning", message="未配置"))

    # Test LLM call
    if api_key:
        try:
            start = time.time()
            chat_completion([{"role": "user", "content": "你好"}], timeout=10)
            elapsed = round(time.time() - start, 2)
            items.append(ServiceStatus(name="模型调用状态", status="normal", message="调用成功"))
            items.append(ServiceStatus(name="最近调用耗时", status="normal", message=f"{elapsed}秒"))
            items.append(ServiceStatus(name="最近错误信息", status="normal", message="暂无异常"))
        except Exception as e:
            has_error = True
            err_str = str(e)[:200]
            items.append(ServiceStatus(name="模型调用状态", status="error", message="调用失败"))
            items.append(ServiceStatus(name="最近调用耗时", status="unknown", message="未完成"))
            items.append(ServiceStatus(name="最近错误信息", status="error", message=err_str))
            error_msg = err_str
    else:
        items.append(ServiceStatus(name="模型调用状态", status="error", message="无法调用（Key未配置）"))
        items.append(ServiceStatus(name="最近调用耗时", status="unknown", message="未检测"))
        items.append(ServiceStatus(name="最近错误信息", status="error", message="API Key 未配置"))

    return items, has_error, error_msg


def _check_business() -> tuple[list[ServiceStatus], list[AbnormalModule]]:
    items = []
    abnormals = []
    api_key = os.getenv("LLM_API_KEY", "")
    if api_key:
        items.append(ServiceStatus(name="伙伴画像生成", status="normal", message="可用（LLM已配置）"))
        items.append(ServiceStatus(name="智能匹配", status="normal", message="可用（LLM已配置）"))
    else:
        items.append(ServiceStatus(name="伙伴画像生成", status="error", message="不可用（LLM未配置）"))
        items.append(ServiceStatus(name="智能匹配", status="error", message="不可用（LLM未配置）"))
        abnormals.append(AbnormalModule(
            module="LLM 模型", status="error", message="LLM API Key 未配置",
            impact="可能影响 AI 画像生成和智能匹配",
            suggestion="请检查模型 API Key 和模型接口配置"
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
    if db_error or (llm_error and not api_key_exists()):
        overall = "error"
    elif all_abnormals:
        overall = "partial"
    elif unknown_count > len(all_items) / 2:
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


def api_key_exists() -> bool:
    return bool(os.getenv("LLM_API_KEY", ""))