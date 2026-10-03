"""Provider-specific options shared by VM-local and cloud model transports."""
from urllib.parse import urlsplit


def provider_request_options(base_url: str, model: str) -> dict:
    # DeepSeek Flash's documented raw HTTP option. Keep other providers' defaults:
    # e.g. GLM-5.3 is thinking-only and does not need this provider-specific field.
    if urlsplit(base_url).hostname == "api.deepseek.com" and model in ("deepseek-v4-flash", "deepseek-flash"):
        return {"thinking": {"type": "enabled"}}
    return {}

