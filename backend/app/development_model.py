"""Strict scene selection and guarded OpenAI-compatible adapter for Phase C."""
import asyncio
import json
from .development_deadlines import model_timeout
from urllib.parse import urlsplit
import httpx
from .database import get_db, get_readonly_db
from .model_resolver import ModelConfigurationError,_resolve_api_key
from .ai_client import _completion_content, provider_request_options


def configuration(*, read_only=False):
    with (get_readonly_db() if read_only else get_db()) as conn:
        selected=conn.execute("SELECT model_config_id FROM model_usage_configs WHERE scene_key='partner_development'").fetchone()
        config_id=selected[0] if selected else None
        if not config_id:
            default=conn.execute("SELECT model_config_id FROM model_usage_configs WHERE scene_key='default'").fetchone()
            config_id=default[0] if default else None
        if not config_id:
            rows=conn.execute('SELECT id FROM model_configs WHERE enabled=1 AND is_default=1').fetchall()
            if len(rows)!=1:raise ModelConfigurationError('Explicit development model selection required')
            config_id=rows[0][0]
        row=conn.execute('SELECT * FROM model_configs WHERE id=? AND enabled=1',(config_id,)).fetchone()
        if not row or not row['base_url'] or not row['model_name']:raise ModelConfigurationError('Invalid development model configuration')
        return dict(row)


def completion(config,messages,schema):
    parsed=urlsplit(config['base_url'])
    if parsed.username or parsed.password or parsed.scheme not in ('http','https'):raise ModelConfigurationError('Invalid model endpoint')
    # DeepSeek rejects json_schema. Keep the same schema and strict program validation.
    response_format={'type':'json_schema','json_schema':{'name':'development_output','strict':True,'schema':schema}}
    if parsed.hostname == 'api.deepseek.com':
        response_format={'type':'json_object'}
        messages=[*messages, {'role':'system','content':'Return a JSON object matching this exact JSON schema. No extra fields: '+json.dumps(schema,ensure_ascii=False)}]
    limit=model_timeout()
    async def send():
        # Wall-clock cancellation also bounds slow/chunked responses that keep resetting read timeouts.
        async with asyncio.timeout(limit):
            async with httpx.AsyncClient(timeout=limit,follow_redirects=False,trust_env=False) as client:
                response=await client.post(config['base_url'].rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+_resolve_api_key(config)},json={
                    'model':config['model_name'],'temperature':0.2,'max_tokens':min(config.get('max_tokens') or 8192,16384),
                    'messages':messages,'response_format':response_format,
                    **provider_request_options(config['base_url'],config['model_name'])})
                response.raise_for_status()
                return _completion_content(response.json())
    # Development execution already runs in the existing worker threads, outside the API event loop.
    return asyncio.run(send())
