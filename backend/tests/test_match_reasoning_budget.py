"""Thinking output and complete-message budgets; isolated PostgreSQL, no provider calls."""
import json
import httpx
import pytest

from backend.app import ai_client, development_model, partner_match_context as context
from backend.app.model_resolver import configuration_stamp
from backend.app.task_failures import MatchInputBudgetError


def config(**overrides):
    return {"id": "synthetic", "api_key": "synthetic", "base_url": "https://api.deepseek.com",
            "model_name": "deepseek-v4-flash", "max_tokens": 384000, **overrides}


@pytest.mark.parametrize("char_limit", [context.DETAIL_CHAR_LIMIT])
def test_all_match_stages_reserve_saved_thinking_allowance(char_limit):
    original = config()
    messages = [{"role": "user", "content": "合成需求"}]
    budgeted, chars, estimate = context.checked_config(original, messages, {"type": "object"}, char_limit)
    assert budgeted["_match_output_tokens"] == 384000
    assert chars > len(messages[0]["content"]) and estimate > 0
    assert configuration_stamp(budgeted) == configuration_stamp(original)
    assert "_match_output_tokens" not in original


@pytest.mark.parametrize("saved", [1, 2048, 131072, 384000])
def test_administrator_output_limit_is_never_increased(saved):
    budgeted, _, _ = context.checked_config(config(max_tokens=saved), [], {}, 10000)
    assert budgeted["_match_output_tokens"] == saved


def test_remaining_context_includes_system_and_schema():
    original = config(base_url="https://unknown.example", max_tokens=131072)
    messages = [{"role": "system", "content": "规则"}, {"role": "user", "content": "中" * 20000}]
    schema = {"type": "object", "description": "完整结构" * 100}
    budgeted, _, estimate = context.checked_config(original, messages, schema, 60000)
    assert estimate > context._token_estimate(messages[-1]["content"])
    assert 0 < budgeted["_match_output_tokens"] == context.UNKNOWN_CONTEXT_CEILING - estimate
    # Adding system/schema text can exhaust context even when raw user input fits.
    with pytest.raises(MatchInputBudgetError):
        context.checked_config(original, messages, {"description": "中" * 10000}, 60000)


@pytest.mark.parametrize("saved", [0, -1])
def test_nonpositive_allowance_rejected_before_request(saved):
    with pytest.raises(MatchInputBudgetError):
        context.checked_config(config(max_tokens=saved), [], {}, 60000)


def test_long_answer_and_separate_reasoning_survive_transport(monkeypatch):
    sent = []
    final = json.dumps({"answer": "合成答复" * 12000}, ensure_ascii=False)
    def handle(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "reasoning_content": "合成思考" * 3000, "content": final}}]})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(development_model.httpx, "AsyncClient", lambda **kw: original_client(transport=httpx.MockTransport(handle), **kw))
    budgeted, _, _ = context.checked_config(config(), [], {"type": "object"}, 60000)
    assert development_model.completion(budgeted, [], {"type": "object"}) == final
    assert len(sent) == 1 and sent[0]["max_tokens"] == 384000
    assert sent[0]["thinking"] == {"type": "enabled"}


@pytest.mark.parametrize("finish,content", [("length", '{"answer":"looks complete"}'), ("stop", ""), ("content_filter", "blocked")])
def test_incomplete_or_reasoning_only_response_is_not_retried(monkeypatch, finish, content):
    sent = []
    def handle(request):
        sent.append(True)
        return httpx.Response(200, json={"choices": [{"finish_reason": finish, "message": {
            "reasoning_content": "synthetic private reasoning", "content": content}}]})
    original_client = httpx.AsyncClient
    monkeypatch.setattr(development_model.httpx, "AsyncClient", lambda **kw: original_client(transport=httpx.MockTransport(handle), **kw))
    with pytest.raises(ai_client.ModelResponseError):
        development_model.completion(config(), [], {"type": "object"})
    assert len(sent) == 1
