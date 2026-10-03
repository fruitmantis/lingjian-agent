"""Small, allowlisted failure metadata; never serialize exceptions or model text."""
import json
import httpx
from pydantic import ValidationError

# retryable means eligible for the EXISTING VM-authorized timeout retry only.
# HTTP 429/5xx, invalid schemas and references do not gain automatic retries.
REASONS = {
    'model_configuration_invalid': 'ValueError',
    'input_budget_exceeded': 'ValueError',
    'provider_http_error': 'HTTPStatusError',
    'provider_transport_error': 'RequestError',
    'provider_response_invalid': 'ValueError',
    'provider_response_too_large': 'ValueError',
    'model_output_incomplete': 'ValueError',
    'model_output_empty': 'ValueError',
    'output_too_large': 'ValueError',
    'output_schema_invalid': 'ValidationError',
    'output_reference_invalid': 'ValueError',
    'output_policy_rejected': 'ValueError',
    'output_state_invalid': 'ValueError',
    'output_validation_failed': 'ValueError',
    'model_timeout': 'TimeoutError',
    'model_timeout_exhausted': 'TimeoutError',
    'vm_lease_expired': 'ValueError',
    'vm_cancelled': 'CancelledError',
    'runtime_interrupted': 'CancelledError',
    'runtime_internal_error': 'RuntimeError',
}
FINISH_REASONS = frozenset(('stop', 'length', 'content_filter', 'tool_calls',
                           'function_call', 'insufficient_system_resource', 'unknown'))
LEGACY_ERRORS = frozenset(('model_timeout', 'model_timeout_exhausted',
                           'runtime_interrupted', 'runtime_execution_failed',
                           'vm_lease_expired', 'vm_cancelled'))


def metadata(value):
    """Only fixed enums and bounded integers may cross this boundary."""
    if type(value) is not dict:
        return {}
    result = {}
    status = value.get('upstream_http_status')
    if type(status) is int and 100 <= status <= 599:
        result['upstream_http_status'] = status
    finish = value.get('finish_reason')
    if type(finish) is str and finish in FINISH_REASONS:
        result['finish_reason'] = finish
    return result


def diagnostic(reason_code, *, retryable=False, **details):
    if type(reason_code) is not str or reason_code not in REASONS:
        reason_code = 'runtime_internal_error'
    return {'reason_code': reason_code, 'error_type': REASONS[reason_code],
            'retryable': retryable is True and reason_code == 'model_timeout',
            **metadata(details)}


def sanitize_diagnostic(value, status=None):
    """Untrusted remote metadata is rebuilt, not copied; old peers may omit it."""
    if type(value) is not dict:
        return None
    reason = value.get('reason_code')
    if type(reason) is not str or reason not in REASONS:
        return None
    return diagnostic(reason, retryable=value.get('retryable') is True
                      and status in (None, 'awaiting_retry'), **metadata(value))


class StageFailure(ValueError):
    def __init__(self, reason_code, **details):
        self.runtime_diagnostic = diagnostic(reason_code, **details)
        # Existing administrator error detail already displays this safe message.
        super().__init__('Runtime stage failed: ' + json.dumps(
            self.runtime_diagnostic, sort_keys=True, separators=(',', ':')))


class ModelOutput(str):
    """Preserve the existing string completion interface with safe metadata only."""
    def __new__(cls, content, **details):
        result = super().__new__(cls, content)
        result.runtime_metadata = metadata(details)
        return result


def diagnose(error, details=None):
    if isinstance(error, StageFailure):
        safe = sanitize_diagnostic(error.runtime_diagnostic)
        if safe:
            return {**safe, **metadata(details)}
    if isinstance(error, ValidationError):
        reason = 'output_schema_invalid'
    elif isinstance(error, httpx.HTTPStatusError):
        return diagnostic('provider_http_error', upstream_http_status=error.response.status_code)
    elif isinstance(error, httpx.RequestError):
        reason = 'provider_transport_error'
    elif isinstance(error, ValueError):
        reason = 'output_validation_failed'
    else:
        reason = 'runtime_internal_error'
    return diagnostic(reason, **metadata(details))
