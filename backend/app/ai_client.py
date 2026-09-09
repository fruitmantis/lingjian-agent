"""OpenAI-compatible LLM client using httpx."""

import httpx
from urllib.parse import urlsplit
from .model_resolver import ModelConfigurationError, resolve_model_config


def provider_request_options(base_url: str, model: str) -> dict:
    # Verified current provider mode: return business content, not a reasoning-only budget.
    if urlsplit(base_url).hostname == "api.deepseek.com" and model == "deepseek-v4-flash":
        return {"thinking": {"type": "disabled"}}
    return {}


class ModelResponseError(RuntimeError):
    """The upstream response is empty, malformed or incomplete."""


def model_error_message(error: Exception) -> str:
    """Return only fixed public messages, never upstream bodies, URLs or exceptions."""
    if isinstance(error, ModelConfigurationError):
        return "业务场景绑定的模型不存在或已停用，请管理员检查模型配置"
    if isinstance(error, httpx.TimeoutException):
        return "模型响应超时，请稍后重试"
    if isinstance(error, httpx.HTTPStatusError):
        if error.response.status_code in (401, 403):
            return "模型服务认证失败，请管理员检查访问凭据"
        if error.response.status_code == 429:
            return "模型服务请求受限，请稍后重试"
        return "模型服务返回异常，请稍后重试或联系管理员"
    if isinstance(error, httpx.RequestError):
        return "无法连接模型服务，请稍后重试或联系管理员"
    if isinstance(error, ModelResponseError):
        return "模型返回的内容为空、不完整或格式无效，请重试"
    return "模型调用失败，请稍后重试或联系管理员检查配置"


def get_llm_config() -> tuple[str, str, str]:
    """Legacy compat: returns (api_key, base_url, model) from resolver."""
    cfg = resolve_model_config()
    return cfg.api_key, cfg.base_url, cfg.model


def _completion_content(data: dict) -> str:
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise ModelResponseError("Invalid choices")

    choice = choices[0]
    if not isinstance(choice, dict) or choice.get("finish_reason") in ("length", "content_filter"):
        raise ModelResponseError("Incomplete completion")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ModelResponseError("Invalid message")
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(part["text"] for part in content
                          if isinstance(part, dict) and isinstance(part.get("text"), str)
                          and part.get("type", "text") in ("text", "output_text"))

    if not isinstance(content, str) or not content.strip():
        raise ModelResponseError("Empty completion")
    if "<think>" in content.lower() or "</think>" in content.lower():
        raise ModelResponseError("Unexpected reasoning content")

    return content


def chat_completion(messages: list[dict], timeout: int | None = None, scene: str = "default") -> str:
    cfg = resolve_model_config(scene)
    if not cfg.api_key:
        raise ModelConfigurationError("LLM_API_KEY is not configured (checked DB and env)")

    url = f"{cfg.base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
    payload = {
        "model": cfg.model,
        "messages": messages,
        "temperature": cfg.temperature,
        "top_p": cfg.top_p,
        "max_tokens": cfg.max_tokens,
    }
    payload.update(provider_request_options(cfg.base_url, cfg.model))
    actual_timeout = cfg.timeout_seconds if timeout is None else timeout

    with httpx.Client(timeout=actual_timeout) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return _completion_content(data)
