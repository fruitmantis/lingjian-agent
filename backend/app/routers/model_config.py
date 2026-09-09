"""Model configuration CRUD router."""

import uuid
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..database import get_db
from ..auth import require_admin
from ..model_resolver import _resolve_api_key
from ..ai_client import _completion_content, model_error_message


router = APIRouter(prefix="/admin/model-configs", tags=["model-configs"], dependencies=[Depends(require_admin)])

_MC_COLS = "id, name, provider, base_url, api_key, api_key_source, api_key_env_name, model_name, temperature, top_p, max_tokens, timeout_seconds, enabled, is_default, created_at, updated_at"


class ModelConfigOut(BaseModel):
    id: str
    name: str
    provider: str | None
    baseUrl: str | None
    apiKeyConfigured: bool
    apiKeySource: str | None
    modelName: str | None
    temperature: float
    topP: float
    maxTokens: int
    timeoutSeconds: int
    enabled: bool
    isDefault: bool
    createdAt: str
    updatedAt: str


class ModelConfigCreate(BaseModel):
    name: str
    provider: str = "OpenAI Compatible"
    baseUrl: str | None = None
    apiKey: str | None = None
    modelName: str | None = None
    temperature: float = Field(default=0.3, ge=0, allow_inf_nan=False)
    topP: float = Field(default=1.0, ge=0, le=1, allow_inf_nan=False)
    maxTokens: int = Field(default=131072, gt=0)
    timeoutSeconds: int = Field(default=60, gt=0)


class ModelConfigUpdate(BaseModel):
    name: str | None = None
    provider: str | None = None
    baseUrl: str | None = None
    apiKey: str | None = None
    modelName: str | None = None
    temperature: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    topP: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    maxTokens: int | None = Field(default=None, gt=0)
    timeoutSeconds: int | None = Field(default=None, gt=0)


class UsageConfigOut(BaseModel):
    sceneKey: str
    sceneName: str
    modelConfigId: str | None
    modelConfigName: str | None
    description: str | None


class UsageConfigUpdate(BaseModel):
    modelConfigId: str | None = None


class TestResult(BaseModel):
    success: bool
    message: str
    latencyMs: int | None = None


def _to_out(r) -> ModelConfigOut:
    return ModelConfigOut(
        id=r["id"], name=r["name"], provider=r["provider"], baseUrl=r["base_url"],
        apiKeyConfigured=bool(_resolve_api_key(r)),
        apiKeySource=r["api_key_source"], modelName=r["model_name"],
        temperature=r["temperature"], topP=r["top_p"], maxTokens=r["max_tokens"],
        timeoutSeconds=r["timeout_seconds"], enabled=bool(r["enabled"]), isDefault=bool(r["is_default"]),
        createdAt=r["created_at"], updatedAt=r["updated_at"]
    )


@router.get("", response_model=list[ModelConfigOut])
def list_configs():
    with get_db() as conn:
        rows = conn.execute(f"SELECT {_MC_COLS} FROM model_configs ORDER BY is_default DESC, created_at ASC").fetchall()
    return [_to_out(r) for r in rows]


@router.post("", response_model=ModelConfigOut, status_code=status.HTTP_201_CREATED)
def create_config(payload: ModelConfigCreate) -> ModelConfigOut:
    now = datetime.now(timezone.utc).isoformat()
    mc_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO model_configs (id, name, provider, base_url, api_key, api_key_source, api_key_env_name, model_name, temperature, top_p, max_tokens, timeout_seconds, enabled, is_default, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'db', 'LLM_API_KEY', ?, ?, ?, ?, ?, 1, 0, ?, ?)",
            (mc_id, payload.name, payload.provider, payload.baseUrl, payload.apiKey, payload.modelName, payload.temperature, payload.topP, payload.maxTokens, payload.timeoutSeconds, now, now)
        )
        row = conn.execute(f"SELECT {_MC_COLS} FROM model_configs WHERE id = ?", (mc_id,)).fetchone()
    return _to_out(row)


