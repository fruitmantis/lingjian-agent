"""OpenAI-compatible LLM client using httpx."""

import os
import httpx


def get_llm_config() -> tuple[str, str, str]:
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("LLM_MODEL", "gpt-4o")
    return api_key, base_url, model


def chat_completion(messages: list[dict], timeout: int = 60) -> str:
    api_key, base_url, model = get_llm_config()
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not configured")

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages, "temperature": 0.3}

    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
