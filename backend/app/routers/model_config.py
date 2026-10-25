"""Model configuration CRUD router."""

import uuid
import time
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import ValidationError, BaseModel, Field, StrictBool, ConfigDict
from backend.business.common import ModelOutput

from ..database import get_db
from ..auth import require_admin, require_active_user, record_audit
from ..model_resolver import _resolve_api_key, model_endpoint_origin, ModelConfigurationError, MODEL_SELECT, model_record
from ..ai_client import ModelResponseError, model_error_message
from .. import development_model, agent_settings
from .. import model_timeout_settings
from ..model_timeout_settings import TimeoutSettings


router = APIRouter(prefix="/admin/model-configs", tags=["model-configs"], dependencies=[Depends(require_admin)])

policy_router = APIRouter(tags=["model-settings"], dependencies=[Depends(require_active_user)])


@policy_router.get('/model-timeout-settings')
def read_timeout_policy(response: Response, agent_id: str = "processing"):
    if agent_id not in ("partner_match","partner_development","processing"):raise HTTPException(422,"智能体不存在")
    response.headers['Cache-Control'] = 'no-store'
    return model_timeout_settings.get_settings(agent_id=agent_id).model_dump()


provider_router = APIRouter(prefix="/admin/model-providers", tags=["model-providers"], dependencies=[Depends(require_admin)])


def _validated_base_url(value):
    base_url = value if value is not None else os.getenv('LLM_BASE_URL', 'https://api.deepseek.com')
    base_url = base_url.strip()
    try:
        model_endpoint_origin(base_url)
    except ModelConfigurationError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from None
    return base_url


class ModelConfigOut(BaseModel):
    id: str
    name: str
    providerId: str
    providerName: str
    modelName: str | None
    temperature: float
    topP: float
    maxTokens: int
    enabled: bool
    isDefault: bool
    userSelectable: bool = False
    defaultBindings: list[str] = Field(default_factory=list)
    createdAt: str
    updatedAt: str


class ModelConfigCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    userSelectable: StrictBool = False
    enabled: StrictBool = True
    name: str = Field(min_length=1, max_length=120)
    providerId: str
    modelName: str = Field(min_length=1)
    temperature: float = Field(default=0.2, ge=0, allow_inf_nan=False)
    topP: float = Field(default=1.0, ge=0, le=1, allow_inf_nan=False)
    maxTokens: int = Field(default=131072, gt=0)


class ModelConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    userSelectable: StrictBool | None = None
    enabled: StrictBool | None = None
    name: str | None = Field(default=None,min_length=1,max_length=120)
    providerId: str | None = None
    modelName: str | None = Field(default=None,min_length=1)
    temperature: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    topP: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    maxTokens: int | None = Field(default=None, gt=0)


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


class _ConnectionProbe(ModelOutput):
    ok: StrictBool


@router.get('/timeout-settings')
def get_timeout_settings(response: Response):
    raise HTTPException(410,"请在智能体管理中配置模型和请求超时")


@router.put('/timeout-settings')
def save_timeout_settings(payload: TimeoutSettings, response: Response):
    raise HTTPException(410,"请在智能体管理中配置模型和请求超时")


def _to_out(r) -> ModelConfigOut:
    return ModelConfigOut(
        id=r["id"], name=r["name"], providerId=r["provider_id"], providerName=r["provider"], modelName=r["model_name"],
        temperature=r["temperature"], topP=r["top_p"], maxTokens=r["max_tokens"],
        enabled=bool(r["enabled"]), isDefault=bool(r["is_default"]),
        createdAt=r["created_at"], updatedAt=r["updated_at"], **agent_settings.connection_usage(r["id"])
    )


@router.get("", response_model=list[ModelConfigOut])
def list_configs():
    with get_db() as conn:
        rows = conn.execute(MODEL_SELECT + " ORDER BY m.is_default DESC, m.created_at ASC").fetchall()
    return [_to_out(r) for r in rows]


@router.post("", response_model=ModelConfigOut, status_code=status.HTTP_201_CREATED)
def create_config(payload: ModelConfigCreate) -> ModelConfigOut:
    now = datetime.now(timezone.utc).isoformat()
    mc_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.lock_writer()
        _require_provider(conn,payload.providerId)
        conn.execute("""INSERT INTO model_configs
            (id,name,provider_id,model_name,temperature,top_p,max_tokens,enabled,is_default,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,0,?,?)""",
            (mc_id,payload.name,payload.providerId,payload.modelName,payload.temperature,payload.topP,
             payload.maxTokens,int(payload.enabled),now,now))
        agent_settings.set_selectable(conn,mc_id,payload.userSelectable)
        row=model_record(conn,mc_id)
    return _to_out(row)