@router.put("/{mc_id}", response_model=ModelConfigOut)
def update_config(mc_id: str, payload: ModelConfigUpdate) -> ModelConfigOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute(f"SELECT {_MC_COLS} FROM model_configs WHERE id = ?", (mc_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="配置不存在")
        updates = []
        params = []
        if payload.name is not None:
            updates.append("name = ?"); params.append(payload.name)
        if payload.provider is not None:
            updates.append("provider = ?"); params.append(payload.provider)
        if payload.baseUrl is not None:
            updates.append("base_url = ?"); params.append(payload.baseUrl)
        if payload.modelName is not None:
            updates.append("model_name = ?"); params.append(payload.modelName)
        if payload.temperature is not None:
            updates.append("temperature = ?"); params.append(payload.temperature)
        if payload.topP is not None:
            updates.append("top_p = ?"); params.append(payload.topP)
        if payload.maxTokens is not None:
            updates.append("max_tokens = ?"); params.append(payload.maxTokens)
        if payload.timeoutSeconds is not None:
            updates.append("timeout_seconds = ?"); params.append(payload.timeoutSeconds)
        # Only update api_key if explicitly provided and non-empty
        if payload.apiKey is not None and payload.apiKey.strip():
            updates.append("api_key = ?"); params.append(payload.apiKey)
            updates.append("api_key_source = 'db'"); 
        updates.append("updated_at = ?"); params.append(now)
        params.append(mc_id)
        if len(updates) > 1:
            conn.execute(f"UPDATE model_configs SET {', '.join(updates)} WHERE id = ?", params)
        row = conn.execute(f"SELECT {_MC_COLS} FROM model_configs WHERE id = ?", (mc_id,)).fetchone()
    return _to_out(row)


@router.patch("/{mc_id}/enable", response_model=ModelConfigOut)
def toggle_enable(mc_id: str, enabled: bool = True) -> ModelConfigOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute(f"SELECT {_MC_COLS} FROM model_configs WHERE id = ?", (mc_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="配置不存在")
        conn.execute("UPDATE model_configs SET enabled = ?, updated_at = ? WHERE id = ?", (1 if enabled else 0, now, mc_id))
        row = conn.execute(f"SELECT {_MC_COLS} FROM model_configs WHERE id = ?", (mc_id,)).fetchone()
    return _to_out(row)


@router.patch("/{mc_id}/default", response_model=ModelConfigOut)
def set_default(mc_id: str) -> ModelConfigOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute(f"SELECT {_MC_COLS} FROM model_configs WHERE id = ? AND enabled = 1", (mc_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="配置不存在或已停用，无法设为默认")
        conn.execute("UPDATE model_configs SET is_default = 0")
        conn.execute("UPDATE model_configs SET is_default = 1, updated_at = ? WHERE id = ?", (now, mc_id))
        row = conn.execute(f"SELECT {_MC_COLS} FROM model_configs WHERE id = ?", (mc_id,)).fetchone()
    return _to_out(row)


@router.post("/{mc_id}/test", response_model=TestResult)
def test_connection(mc_id: str) -> TestResult:
    with get_db() as conn:
        row = conn.execute(f"SELECT {_MC_COLS} FROM model_configs WHERE id = ?", (mc_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="配置不存在")

    import os
    api_key = _resolve_api_key(row)
    base_url = row["base_url"] or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    model = row["model_name"] or os.getenv("LLM_MODEL", "gpt-4o")

    if not api_key:
        return TestResult(success=False, message="API Key 未配置")

    try:
        start = time.time()
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        from ..ai_client import provider_request_options
        payload = {"model": model, "messages": [{"role": "user", "content": "只回复ok"}], "temperature": 0, "max_tokens": 10}
        payload.update(provider_request_options(base_url, model))
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            _completion_content(resp.json())
        elapsed = int((time.time() - start) * 1000)
        return TestResult(success=True, message="连接成功", latencyMs=elapsed)
    except Exception as e:
        return TestResult(success=False, message=model_error_message(e))


# ============ Usage Configs ============

@router.get("/usage", response_model=list[UsageConfigOut])
def list_usage_configs():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT muc.scene_key, muc.scene_name, muc.model_config_id, muc.description,
                   mc.name as model_config_name
            FROM model_usage_configs muc
            LEFT JOIN model_configs mc ON muc.model_config_id = mc.id
            ORDER BY muc.scene_key
        """).fetchall()
    return [UsageConfigOut(
        sceneKey=r["scene_key"], sceneName=r["scene_name"],
        modelConfigId=r["model_config_id"], modelConfigName=r["model_config_name"],
        description=r["description"]
    ) for r in rows]


@router.put("/usage/{scene_key}", response_model=UsageConfigOut)
def update_usage_config(scene_key: str, payload: UsageConfigUpdate) -> UsageConfigOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM model_usage_configs WHERE scene_key = ?", (scene_key,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="场景不存在")
        if payload.modelConfigId is not None:
            config = conn.execute(
                "SELECT id FROM model_configs WHERE id = ? AND enabled = 1", (payload.modelConfigId,),
            ).fetchone()
            if config is None:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="绑定失败：模型配置不存在或已停用")
        conn.execute("UPDATE model_usage_configs SET model_config_id = ?, updated_at = ? WHERE scene_key = ?",
                     (payload.modelConfigId, now, scene_key))
        row = conn.execute("""
            SELECT muc.scene_key, muc.scene_name, muc.model_config_id, muc.description,
                   mc.name as model_config_name
            FROM model_usage_configs muc
            LEFT JOIN model_configs mc ON muc.model_config_id = mc.id
            WHERE muc.scene_key = ?
        """, (scene_key,)).fetchone()
    return UsageConfigOut(
        sceneKey=row["scene_key"], sceneName=row["scene_name"],
        modelConfigId=row["model_config_id"], modelConfigName=row["model_config_name"],
        description=row["description"]
    )
