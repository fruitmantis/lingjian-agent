"""Public model failures must not expose upstream diagnostics or content."""
import httpx
import pytest

from backend.app import ai_client
from backend.app.database import get_db
from backend.app.routers import model_config, profile
from .conftest import auth_headers, make_partner, make_user


@pytest.mark.parametrize("data", [
    None, [], {}, {"choices": []}, {"choices": [None]},
    {"choices": [{"message": None}]}, {"choices": [{"message": {"content": " "}}]},
    {"choices": [{"message": {"content": [{"text": 123}]}}]},
    {"choices": [{"finish_reason": "length", "message": {"content": "truncated"}}]},
    {"choices": [{"finish_reason": "content_filter", "message": {"content": "filtered"}}]},
])
def test_incomplete_or_malformed_completion_is_rejected(data):
    with pytest.raises(ai_client.ModelResponseError):
        ai_client._completion_content(data)


def test_text_content_parts_remain_supported():
    assert ai_client._completion_content({"choices": [{"message": {"content": [{"type": "text", "text": "合成"}, {"text": "结果"}]}}]}) == "合成结果"


@pytest.mark.parametrize("failure", ["timeout", "http401", "http429", "http500", "exception", "empty", "truncated", "missing", "success"])
def test_manual_connection_test_validates_content_and_sanitizes_errors(client, monkeypatch, failure):
    admin = make_user("connection_admin", role="admin")
    config = model_config.create_config(model_config.ModelConfigCreate(name="synthetic", apiKey="synthetic-private-key", modelName="test", baseUrl="https://model.invalid/private-path"))
    marker = "synthetic-private-key Authorization Bearer synthetic-token private-customer-data"
    class FakeClient:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_args): pass
        def post(self, url, **kwargs):
            req = httpx.Request("POST", url)
            if failure == "timeout": raise httpx.ReadTimeout(marker, request=req)
            if failure == "exception": raise RuntimeError(marker)
            if failure.startswith("http"):
                return httpx.Response(int(failure[4:]), request=req, text=marker)
            data = {"choices": [{"finish_reason": "length" if failure == "truncated" else "stop", "message": {"content": "" if failure == "empty" else "synthetic ok"}}]}
            return httpx.Response(200, request=req, json={} if failure == "missing" else data)
    monkeypatch.setattr(model_config.httpx, "Client", FakeClient)
    response = client.post(f"/admin/model-configs/{config.id}/test", headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()["success"] is (failure == "success")
    for text in ("synthetic-private-key", "synthetic-token", "private-customer-data", "private-path", "Authorization"):
        assert text not in response.text


def test_profile_failure_preserves_data_without_exposing_exception(client, monkeypatch):
    make_partner()
    admin = make_user("profile_error_admin", role="admin")
    with get_db() as conn:
        before = dict(conn.execute("SELECT * FROM partners WHERE id = 'partner-1'").fetchone())
    def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic-secret raw-model-JSON internal-prompt")
    monkeypatch.setattr(profile, "chat_completion", fail)
    response = client.post("/partners/partner-1/profile", headers=auth_headers(admin))
    assert response.status_code == 502
    assert "模型调用失败" in response.json()["detail"]
    for text in ("synthetic-secret", "raw-model-JSON", "internal-prompt"):
        assert text not in response.text
    with get_db() as conn:
        assert dict(conn.execute("SELECT * FROM partners WHERE id = 'partner-1'").fetchone()) == before


def test_batch_profile_does_not_copy_nested_exception(client, monkeypatch):
    make_partner()
    admin = make_user("batch_error_admin", role="admin")
    def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic-secret raw-model-JSON internal-prompt")
    monkeypatch.setattr(profile, "generate_profile", fail)
    response = client.post("/partners/batch-profile", headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()["failed"] == 1
    assert "synthetic-secret" not in response.text and "raw-model-JSON" not in response.text


def test_reasoning_parts_are_not_returned_as_public_text():
    data = {"choices": [{"message": {"content": [
        {"type": "reasoning", "text": "synthetic-private-thought"},
        {"type": "text", "text": "可展示的结果"},
    ]}}]}
    assert ai_client._completion_content(data) == "可展示的结果"


def test_inline_reasoning_tags_are_rejected():
    with pytest.raises(ai_client.ModelResponseError):
        ai_client._completion_content({"choices": [{"message": {"content": "<think>synthetic-private-thought</think>结果"}}]})


@pytest.mark.parametrize("narrative", ["", '{"internal":"synthetic-secret"}', '```json\n{"raw":"synthetic-secret"}\n```'])
def test_profile_does_not_persist_raw_structured_output(client, monkeypatch, narrative):
    make_partner()
    admin = make_user("profile_format_admin", role="admin")
    responses = iter(['{}', narrative])
    monkeypatch.setattr(profile, "chat_completion", lambda *_a, **_k: next(responses))
    response = client.post("/partners/partner-1/profile", headers=auth_headers(admin))
    assert response.status_code == 502
    assert "synthetic-secret" not in response.text
    with get_db() as conn:
        assert conn.execute("SELECT ai_profile FROM partners WHERE id = 'partner-1'").fetchone()[0] is None
