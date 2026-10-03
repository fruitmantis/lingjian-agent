"""Timeout policy and lifecycle regression; synthetic HTTP only, isolated storage."""
import asyncio
import copy
import json
import time

import httpx
import pytest

from backend.app import ai_client, model_timeout_settings as config, development_model, development_engine as engine
from backend.app import development_lifecycle as life, error_diagnostics as diagnostics
from backend.app.database import get_db
from backend.app.development_types import Revise
from backend.app.model_resolver import ModelConfigurationError, resolve_model_record
from backend.tests.test_development_lifecycle import prepared, plan
from backend.tests.test_unified_flow import unified, generated
from backend.tests.conftest import auth_headers, make_task, make_user

REAL_COMPLETION = development_model.completion


@pytest.fixture(autouse=True)
def timeout_settings(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY', 'synthetic-private-timeout-key')


def transport(monkeypatch, handler):
    original_sync, original_async = httpx.Client, httpx.AsyncClient
    monkeypatch.setattr(httpx, 'Client', lambda **kw: original_sync(**{'transport': httpx.MockTransport(handler), **kw}))
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original_async(**{'transport': httpx.MockTransport(handler), **kw}))


def reply(request, content='synthetic result'):
    return httpx.Response(200, request=request, json={'choices': [{'message': {'content': content}, 'finish_reason': 'stop'}]})


def invoke(kind):
    messages = [{'role': 'user', 'content': 'same synthetic business input'}]
    if kind == 'text':
        return ai_client.chat_completion(messages)
    return REAL_COMPLETION(resolve_model_record(), messages, {'type': 'object'})


def set_policy(seconds=300, retries=3):
    from backend.app import agent_settings
    policy=config.TimeoutSettings(timeoutSeconds=seconds,timeoutRetries=retries).model_dump()
    current=agent_settings.read()
    for agent_id,value in current['agents'].items():
        agent_settings.save(agent_id,agent_settings.AgentSettings(**{**value,**policy}))
    agent_settings.save('processing',agent_settings.ModelSettings(**{**current['processing'],**policy}))


def test_default_and_custom_saved_policy():
    from backend.app.development_deadlines import run_timeout
    assert config.describe() == {'timeoutSeconds':300, 'timeoutRetries':3}
    assert (config.get_settings().call_budget(), run_timeout()) == (1200, 2460)
    set_policy(420, 1)
    assert (config.get_settings().call_budget(), run_timeout()) == (840, 1740)


@pytest.mark.parametrize('kind', ['text', 'structured'])
@pytest.mark.parametrize('retries', [0, 1, 3])
@pytest.mark.parametrize('exception', [TimeoutError, httpx.ReadTimeout, httpx.ConnectTimeout, httpx.WriteTimeout, httpx.PoolTimeout])
def test_timeout_retries_reuse_payload_and_saved_policy(kind, retries, exception, monkeypatch):
    set_policy(7, retries)
    calls = []
    def handle(request):
        calls.append((request.url, copy.deepcopy(json.loads(request.content)), dict(request.headers)))
        assert all(value == 7 for value in request.extensions['timeout'].values())
        if len(calls) <= retries:
            raise exception('synthetic timeout synthetic-private-timeout-key')
        return reply(request)
    transport(monkeypatch, handle)
    assert invoke(kind) == 'synthetic result'
    assert len(calls) == retries + 1 and all(call == calls[0] for call in calls)
    errors = diagnostics.recent_errors()
    assert len(errors) == retries
    assert all(error['exception_type'] == exception.__name__ for error in errors)
    if errors:
        assert 'synthetic-private-timeout-key' not in diagnostics.log_path().read_text()


@pytest.mark.parametrize('kind', ['text', 'structured'])
@pytest.mark.parametrize('error_kind', ['timeout', 'connection', 'authentication', 'rate_limit', 'provider', 'malformed', 'empty'])
def test_exhaustion_records_actual_error_and_other_failures_do_not_retry(kind, error_kind, monkeypatch):
    calls = []
    def handle(request):
        calls.append(request)
        if error_kind == 'timeout': raise TimeoutError('synthetic timed out')
        if error_kind == 'connection': raise httpx.ConnectError('synthetic connection failed')
        if error_kind == 'malformed': return httpx.Response(200, text='{broken')
        if error_kind == 'empty': return reply(request, '')
        return httpx.Response({'authentication':401, 'rate_limit':429, 'provider':500}[error_kind])
    transport(monkeypatch, handle)
    with pytest.raises(Exception) as raised:
        invoke(kind)
    assert len(calls) == (4 if error_kind == 'timeout' else 1)
    if error_kind == 'timeout':
        assert type(raised.value) is TimeoutError
        last = max(diagnostics.recent_errors(), key=lambda row: row['attempt_count'])
        assert (last['exception_type'], last['retry_count'], last['attempt_count'], last['max_retries']) == ('TimeoutError', 3, 4, 3)
        assert 'TimeoutError: synthetic timed out' in last['traceback']
        assert 'retries=3/3' in last['message']
        assert ai_client.model_error_message(raised.value) == '模型响应超时，请稍后重试'


@pytest.mark.parametrize('kind', ['text', 'structured'])
@pytest.mark.parametrize('mutation', ['disabled', 'changed', 'deleted'])
def test_configuration_changes_stop_retries(kind, mutation, monkeypatch):
    calls = []
    def handle(request):
        calls.append(request)
        with get_db() as conn:
            if mutation == 'disabled': conn.execute('UPDATE model_configs SET enabled=0')
            elif mutation == 'changed': conn.execute('UPDATE model_configs SET temperature=0.9')
            else: conn.execute('DELETE FROM model_usage_configs'); conn.execute('DELETE FROM model_configs')
        raise httpx.ReadTimeout('synthetic timeout')
    transport(monkeypatch, handle)
    with pytest.raises(ModelConfigurationError):
        invoke(kind)
    assert len(calls) == 1


