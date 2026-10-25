"""Unified model configuration resolver.

Each fixed agent and processing has one connection; runs preserve their selected options.
"""

import os
import hashlib
import json
from urllib.parse import urlsplit
from dataclasses import dataclass
import httpx
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


def model_endpoint_origin(base_url: str) -> tuple:
    """Validate the base URL and compare the normalized origin HTTPX will send."""
    try:
        if not isinstance(base_url, str) or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in base_url) or "\\" in base_url:
            raise ValueError('Invalid URL characters')
        parsed = urlsplit(base_url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or '?' in base_url or '#' in base_url):
            raise ValueError('Invalid HTTP base URL')
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            raise ValueError('Invalid port')
        target = httpx.URL(base_url)
        host = target.raw_host.decode('ascii')
        if not host.rstrip('.'):
            raise ValueError('Empty normalized host')
        return target.scheme, host, target.port or (443 if target.scheme == 'https' else 80)
    except (ValueError, UnicodeError, httpx.InvalidURL):
        raise ModelConfigurationError('模型接口地址须为有效的 HTTP(S) 基础地址，不能包含内嵌凭据、查询参数或片段') from None


def _resolve_api_key(row) -> str:
    """Use only the stored key or the environment variable explicitly bound to this connection."""
    if row and row["api_key"]:
        return row["api_key"]
    if row and row["api_key_source"] == "env" and row["api_key_env_name"]:
        return os.getenv(row["api_key_env_name"], "")
    return ""


# Connection fields have a single persisted source: the owning provider.
MODEL_SELECT = """SELECT m.*, p.name AS provider, p.base_url, p.protocol,
    p.api_key, p.api_key_source, p.api_key_env_name
    FROM model_configs m JOIN model_providers p ON p.id=m.provider_id"""

def model_record(connection, model_id, *, enabled_only=False):
    return connection.execute(MODEL_SELECT + ' WHERE m.id=?' +
        (' AND m.enabled=1' if enabled_only else ''), (model_id,)).fetchone()


def resolve_model_record(scene: str = "default", *, read_only: bool = False, connection=None) -> dict:
    """Resolve one agent/processing connection; no scene/default override chain."""
    if connection is None:
        with (get_readonly_db() if read_only else get_db()) as conn:
            return resolve_model_record(scene, connection=conn)
    agent_id=agent_settings.owner(scene)
    frozen=agent_settings.current_execution()
    selected=frozen if frozen and frozen['agentId']==agent_id else agent_settings.execution(connection,agent_id)
    row=model_record(connection, selected['modelConfigId'], enabled_only=True)
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
    row = model_record(connection, stamp['id'], enabled_only=True)
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
        row = model_record(conn, config['id'])
    current=dict(row) if row else {}
    if config.get('_agent_execution'):current['_agent_execution']=config['_agent_execution']
    if (row is None or row['enabled'] != config['enabled']
            or configuration_stamp(current) != configuration_stamp(config)):
        raise ModelConfigurationError('本次运行的模型配置已变化，请重试以使用当前配置')


def model_config_from_record(record) -> ResolvedModelConfig:
    """Use the same saved settings for text, structured output and connection tests."""
    row = dict(record)
    execution=row.get('_agent_execution')
    base_url=row.get("base_url") or os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    model_endpoint_origin(base_url)
    model=row.get("model_name") or os.getenv("LLM_MODEL", "deepseek-flash")
    if execution and urlsplit(row.get('base_url') or '').hostname=='api.deepseek.com' and model=='deepseek-v4-flash':
        model='deepseek-flash'
    return ResolvedModelConfig(
        api_key=_resolve_api_key(row),
        base_url=base_url,
        model=model,
        temperature=row["temperature"] if row.get("temperature") is not None else 0.2,
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
