"""Strict scene selection and guarded OpenAI-compatible adapter for Phase C."""
import os
import time
from threading import Timer
from .development_deadlines import model_timeout
from urllib.parse import urlsplit
import httpx
from .database import get_db
from .model_resolver import ModelConfigurationError,_resolve_api_key
from .ai_client import _completion_content


def configuration():
    with get_db() as conn:
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
    # Fail closed by default. The real adapter exists but this phase never enables it.
    if parsed.hostname not in ('127.0.0.1','localhost','::1') and os.getenv('LINGJIAN_ALLOW_REAL_DEVELOPMENT_MODEL')!='1':
        raise ModelConfigurationError('Real development model calls are disabled')
    limit=model_timeout()
    started=time.monotonic()
    with httpx.Client(timeout=limit,follow_redirects=False,trust_env=False) as client:
        deadline=Timer(limit,client.close)
        deadline.daemon=True
        deadline.start()
        try:
            response=client.post(config['base_url'].rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+_resolve_api_key(config)},json={
            'model':config['model_name'],'temperature':0.2,'max_tokens':min(config.get('max_tokens') or 8192,16384),
            'messages':messages,'response_format':{'type':'json_schema','json_schema':{'name':'development_output','strict':True,'schema':schema}}})
            if time.monotonic()-started >= limit:raise TimeoutError('Model deadline exceeded')
            response.raise_for_status()
            return _completion_content(response.json())
        finally:
            deadline.cancel()
