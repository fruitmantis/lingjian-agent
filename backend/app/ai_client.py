"""OpenAI-compatible LLM client using httpx."""

import json
import httpx
from contextvars import ContextVar
from urllib.parse import urlsplit
from .model_resolver import ModelConfigurationError, ResolvedModelConfig, resolve_model_config
from .model_timeout_settings import get_settings

_LAST_RETRY_COUNT = ContextVar('model_last_retry_count', default=0)


def last_retry_count() -> int:
    return _LAST_RETRY_COUNT.get()


def reset_retry_count() -> None:
    _LAST_RETRY_COUNT.set(0)


def provider_request_options(base_url: str, model: str) -> dict:
    # Verified current provider mode: return business content, not a reasoning-only budget.
    if urlsplit(base_url).hostname == "api.deepseek.com" and model == "deepseek-v4-flash":
        return {"thinking": {"type": "disabled"}}
    return {}


def completion_payload(config: ResolvedModelConfig, messages: list[dict], schema: dict | None = None) -> dict:
    payload = {
        "model": config.model, "messages": messages,
        "temperature": config.temperature, "top_p": config.top_p, "max_tokens": config.max_tokens,
        **provider_request_options(config.base_url, config.model),
    }
    if schema is not None:
        # JSON mode is portable; field/permission validation remains in the application.
        instruction = "Return only a JSON object matching this JSON schema. No extra fields: " + json.dumps(schema, ensure_ascii=False)
        if messages and messages[0].get("role") == "system":
            messages = [{**messages[0], "content": messages[0]["content"] + "\n\n" + instruction}, *messages[1:]]
        else:
            messages = [{"role": "system", "content": instruction}, *messages]
        payload.update(messages=messages, response_format={"type": "json_object"})
    return payload


class ModelResponseError(RuntimeError):
    """The upstream response is empty, malformed or incomplete."""


def model_error_message(error: Exception) -> str:
    """Return only fixed public messages, never upstream bodies, URLs or exceptions."""
    if isinstance(error, ModelConfigurationError):
        return "暂无可用模型，请管理员检查启用状态和连接配置"
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
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


def retry_model_timeout(send, *, policy, before_retry):
    """Retry only the transport request, never the enclosing business operation."""
    from .error_diagnostics import record_error
    retries = policy.timeoutRetries
    for retry_count in range(retries + 1):
        _LAST_RETRY_COUNT.set(retry_count)
        if retry_count:
            before_retry()
        try:
            return send()
        except (TimeoutError, httpx.TimeoutException) as error:
            # Keep the original exception class, message and traceback for administrators.
            if retry_count and hasattr(error, '_banfei_diagnostic_id'):
                del error._banfei_diagnostic_id
            error.model_timeout_details = {
                'timeout_seconds': policy.timeoutSeconds, 'retry_count': retry_count,
                'attempt_count': retry_count + 1, 'max_retries': retries,
            }
            record_error(error)
            if retry_count == retries:
                raise


def chat_completion(messages: list[dict], scene: str = "default") -> str:
    from .error_diagnostics import bind_context, register_secret, model_response, record_error, current_stage
    stage = current_stage(scene)
    bind_context(stage=stage, model=None, http_status=None, response_excerpt=None)
    try:
        cfg = resolve_model_config(scene)
        register_secret(cfg.api_key)
        bind_context(model=cfg.model)
        if not cfg.api_key:
            raise ModelConfigurationError("LLM_API_KEY is not configured (checked DB and env)")

        url = f"{cfg.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
        payload = completion_payload(cfg, messages)
        # Freeze both values for this call and its retries; the next call reads saved settings.
        policy = get_settings()

        def send():
            with httpx.Client(timeout=policy.timeoutSeconds) as client:
                resp = client.post(url, headers=headers, json=payload)
                model_response(resp, cfg.model)
                resp.raise_for_status()
                return _completion_content(resp.json())

        def before_retry():
            if resolve_model_config(scene) != cfg:
                raise ModelConfigurationError('本次运行的模型参数已变化，请重试以使用当前配置')

        return retry_model_timeout(send, policy=policy, before_retry=before_retry)
    except Exception as error:
        record_error(error, stage)
        raise
