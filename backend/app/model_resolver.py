"""Unified model configuration resolver.

Each fixed agent and processing has one connection; runs preserve their selected options.
"""

import os
import hashlib
import json
from urllib.parse import urlsplit
from dataclasses import dataclass
from .database import get_db, get_readonly_db
from . import agent_settings


@dataclass
class ResolvedModelConfig:
    api_key: str
    base_url: str
    model: str
    temperature: float
    top_p: float
    max_tokens: int
    source: str  # "db" / "env" / "default"
    thinking: bool | None = None


class ModelConfigurationError(RuntimeError):
    """No enabled model or an invalid connection configuration."""


def _resolve_api_key(row) -> str:
    """Resolve API key: DB key > env var > empty."""
    from backend.agent_runtime.provider import PROXY_BASE
    if row and (row['base_url'] or '').rstrip('/')==PROXY_BASE:return ''
    if row and row["api_key"]:
        return row["api_key"]
    if row and row["api_key_source"] == "env" and row["api_key_env_name"]:
        return os.getenv(row["api_key_env_name"], "")
    # Fallback to default env var
    return os.getenv("LLM_API_KEY", "")


def resolve_model_record(scene: str = "default", *, read_only: bool = False, connection=None) -> dict:
    """Resolve one agent/processing connection; no scene/default override chain."""
    if connection is None:
        with (get_readonly_db() if read_only else get_db()) as conn:
            return resolve_model_record(scene, connection=conn)
    agent_id=agent_settings.owner(scene)
    frozen=agent_settings.current_execution()
    selected=frozen if frozen and frozen['agentId']==agent_id else agent_settings.execution(connection,agent_id)
    row=connection.execute('SELECT * FROM model_configs WHERE id=? AND enabled=1',(selected['modelConfigId'],)).fetchone()
    if row is None:raise ModelConfigurationError('请为该智能体选择已启用的模型连接')
    return {**dict(row),'_agent_execution':selected}


def configuration_stamp(config: dict) -> dict:
    """No credentials are persisted in task snapshots, only a configuration digest."""
    resolved = model_config_from_record(config)
    fields=vars(resolved).copy()
    if fields.get('thinking') is None:fields.pop('thinking',None)
    digest = hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
    stamp={'id': config['id'], 'fingerprint': digest}
    if config.get('_agent_execution'):stamp['agent_execution']=config['_agent_execution']
    return stamp


def pinned_configuration(stamp: dict, connection=None) -> dict:
    if connection is None:
        with get_db() as conn:
            return pinned_configuration(stamp, conn)
    row = connection.execute('SELECT * FROM model_configs WHERE id=? AND enabled=1', (stamp['id'],)).fetchone()
    if row is None:
        raise ModelConfigurationError('本次运行的模型已停用或删除，请重试以使用当前配置')
    config = dict(row)
    if stamp.get('agent_execution'):config['_agent_execution']=stamp['agent_execution']
    if configuration_stamp(config) != stamp:
        raise ModelConfigurationError('本次运行的模型参数已变化，请重试以使用当前配置')
    return config


def resolve_model_config(scene: str = "default", *, read_only: bool = False) -> ResolvedModelConfig:
    return model_config_from_record(resolve_model_record(scene, read_only=read_only))


def validate_model_retry(config: dict):
    """Do not switch providers or send another request after settings/enablement change."""
    with get_readonly_db() as conn:
        row = conn.execute('SELECT * FROM model_configs WHERE id=?', (config['id'],)).fetchone()
    current=dict(row) if row else {}
    if config.get('_agent_execution'):current['_agent_execution']=config['_agent_execution']
    if (row is None or row['enabled'] != config['enabled']
            or configuration_stamp(current) != configuration_stamp(config)):
        raise ModelConfigurationError('本次运行的模型配置已变化，请重试以使用当前配置')


def model_config_from_record(record) -> ResolvedModelConfig:
    """Use the same saved settings for text, structured output and connection tests."""
    row = dict(record)
    execution=row.get('_agent_execution')
    model=row.get("model_name") or os.getenv("LLM_MODEL", "deepseek-flash")
    if execution and urlsplit(row.get('base_url') or '').hostname=='api.deepseek.com' and model=='deepseek-v4-flash':
        model='deepseek-flash'
    return ResolvedModelConfig(
        api_key=_resolve_api_key(row),
        base_url=row.get("base_url") or os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
        model=model,
        temperature=row["temperature"] if row.get("temperature") is not None else 0.3,
        top_p=row["top_p"] if row.get("top_p") is not None else 1.0,
        max_tokens=row["max_tokens"] if row.get("max_tokens") is not None else 131072,
        source="db",
        thinking=execution['thinking'] if execution else None,
    )


def get_config_source_label(scene: str = "default") -> str:
    """Get a human-readable label for the config source."""
    cfg = resolve_model_config(scene)
    if cfg.source == "db":
        return "数据库配置"
    return "环境变量配置（兼容模式）"
