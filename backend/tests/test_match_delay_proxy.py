"""Matching-only delay transport, synthetic loopback and isolated PostgreSQL."""
import json
import time

import pytest

from backend.app import development_model, partner_match_context
from backend.app.database import get_db
from backend.app.model_resolver import (
    ModelConfigurationError, configuration_stamp, model_config_from_record, resolve_model_record,
)
from backend.app.routers import match
from backend.tests.test_development_lifecycle import prepared
from backend.tests.test_partner_match_stages import answer
from scripts.simulate_slow_model import slow_proxy
from scripts.tests.test_slow_model_simulation import Capture, upstream


def test_loopback_transport_preserves_provider_options_and_large_input_budget(monkeypatch):
    with get_db() as conn:
        conn.execute("UPDATE model_configs SET base_url='https://api.deepseek.com',model_name='deepseek-v4-flash',api_key='synthetic-only-key',api_key_source='db'")
    config = resolve_model_record('partner_match')
    messages = [{'role': 'user', 'content': '资料' * 14000}]
    schema = {'type': 'object'}
    stamp = configuration_stamp(config)
    # This input exceeds the unknown-provider ceiling but fits the original model.
    budgeted, chars, tokens = partner_match_context.checked_config(config, messages, schema, 60000, 2048)
    assert tokens + 2048 > partner_match_context.UNKNOWN_CONTEXT_CEILING
    with upstream() as (url, received, _):
        with slow_proxy(url, delay=.1, port=0, events=Capture()) as server:
            monkeypatch.setenv('BANFEI_MATCH_DELAY_PROXY_URL', f'http://127.0.0.1:{server.server_port}/v1')
            monkeypatch.setenv('BANFEI_MATCH_DELAY_UPSTREAM', 'https://api.deepseek.com')
            started = time.monotonic()
            result = development_model.completion({**budgeted, '_match_request': True}, messages, schema)
            assert time.monotonic() - started >= .1
    assert result == 'synthetic result' and len(received) == 1
    body = json.loads(received[0][1])
    assert body['thinking'] == {'type': 'disabled'}
    assert body['max_tokens'] == 2048 and body['model'] == 'deepseek-v4-flash'
    assert body['messages'][-1]['content'] == messages[0]['content']
    assert configuration_stamp(budgeted) == stamp
    assert partner_match_context.input_metrics(budgeted, messages, schema)[0] == chars
    # Other scenes keep using their original endpoint even while the flag is on.
    assert development_model.request_base_url(config, model_config_from_record(config)) == 'https://api.deepseek.com'


@pytest.mark.parametrize('proxy,origin', [
    ('http://192.0.2.1:18181/v1', 'https://api.deepseek.com'),
    ('http://127.0.0.1:18181/v1?key=x', 'https://api.deepseek.com'),
    ('http://127.0.0.1:18181/v1', 'https://different.example'),
])
def test_proxy_rejects_nonlocal_or_mismatched_upstream(monkeypatch, proxy, origin):
    config = resolve_model_record()
    config['base_url'] = 'https://api.deepseek.com'
    monkeypatch.setenv('BANFEI_MATCH_DELAY_PROXY_URL', proxy)
    monkeypatch.setenv('BANFEI_MATCH_DELAY_UPSTREAM', origin)
    with pytest.raises(ModelConfigurationError):
        development_model.request_base_url({**config, '_match_request': True}, model_config_from_record(config))


def test_all_three_matching_calls_opt_into_delay_transport(prepared, monkeypatch):
    seen = []

    def complete(config, messages, schema):
        seen.append((schema['title'], config.get('_match_request')))
        if schema['title'] == 'MatchUnderstanding':
            return '{"in_scope":true,"facts":{"technicalNeeds":"合成需求"}}'
        if schema['title'] == 'InitialSelection':
            return '{"candidates":[{"partnerId":"partner-1","verificationFocus":"合成核验"}]}'
        return answer()

    monkeypatch.setattr(development_model, 'completion', complete)
    result = match.match_partners(match.MatchRequest(requirement='合成匹配测试'), prepared[0])
    assert result.taskStatus == 'ready'
    assert seen == [('MatchUnderstanding', True), ('InitialSelection', True), ('MatchAnswer', True)]
