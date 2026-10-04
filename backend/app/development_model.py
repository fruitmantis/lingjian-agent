"""Shared model routing and guarded OpenAI-compatible adapter for Phase C."""
import asyncio
import os
from .model_timeout_settings import get_settings
from urllib.parse import urlsplit
import httpx
from .model_resolver import ModelConfigurationError,model_config_from_record,resolve_model_record,validate_model_retry
from .ai_client import _completion_content, completion_payload, retry_model_timeout


def configuration(*, read_only=False, connection=None):
    return resolve_model_record('partner_development', read_only=read_only, connection=connection)


def request_base_url(config, selected):
    """Explicit local matching test transport; keep provider identity and budgets."""
    proxy = os.getenv('BANFEI_MATCH_DELAY_PROXY_URL', '').strip() if config.get('_match_request') else ''
    if not proxy:
        return selected.base_url
    upstream = os.getenv('BANFEI_MATCH_DELAY_UPSTREAM', '').strip()
    if selected.base_url.rstrip('/') != upstream.rstrip('/'):
        raise ModelConfigurationError('慢响应测试上游与当前模型不一致，请停用测试代理或更新其配置')
    try:
        parsed = urlsplit(proxy)
        valid = (parsed.scheme == 'http' and parsed.hostname == '127.0.0.1'
                 and parsed.port is not None and parsed.path.rstrip('/') == '/v1'
                 and not any((parsed.username, parsed.password, parsed.query, parsed.fragment)))
    except ValueError:
        valid = False
    if not valid:
        raise ModelConfigurationError('慢响应测试仅允许本机 127.0.0.1 HTTP 代理')
    return proxy.rstrip('/')


def completion(config,messages,schema):
    from .error_diagnostics import bind_context, register_secret, model_response, record_error
    bind_context(model=config.get('model_name'), http_status=None, response_excerpt=None)
    try:
        selected=model_config_from_record(config)
        register_secret(selected.api_key)
        if not selected.api_key:raise ModelConfigurationError('Model API key is not configured')
        parsed=urlsplit(selected.base_url)
        if parsed.username or parsed.password or parsed.scheme not in ('http','https'):raise ModelConfigurationError('Invalid model endpoint')
        endpoint=request_base_url(config, selected).rstrip('/')+'/chat/completions'
        payload=completion_payload(selected,messages,schema)
        if config.get('_match_output_tokens'):
            payload['max_tokens'] = min(payload['max_tokens'], config['_match_output_tokens'])
        policy=get_settings(execution=config.get('_agent_execution'))
        limit=policy.timeoutSeconds
        async def send():
            # Wall-clock cancellation also bounds slow/chunked responses that keep resetting read timeouts.
            async with asyncio.timeout(limit):
                async with httpx.AsyncClient(timeout=limit,follow_redirects=False,trust_env=False) as client:
                    response=await client.post(endpoint,headers={'Authorization':'Bearer '+selected.api_key},json=payload)
                    model_response(response, selected.model)
                    response.raise_for_status()
                    return _completion_content(response.json())
        # Development execution already runs in the existing worker threads, outside the API event loop.
        return retry_model_timeout(lambda: asyncio.run(send()), policy=policy,
                                   before_retry=lambda: validate_model_retry(config))
    except Exception as error:
        record_error(error)
        raise
