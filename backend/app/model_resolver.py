"""Unified model configuration resolver.

Priority: scene binding → default scene binding → enabled default → first enabled → env.
"""

import os
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
    """An explicit model selection is unavailable; never silently switch models."""


def _resolve_api_key(row) -> str:
    """Resolve API key: DB key > env var > empty."""
    if row and row["api_key"]:
        return row["api_key"]
    if row and row["api_key_source"] == "env" and row["api_key_env_name"]:
        return os.getenv(row["api_key_env_name"], "")
    # Fallback to default env var
    return os.getenv("LLM_API_KEY", "")


def resolve_model_config(scene: str = "default", *, read_only: bool = False) -> ResolvedModelConfig:
    """Resolve model config for a given business scene."""
    with (get_readonly_db() if read_only else get_db()) as conn:
        # 1. Try scene-bound config
        usage = conn.execute(
            "SELECT model_config_id FROM model_usage_configs WHERE scene_key = ?", (scene,)
        ).fetchone()
        config_id = None
        if usage and usage["model_config_id"]:
            config_id = usage["model_config_id"]

        # 2. If no scene config, try default scene
        if not config_id and scene != "default":
            usage_def = conn.execute(
                "SELECT model_config_id FROM model_usage_configs WHERE scene_key = 'default'"
            ).fetchone()
            if usage_def and usage_def["model_config_id"]:
                config_id = usage_def["model_config_id"]

        # 3. Try default ModelConfig
        if not config_id:
            default_mc = conn.execute(
                "SELECT * FROM model_configs WHERE is_default = 1 AND enabled = 1"
            ).fetchone()
            if default_mc:
                config_id = default_mc["id"]

        # 4. Try any enabled config
        if not config_id:
            any_mc = conn.execute(
                "SELECT * FROM model_configs WHERE enabled = 1 ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if any_mc:
                config_id = any_mc["id"]

        if config_id:
            row = conn.execute("SELECT * FROM model_configs WHERE id = ?", (config_id,)).fetchone()
            if row is None or not row["enabled"]:
                raise ModelConfigurationError("业务场景绑定的模型不存在或已停用，请管理员检查模型配置")
            if row:
                return ResolvedModelConfig(
                    api_key=_resolve_api_key(row),
                    base_url=row["base_url"] or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
                    model=row["model_name"] or os.getenv("LLM_MODEL", "gpt-4o"),
                    temperature=row["temperature"] if row["temperature"] is not None else 0.3,
                    top_p=row["top_p"] if row["top_p"] is not None else 1.0,
                    max_tokens=row["max_tokens"] if row["max_tokens"] is not None else 131072,
                    timeout_seconds=row["timeout_seconds"] if row["timeout_seconds"] is not None else 60,
                    source="db",
                )

    # 5. Fallback to env vars / code defaults
    return ResolvedModelConfig(
        api_key=os.getenv("LLM_API_KEY", ""),
        base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        model=os.getenv("LLM_MODEL", "gpt-4o"),
        temperature=0.3,
        top_p=1.0,
        max_tokens=131072,
        timeout_seconds=60,
        source="env",
    )


def get_config_source_label(scene: str = "default") -> str:
    """Get a human-readable label for the config source."""
    cfg = resolve_model_config(scene)
    if cfg.source == "db":
        return "数据库配置"
    return "环境变量配置（兼容模式）"