def test_wall_clock_timeout_resets_for_each_attempt(monkeypatch):
    set_policy(.05)
    calls = []
    async def handle(request):
        calls.append(request)
        await asyncio.sleep(1)
        return reply(request)
    original = httpx.AsyncClient
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handle), **kw))
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        invoke('structured')
    elapsed = time.monotonic() - started
    assert len(calls) == 4 and .18 <= elapsed < 1
    assert max(row['retry_count'] for row in diagnostics.recent_errors()) == 3


@pytest.mark.parametrize('exhausted', [False, True])
def test_retries_do_not_create_runs_versions_or_overwrite_current(unified, monkeypatch, exhausted, client):
    accepted, detail = generated(unified)
    user, _, admin, request = unified[0]
    pid = accepted['plan_id']; before = detail['plan']['current_version_id']
    revision = life.revise(pid, Revise(submission_id='timeout-revision', based_on_version_id=before,
                                     instruction='重新规划数据库迁移建议', request=request), user)
    calls = []
    def handle(req):
        payload = json.loads(req.content)
        if payload['messages'][0]['content'].startswith('partner_development:analyze'):
            return reply(req, unified[2](resolve_model_record(), payload['messages'], {}))
        calls.append(payload)
        with get_db() as conn:
            assert conn.execute('SELECT count(*) FROM development_versions WHERE plan_id=?', (pid,)).fetchone()[0] == 1
            assert conn.execute('SELECT count(*) FROM development_runs WHERE plan_id=?', (pid,)).fetchone()[0] == 2
        assert plan(pid)['current_version_id'] == before
        if exhausted or len(calls) < 4: raise TimeoutError('synthetic generation timeout')
        return reply(req, unified[2](resolve_model_record(), payload['messages'], {}))
    transport(monkeypatch, handle)
    monkeypatch.setattr(development_model, 'completion', REAL_COMPLETION)
    engine.execute(revision['run_id'])
    assert len(calls) == 4 and all(call == calls[0] for call in calls)
    with get_db() as conn:
        run = dict(conn.execute('SELECT * FROM development_runs WHERE id=?', (revision['run_id'],)).fetchone())
        versions = conn.execute('SELECT id FROM development_versions WHERE plan_id=?', (pid,)).fetchall()
    assert run['status'] == ('failed' if exhausted else 'ready')
    assert len(versions) == (1 if exhausted else 2)
    assert (plan(pid)['current_version_id'] == before) is exhausted
    if exhausted:
        assert json.loads(run['safe_error_message'])[0]['message'] == '本次处理失败，请重试。'
        # The existing admin endpoint exposes true type + retry count; user views do not.
        errors = client.get('/admin/system/errors', headers=auth_headers(admin)).json()['items']
        assert any(row['exception_type'] == 'TimeoutError' and row.get('retry_count') == 3 for row in errors)
        assert client.get('/admin/system/errors', headers=auth_headers(user)).status_code == 403


def test_task_recovery_does_not_expire_a_legitimate_retry(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from backend.app.database import recover_stale_tasks
    user = make_user('timeout-recovery')
    updated = (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat()
    task = make_task(user, 'synthetic pending retry', task_status='matching', updated_at=updated)
    assert recover_stale_tasks(record_id=task) == 0
    assert recover_stale_tasks(record_id=task, stale_after_seconds=900) == 1


@pytest.mark.parametrize('kind', ['text', 'structured'])
def test_real_loopback_request_timeouts_and_recovery(kind, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    set_policy(.1)
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            attempt = len(requests)
            if attempt <= 3: time.sleep(.4)
            body = json.dumps({'choices': [{'message': {'content': 'synthetic result'}}]}).encode()
            try:
                self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = Thread(target=lambda: server.serve_forever(poll_interval=.02), daemon=True)
    worker.start()
    try:
        with get_db() as conn:
            conn.execute('UPDATE model_configs SET base_url=?', (f'http://127.0.0.1:{server.server_port}/v1',))
        assert invoke(kind) == 'synthetic result'
        assert len(requests) == 4 and all(item == requests[0] for item in requests)
        assert len(diagnostics.recent_errors()) == 3
    finally:
        server.shutdown(); server.server_close(); worker.join(2)


def test_reused_timeout_exception_still_records_final_retry_count(monkeypatch):
    error = TimeoutError('same exception object')
    transport(monkeypatch, lambda request: (_ for _ in ()).throw(error))
    with pytest.raises(TimeoutError) as raised:
        invoke('text')
    assert raised.value is error
    assert sorted(row['retry_count'] for row in diagnostics.recent_errors()) == [0, 1, 2, 3]


@pytest.mark.parametrize('kind', ['text', 'structured'])
def test_save_affects_next_call_not_attempts_already_started(kind, monkeypatch):
    set_policy(7, 3)
    calls = []
    def handle(request):
        calls.append(request.extensions['timeout']['read'])
        if len(calls) == 1:
            set_policy(11, 0)
        if len(calls) <= 3:
            raise TimeoutError('synthetic timeout while admin updates policy')
        return reply(request)
    transport(monkeypatch, handle)
    assert invoke(kind) == 'synthetic result'
    assert calls == [7, 7, 7, 7]
    assert invoke(kind) == 'synthetic result'
    assert calls == [7, 7, 7, 7, 11]
