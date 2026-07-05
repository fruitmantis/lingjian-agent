"""OpenAI-compatible LLM client using httpx."""

import os
import httpx
from .model_resolver import resolve_model_config


def get_llm_config() -> tuple[str, str, str]:
    """Legacy compat: returns (api_key, base_url, model) from resolver."""
    cfg = resolve_model_config()
    return cfg.api_key, cfg.base_url, cfg.model


def _completion_content(data: dict) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("LLM 响应缺少 choices")

    choice = choices[0]
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )

    if not isinstance(content, str) or not content.strip():
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        diagnostics = [f"finish_reason={choice.get('finish_reason') or 'unknown'}"]
        if usage.get("completion_tokens") is not None:
            diagnostics.append(f"completion_tokens={usage['completion_tokens']}")
        if details.get("reasoning_tokens") is not None:
            diagnostics.append(f"reasoning_tokens={details['reasoning_tokens']}")
        raise RuntimeError(f"LLM 返回空内容（{', '.join(diagnostics)}）")

    return content


def chat_completion(messages: list[dict], timeout: int = 60, scene: str = "default") -> str:
    cfg = resolve_model_config(scene)
    if not cfg.api_key:
        raise RuntimeError("LLM_API_KEY is not configured (checked DB and env)")

    url = f"{cfg.base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {cfg.api_key}", "Content-Type": "application/json"}
    payload = {
        "model": cfg.model,
        "messages": messages,
        "temperature": cfg.temperature,
        "top_p": cfg.top_p,
        "max_tokens": cfg.max_tokens,
    }
    actual_timeout = timeout if timeout != 60 else cfg.timeout_seconds

    with httpx.Client(timeout=actual_timeout) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return _completion_content(data)