@router.put("/{mc_id}", response_model=ModelConfigOut)
def update_config(mc_id: str, payload: ModelConfigUpdate) -> ModelConfigOut:
    now=datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.lock_writer()
        if model_record(conn,mc_id) is None:raise HTTPException(404,"配置不存在")
        if payload.providerId is not None:_require_provider(conn,payload.providerId)
        if payload.userSelectable is not None:agent_settings.set_selectable(conn,mc_id,payload.userSelectable)
        fields={'name':'name','providerId':'provider_id','modelName':'model_name','temperature':'temperature',
                'topP':'top_p','maxTokens':'max_tokens','enabled':'enabled'}
        updates=[];params=[]
        for field,column in fields.items():
            value=getattr(payload,field)
            if value is not None:
                updates.append(column+'=?');params.append(int(value) if field=='enabled' else value)
        if updates:
            conn.execute("UPDATE model_configs SET "+','.join(updates)+",updated_at=? WHERE id=?",[*params,now,mc_id])
        row=model_record(conn,mc_id)
    return _to_out(row)


@router.delete("/{mc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config(mc_id: str, admin: dict = Depends(require_admin)) -> None:
    with get_db() as conn:
        conn.lock_writer()
        row = model_record(conn,mc_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="配置不存在")
        usages = conn.execute(
            "SELECT scene_key FROM model_usage_configs WHERE model_config_id = ? ORDER BY scene_key", (mc_id,),
        ).fetchall()
        runs = conn.execute("SELECT id, status FROM development_runs WHERE model_config_id = ? ORDER BY id", (mc_id,)).fetchall()
        # The historical model reference is provenance, not a task dependency.
        # Preserve it in the existing audit log without retaining connection secrets.
        conn.execute("UPDATE development_runs SET model_config_id = NULL WHERE model_config_id = ?", (mc_id,))
        conn.execute("UPDATE model_usage_configs SET model_config_id = NULL, updated_at = ? WHERE model_config_id = ?", (datetime.now(timezone.utc).isoformat(), mc_id))
        conn.execute("DELETE FROM model_configs WHERE id = ?", (mc_id,))
        agent_settings.set_selectable(conn,mc_id,None)
        record_audit(conn, "model_config_deleted", actor_user_id=admin["id"], summary={
            "model_config_id": mc_id, "name": row["name"], "provider": row["provider"],
            "model_name": row["model_name"], "historical_run_ids": [run["id"] for run in runs],
            "scene_keys": [usage["scene_key"] for usage in usages],
        })


@router.patch("/{mc_id}/enable", response_model=ModelConfigOut)
def toggle_enable(mc_id: str, enabled: bool = True) -> ModelConfigOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.lock_writer()
        row = model_record(conn,mc_id)
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="配置不存在")
        conn.execute("UPDATE model_configs SET enabled = ?, updated_at = ? WHERE id = ?", (1 if enabled else 0, now, mc_id))
        row = model_record(conn,mc_id)
    return _to_out(row)


@router.patch("/{mc_id}/default", response_model=ModelConfigOut)
def set_default(mc_id: str) -> ModelConfigOut:
    raise HTTPException(410,"请在智能体管理中配置模型和请求超时")


@router.post("/{mc_id}/test", response_model=TestResult)
def test_connection(mc_id: str) -> TestResult:
    with get_db() as conn:
        row = model_record(conn,mc_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="配置不存在")

    from ..error_diagnostics import bind_context, record_error
    bind_context(stage="model_test", model=row["model_name"])
    api_key = _resolve_api_key(row)
    if not api_key:
        record_error(ValueError("Model API credential is not configured"))
        return TestResult(success=False, message="API Key 未配置")

    try:
        start = time.monotonic()
        raw = development_model.completion(dict(row), [{"role": "user", "content": '请只返回 JSON：{"ok": true}。'}], _ConnectionProbe.model_json_schema())
        if not _ConnectionProbe.model_validate_json(raw).ok:
            raise ModelResponseError("Connection probe did not return ok=true")
        elapsed = int((time.monotonic() - start) * 1000)
        return TestResult(success=True, message="连接及 JSON 格式校验通过", latencyMs=elapsed)
    except Exception as e:
        record_error(e)
        message = '连接成功，但返回内容未通过校验' if isinstance(e,(ModelResponseError,ValidationError)) else model_error_message(e)
        return TestResult(success=False, message=message, latencyMs=int((time.monotonic()-start)*1000))


