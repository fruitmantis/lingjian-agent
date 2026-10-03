"""Append-only, redacted diagnostics in the existing server log directory.

No database dependency: failed transactions and successful retries cannot erase evidence.
Only the admin system router exposes this log; request bodies/headers are never recorded.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
import fcntl
import json
import logging
import os
import re
import traceback
import uuid
from urllib.parse import quote

from pydantic import ValidationError
from starlette.exceptions import HTTPException
from sqlalchemy.exc import StatementError

from .config import PROJECT_ROOT

_CONTEXT = ContextVar('error_diagnostic_context', default=None)
_LOG = logging.getLogger('banfei.errors')
_SENSITIVE = re.compile(r'password|passwd|secret|token|credential|api.?key|identity.?key|authorization|cookie|database_url', re.I)


def log_path():
    return Path(os.environ.get('BANFEI_ERROR_LOG_PATH') or PROJECT_ROOT / '.isolation/logs/errors.jsonl')


@contextmanager
def diagnostic_scope(**values):
    context = {'request_id': str(uuid.uuid4()), **values}
    token = _CONTEXT.set(context)
    try:
        yield context
    finally:
        _CONTEXT.reset(token)


def bind_context(**values):
    context = _CONTEXT.get()
    if context is not None:
        context.update(values)


def register_secret(value):
    context = _CONTEXT.get()
    if context is not None and value:
        context.setdefault('_secrets', set()).add(str(value))


def redact(value):
    """Sanitize before truncation so a cut-off credential cannot evade masking."""
    if isinstance(value, dict):
        return {str(k): '[REDACTED]' if _SENSITIVE.search(str(k)) or str(k).lower() in ('prompt', 'messages', 'request_body') else redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if not isinstance(value, str):
        return value
    secrets = set((_CONTEXT.get() or {}).get('_secrets', ()))
    secrets.update(v for k, v in os.environ.items() if (_SENSITIVE.search(k) or re.search(r'(?:^|_)KEY$', k, re.I)) and len(v) >= 4)
    for secret in sorted(secrets, key=len, reverse=True):
        for encoded in {secret, quote(secret, safe=''), json.dumps(secret, ensure_ascii=True)[1:-1]}:
            value = value.replace(encoded, '[REDACTED]')
    value = re.sub(r'\b(?:bf_|sk-)[A-Za-z0-9_-]+', '[REDACTED]', value)
    value = re.sub(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', '[REDACTED]', value)
    value = re.sub(r'\bgAAAAA[A-Za-z0-9_=-]+', '[REDACTED]', value)
    value = re.sub(r'INTERNAL_SECRET_[A-Za-z0-9_]+', '[REDACTED]', value)
    value = re.sub(r'(?im)^(Cookie|Set-Cookie)\s*:[^\r\n]*', r'\1: [REDACTED]', value)
    value = re.sub(r'(?i)\b(Bearer|Basic)\s+[^\s,;\"\'<>]+', r'\1 [REDACTED]', value)
    value = re.sub(r'(?i)([a-z][a-z0-9+.-]*://)[^\s/@]+:[^\s/@]+@', r'\1[REDACTED]@', value)
    value = re.sub(r'(?i)(https?://[^\s?\"\'<>]+)\?[^\s\"\'<>]*', r'\1?[REDACTED]', value)
    # Quoted JSON/Python assignments, then unquoted header/env/query values.
    value = re.sub(r'''(?ix)(["']?(?:api[_-]?key|identity[_-]?key|access[_-]?token|refresh[_-]?token|token|password|passwd|secret|authorization|cookie|set-cookie)["']?\s*[:=]\s*)(["'])(?:\\.|(?!\2).)*?\2''', r'\1"[REDACTED]"', value)
    value = re.sub(r'''(?ix)(\b(?:api[_-]?key|identity[_-]?key|access[_-]?token|refresh[_-]?token|token|password|passwd|secret|authorization|cookie|set-cookie)\s*[:=]\s*)(?!["'])([^\s,;&}\]]+)''', r'\1[REDACTED]', value)
    return value


def excerpt(value, limit=2000):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    try:
        text = json.dumps(redact(json.loads(text)), ensure_ascii=False)
    except (ValueError, TypeError):
        text = redact(text)
    return text[:limit] + ('…[truncated]' if len(text) > limit else '')


def current_stage(default):
    context = _CONTEXT.get() or {}
    return context.get('stage', default) if context.get('task_id') else default


def model_response(response, model=None):
    # Prefer the necessary completion fragment, without unrelated provider metadata.
    value = response.text
    try:
        data = response.json()
        choices = data.get('choices') if isinstance(data, dict) else None
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get('message')
            content = message.get('content') if isinstance(message, dict) else message
            if isinstance(content, str):
                try:content = json.loads(content)
                except ValueError:pass
            value = {'finish_reason': choices[0].get('finish_reason'), 'content': content}
    except ValueError:
        pass
    bind_context(model=model, http_status=response.status_code, response_excerpt=excerpt(value))


def _message(error):
    if isinstance(error, ValidationError):
        return json.dumps(error.errors(include_input=False, include_url=False), ensure_ascii=False, default=str)
    if isinstance(error, StatementError):
        # SQLAlchemy's str(error) embeds bind parameters (including passwords).
        return str(error.orig) if error.orig else type(error).__name__
    return str(error)


def record_error(error, stage=None, **values):
    original = getattr(error, 'original_error', error)
    if isinstance(original, HTTPException):
        original = original.__cause__ or original.__context__ or original
    if getattr(original, '_banfei_diagnostic_id', None):
        return original._banfei_diagnostic_id
    context = {**(_CONTEXT.get() or {}), **values}
    record = {
        'id': str(uuid.uuid4()), 'time': datetime.now(timezone.utc).isoformat(),
        'request_id': context.get('request_id') or str(uuid.uuid4()),
        'task_id': context.get('task_id'), 'run_id': context.get('run_id'),
        'stage': stage or context.get('stage') or 'request',
        'exception_type': type(original).__name__, 'message': excerpt(_message(original), 6000),
        'model': context.get('model'), 'http_status': context.get('http_status'),
        'response_excerpt': context.get('response_excerpt'),
    }
    timeout_details = getattr(original, 'model_timeout_details', None)
    if timeout_details:
        record.update(timeout_details)
        # The existing admin detail view displays message; no new UI or log endpoint is needed.
        record['message'] += f" [attempts={timeout_details['attempt_count']}, retries={timeout_details['retry_count']}/{timeout_details['max_retries']}]"
    response = getattr(original, 'response', None)
    if response is not None:
        record['http_status'] = response.status_code
        record['response_excerpt'] = excerpt(response.text)
    # Remote Runtime failures contain only a rebuilt whitelist. Do not reuse any
    # model response excerpt from the surrounding VM diagnostic context.
    from backend.agent_runtime.diagnostics import StageFailure, sanitize_diagnostic
    if isinstance(original, StageFailure):
        safe = sanitize_diagnostic(original.runtime_diagnostic)
        if safe:
            record['runtime_diagnostic'] = safe
            record['http_status'] = safe.get('upstream_http_status')
            record['response_excerpt'] = None
    # Include the actual stack without locals, raw SQL bind parameters or request payloads.
    stack = ''.join(f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}\n'
                    for frame in traceback.extract_tb(original.__traceback__))
    record['traceback'] = excerpt(stack + f'{type(original).__name__}: {_message(original)}', 24000)
    record = redact(record)
    line = json.dumps(record, ensure_ascii=False, default=str)
    # Always emit to the existing server logger, even when the diagnostic file cannot be written.
    _LOG.error('BANFEI_ERROR %s', line)
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, 'a', encoding='utf-8') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.write(line + '\n')
            stream.flush()
            fcntl.flock(stream, fcntl.LOCK_UN)
    except OSError:
        _LOG.error('Diagnostic file unavailable; the redacted event remains in the server log.')
    try:
        original._banfei_diagnostic_id = record['id']
    except (AttributeError, TypeError):
        pass
    return record['id']


def recent_errors(limit=50):
    try:
        with log_path().open('rb') as stream:
            stream.seek(0, 2)
            start = max(0, stream.tell() - 8 * 1024 * 1024)
            stream.seek(start)
            if start:
                stream.readline()  # Discard the partial oldest line.
            lines = stream.read().splitlines()
    except FileNotFoundError:
        return []
    items = []
    for line in reversed(lines):
        try:
            value = json.loads(line)
            if isinstance(value, dict) and value.get('id') and value.get('time'):
                items.append(redact(value))
        except (ValueError, UnicodeError):
            continue  # A killed writer must not make earlier complete records unreadable.
        if len(items) >= limit:
            break
    return sorted(items, key=lambda item: (item['time'], item['id']), reverse=True)


class ErrorDiagnosticsMiddleware:
    """Give every HTTP request correlation and keep unhandled failures out of public bodies."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        started = False
        with diagnostic_scope(stage=f"{scope['method']} {scope['path']}") as context:
            # Do not accept arbitrary client text as a log correlation value.
            path = scope['path']
            match = re.match(r'^/(?:agent/tasks|development/plans)/([^/]+)', path)
            if match:
                bind_context(task_id=match[1])
            async def wrapped_send(message):
                nonlocal started
                if message['type'] == 'http.response.start':
                    started = True
                    message['headers'] = [*message.get('headers', []), (b'x-request-id', context['request_id'].encode())]
                await send(message)
            try:
                await self.app(scope, receive, wrapped_send)
            except Exception as error:
                record_error(error)
                if not started:
                    from starlette.responses import JSONResponse
                    await JSONResponse({'detail': '服务异常，请联系管理员。'}, status_code=500)(scope, receive, wrapped_send)
