"""Unified model configuration resolver.

Priority: enabled scene preference → enabled default preference → enabled default.
"""

import os
import hashlib
import json
from dataclasses import dataclass
from .database import get_db, get_readonly_db


@dataclass
class ResolvedModelConfig:
    api_key: str
    base_url: str
    model: str
    temperature: float
    top_p: float
    max_tokens: int
    timeout_seconds: int
    source: str  # "db" / "env" / "default"


class ModelConfigurationError(RuntimeError):
    """No enabled model or an invalid connection configuration."""


def _resolve_api_key(row) -> str:
    """Resolve API key: DB key > env var > empty."""
    if row and row["api_key"]:
        return row["api_key"]
    if row and row["api_key_source"] == "env" and row["api_key_env_name"]:
        return os.getenv(row["api_key_env_name"], "")
    # Fallback to default env var
    return os.getenv("LLM_API_KEY", "")


def resolve_model_record(scene: str = "default", *, read_only: bool = False, connection=None) -> dict:
    """Select only a scene preference or an explicit system default for a new run."""
    if connection is None:
        with (get_readonly_db() if read_only else get_db()) as conn:
            return resolve_model_record(scene, connection=conn)
    rows = connection.execute(
        "SELECT * FROM model_configs WHERE enabled = 1 ORDER BY is_default DESC, created_at, id"
    ).fetchall()
    if not rows:
        raise ModelConfigurationError("没有启用的模型配置，请管理员新增或启用模型")
    available = {row["id"]: row for row in rows}
    selected = next((row for row in rows if row['is_default']), None)
    for key in dict.fromkeys((scene, "default")):
        usage = connection.execute("SELECT model_config_id FROM model_usage_configs WHERE scene_key = ?", (key,)).fetchone()
        if usage and usage[0] in available:
            selected = available[usage[0]]
            break
    if selected is None:
        raise ModelConfigurationError('请配置启用的场景首选或系统默认模型')
    config = dict(selected)
    # Preserve existing per-configuration environment-backed connection fields.
    config["base_url"] = config["base_url"] or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    config["model_name"] = config["model_name"] or os.getenv("LLM_MODEL", "gpt-4o")
    return config


def configuration_stamp(config: dict) -> dict:
    """No credentials are persisted in task snapshots, only a configuration digest."""
    resolved = model_config_from_record(config)
    digest = hashlib.sha256(json.dumps(vars(resolved), sort_keys=True).encode()).hexdigest()
    return {'id': config['id'], 'fingerprint': digest}


def pinned_configuration(stamp: dict, connection=None) -> dict:
    if connection is None:
        with get_db() as conn:
            return pinned_configuration(stamp, conn)
    row = connection.execute('SELECT * FROM model_configs WHERE id=? AND enabled=1', (stamp['id'],)).fetchone()
    if row is None:
        raise ModelConfigurationError('本次运行的模型已停用或删除，请重试以使用当前配置')
    config = dict(row)
    if configuration_stamp(config) != stamp:
        raise ModelConfigurationError('本次运行的模型参数已变化，请重试以使用当前配置')
    return config


def resolve_model_config(scene: str = "default", *, read_only: bool = False) -> ResolvedModelConfig:
    return model_config_from_record(resolve_model_record(scene, read_only=read_only))


def model_config_from_record(record) -> ResolvedModelConfig:
    """Use the same saved settings for text, structured output and connection tests."""
    row = dict(record)
    return ResolvedModelConfig(
        api_key=_resolve_api_key(row),
        base_url=row.get("base_url") or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        model=row.get("model_name") or os.getenv("LLM_MODEL", "gpt-4o"),
        temperature=row["temperature"] if row.get("temperature") is not None else 0.3,
        top_p=row["top_p"] if row.get("top_p") is not None else 1.0,
        max_tokens=row["max_tokens"] if row.get("max_tokens") is not None else 131072,
        timeout_seconds=row["timeout_seconds"] if row.get("timeout_seconds") is not None else 60,
        source="db",
    )


def get_config_source_label(scene: str = "default") -> str:
    """Get a human-readable label for the config source."""
    cfg = resolve_model_config(scene)
    if cfg.source == "db":
        return "数据库配置"
    return "环境变量配置（兼容模式）"