# ============ Usage Configs ============

@router.get("/usage", response_model=list[UsageConfigOut])
def list_usage_configs():
    raise HTTPException(410,"请在智能体管理中配置模型和请求超时")


@router.put("/usage/{scene_key}", response_model=UsageConfigOut)
def update_usage_config(scene_key: str, payload: UsageConfigUpdate) -> UsageConfigOut:
    raise HTTPException(410,"请在智能体管理中配置模型和请求超时")


class ProviderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1,max_length=120)
    baseUrl: str
    apiKey: str | None = None

class ProviderUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None,min_length=1,max_length=120)
    baseUrl: str | None = None
    apiKey: str | None = None

class ProviderOut(BaseModel):
    id: str
    name: str
    baseUrl: str | None
    protocol: str
    apiKeyConfigured: bool
    apiKeySource: str | None
    modelCount: int
    createdAt: str
    updatedAt: str

def _require_provider(conn,provider_id):
    row=conn.execute('SELECT * FROM model_providers WHERE id=?',(provider_id,)).fetchone()
    if row is None:raise HTTPException(404,"提供商不存在")
    return row

def _provider_out(conn,row):
    return ProviderOut(id=row['id'],name=row['name'],baseUrl=row['base_url'],protocol=row['protocol'],
        apiKeyConfigured=bool(_resolve_api_key(row)),apiKeySource=row['api_key_source'],
        modelCount=conn.execute('SELECT count(*) FROM model_configs WHERE provider_id=?',(row['id'],)).fetchone()[0],
        createdAt=row['created_at'],updatedAt=row['updated_at'])

@provider_router.get("",response_model=list[ProviderOut])
def list_providers():
    with get_db() as conn:
        return [_provider_out(conn,row) for row in conn.execute('SELECT * FROM model_providers ORDER BY created_at,id')]

@provider_router.post("",response_model=ProviderOut,status_code=201)
def create_provider(payload:ProviderCreate):
    base_url=_validated_base_url(payload.baseUrl)
    now=datetime.now(timezone.utc).isoformat();provider_id=str(uuid.uuid4())
    with get_db() as conn:
        conn.execute("""INSERT INTO model_providers
            (id,name,base_url,protocol,api_key,api_key_source,api_key_env_name,created_at,updated_at)
            VALUES (?,?,?,'openai_chat_completions',?,'db',NULL,?,?)""",
            (provider_id,payload.name,base_url,payload.apiKey,now,now))
        return _provider_out(conn,_require_provider(conn,provider_id))

@provider_router.put("/{provider_id}",response_model=ProviderOut)
def update_provider(provider_id:str,payload:ProviderUpdate):
    with get_db() as conn:
        conn.lock_writer();row=_require_provider(conn,provider_id)
        base_url=_validated_base_url(payload.baseUrl if payload.baseUrl is not None else row['base_url'])
        new_key=payload.apiKey if payload.apiKey is not None and payload.apiKey.strip() else None
        if payload.baseUrl is not None:
            try:previous_origin=model_endpoint_origin(row['base_url'] or os.getenv('LLM_BASE_URL','https://api.deepseek.com'))
            except ModelConfigurationError:previous_origin=None
            if (model_endpoint_origin(base_url)!=previous_origin
                    and (row['api_key'] or row['api_key_source']=='env') and new_key is None):
                raise HTTPException(422,'模型接口目标已变化，请重新填写该目标的 API Key，不能沿用旧凭据')
        updates=[];params=[]
        for field,column in [('name','name'),('baseUrl','base_url')]:
            if getattr(payload,field) is not None:
                updates.append(column+'=?');params.append(base_url if field=='baseUrl' else payload.name)
        if new_key is not None:
            updates.extend(['api_key=?',"api_key_source='db'",'api_key_env_name=NULL']);params.append(new_key)
        if updates:
            conn.execute('UPDATE model_providers SET '+','.join(updates)+',updated_at=? WHERE id=?',
                         [*params,datetime.now(timezone.utc).isoformat(),provider_id])
        return _provider_out(conn,_require_provider(conn,provider_id))

@provider_router.delete("/{provider_id}",status_code=204)
def delete_provider(provider_id:str):
    with get_db() as conn:
        conn.lock_writer();_require_provider(conn,provider_id)
        if conn.execute('SELECT count(*) FROM model_configs WHERE provider_id=?',(provider_id,)).fetchone()[0]:
            raise HTTPException(409,'请先处理所属模型，再删除提供商')
        conn.execute('DELETE FROM model_providers WHERE id=?',(provider_id,))
