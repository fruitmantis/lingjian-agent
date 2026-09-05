"""Model selection and admin validation against the isolated pytest database."""
import json
from contextlib import contextmanager
from datetime import datetime, timezone

import httpx
import pytest

from backend.app import ai_client, model_resolver
from backend.app.database import get_db
from backend.app.routers import model_config, match, profile
from .conftest import auth_headers, make_partner, make_task, make_user, recommendation


@pytest.fixture(autouse=True)
def isolated_models(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "synthetic-env-key")
    monkeypatch.setenv("LLM_MODEL", "synthetic-env-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://model.invalid/v1")
    with get_db() as conn:
        conn.execute("UPDATE model_usage_configs SET model_config_id = NULL")
        conn.execute("DELETE FROM model_configs")
    # Any unintended external request is a test failure.
    def no_network(*args, **kwargs):
        raise AssertionError("unexpected real model request")
    monkeypatch.setattr(httpx.Client, "post", no_network)


def add_model(name="model-a", **kwargs):
    return model_config.create_config(model_config.ModelConfigCreate(name=name, modelName=name, **kwargs)).id


def bind(scene, model_id):
    with get_db() as conn:
        conn.execute("UPDATE model_usage_configs SET model_config_id = ? WHERE scene_key = ?", (model_id, scene))


def test_unbound_priority_is_preserved():
    assert model_resolver.resolve_model_config("partner_match").model == "synthetic-env-model"
    first = add_model("first")
    default = add_model("default")
    explicit = add_model("explicit")
    assert model_resolver.resolve_model_config("partner_match").model == "first"
    model_config.set_default(default)
    assert model_resolver.resolve_model_config("partner_match").model == "default"
    bind("default", first)
    assert model_resolver.resolve_model_config("partner_match").model == "first"
    bind("partner_match", explicit)
    assert model_resolver.resolve_model_config("partner_match").model == "explicit"
    bind("partner_match", None)
    bind("default", None)
    model_config.toggle_enable(default, False)
    assert model_resolver.resolve_model_config("partner_match").model == "first"


@pytest.mark.parametrize("scene", ["partner_match", "default"])
@pytest.mark.parametrize("missing", [False, True])
def test_explicit_unavailable_binding_never_falls_back(scene, missing):
    model_id = add_model()
    model_config.toggle_enable(model_id, False)
    add_model("available-fallback")
    bind(scene, "missing-id" if missing else model_id)
    with pytest.raises(model_resolver.ModelConfigurationError, match="不存在或已停用"):
        model_resolver.resolve_model_config("partner_match")


def test_database_failure_does_not_select_environment_model(monkeypatch):
    @contextmanager
    def unavailable():
        raise RuntimeError("synthetic database unavailable")
        yield
    monkeypatch.setattr(model_resolver, "get_db", unavailable)
    with pytest.raises(RuntimeError, match="database unavailable"):
        model_resolver.resolve_model_config()


def test_system_status_reports_unavailable_binding_without_model_call():
    from backend.app.routers.system import _check_llm
    bind("default", "missing-config")
    items, has_error, message = _check_llm()
    assert has_error
    assert items[0].status == "error"
    assert "请管理员检查模型配置" in message


def test_zero_parameters_and_large_token_budget_are_preserved():
    add_model(temperature=0, topP=0, maxTokens=384000)
    resolved = model_resolver.resolve_model_config()
    assert resolved.temperature == 0
    assert resolved.top_p == 0
    assert resolved.max_tokens == 384000


@pytest.mark.parametrize("source,custom_key,expected", [("env", "synthetic-custom", True), ("env", "", False), ("db", "", True)])
def test_api_key_status_agrees_with_resolver_without_exposing_key(client, monkeypatch, source, custom_key, expected):
    admin = make_user("key_admin", role="admin")
    model_id = add_model()
    monkeypatch.setenv("SYNTHETIC_MODEL_KEY", custom_key)
    with get_db() as conn:
        conn.execute("UPDATE model_configs SET api_key_source = ?, api_key_env_name = 'SYNTHETIC_MODEL_KEY' WHERE id = ?", (source, model_id))
    response = client.get("/admin/model-configs", headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()[0]["apiKeyConfigured"] is expected
    assert bool(model_resolver.resolve_model_config().api_key) is expected
    assert "synthetic-custom" not in response.text
    assert "synthetic-env-key" not in response.text
    assert "apiKey" not in response.json()[0]


@pytest.mark.parametrize("method", ["post", "put"])
@pytest.mark.parametrize("field,value", [
    ("temperature", -1), ("temperature", "NaN"), ("temperature", "Infinity"),
    ("topP", -1), ("topP", 1.1), ("topP", "NaN"),
    ("maxTokens", 0), ("maxTokens", 1.5), ("timeoutSeconds", -1),
])
def test_rejects_invalid_numeric_parameters(client, method, field, value):
    admin = make_user("parameter_admin", role="admin")
    model_id = add_model()
    path = "/admin/model-configs" + (f"/{model_id}" if method == "put" else "")
    response = getattr(client, method)(path, headers=auth_headers(admin), json={"name": "bad", field: value})
    assert response.status_code == 422
    assert model_resolver.resolve_model_config().model == "model-a"


def test_binding_api_validates_enabled_target_and_allows_unbind(client):
    admin = make_user("binding_admin", role="admin")
    user = make_user("binding_user")
    model_id = add_model()
    path = "/admin/model-configs/usage/partner_match"
    assert client.put(path, headers=auth_headers(user), json={"modelConfigId": model_id}).status_code == 403
    assert client.put(path, headers=auth_headers(admin), json={"modelConfigId": "absent"}).status_code == 400
    assert client.put(path, headers=auth_headers(admin), json={"modelConfigId": model_id}).status_code == 200
    model_config.toggle_enable(model_id, False)
    assert client.put(path, headers=auth_headers(admin), json={"modelConfigId": model_id}).status_code == 400
    response = client.put(path, headers=auth_headers(admin), json={"modelConfigId": None})
    assert response.status_code == 200 and response.json()["modelConfigId"] is None


@pytest.mark.parametrize("timeout,expected", [(None, 123), (60, 60), (180, 180)])
def test_client_honors_explicit_timeout_and_sends_zero(monkeypatch, timeout, expected):
    add_model(temperature=0, topP=0, timeoutSeconds=123)
    observed = {}
    class FakeClient:
        def __init__(self, **kwargs): observed.update(kwargs)
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def post(self, url, **kwargs):
            observed.update(kwargs)
            return httpx.Response(200, request=httpx.Request("POST", url), json={"choices": [{"message": {"content": "synthetic result"}}]})
    monkeypatch.setattr(ai_client.httpx, "Client", FakeClient)
    assert ai_client.chat_completion([], timeout=timeout) == "synthetic result"
    assert observed["timeout"] == expected
    assert observed["json"]["temperature"] == 0
    assert observed["json"]["top_p"] == 0


def test_each_business_call_uses_its_own_scene(monkeypatch):
    make_partner()
    owner = make_user("scene_user")
    task_id = make_task(owner, "scene validation")
    recs = [match.PartnerRecommendation(**recommendation())]
    calls = []
    responses = iter(['{}', 'synthetic profile', '{}', '[]', '{}', '[]', '[%s]' % json.dumps(recommendation())])
    def complete(messages, **kwargs):
        calls.append((kwargs.get("scene"), kwargs.get("timeout")))
        return next(responses)
    monkeypatch.setattr(profile, "chat_completion", complete)
    monkeypatch.setattr(match, "chat_completion", complete)
    monkeypatch.setattr(ai_client, "chat_completion", complete)
    profile.generate_profile("partner-1")
    match._generate_demand_profile(task_id, "需求", recs, datetime.now(timezone.utc).isoformat())
    assert match._generate_tag_suggestions("需求", task_id)
    assert match._extract_project_opportunity("需求", task_id, recs)
    from backend.app.routers.capability_tags import scan_suggestions
    scan_suggestions()
    match._perform_partner_match("需求")
    assert calls == [
        ("partner_profile", 60), ("partner_profile", 90), ("demand_profile", 30),
        ("tag_suggestion", 30), ("demand_profile", 60), ("tag_suggestion", 30), ("partner_match", 180),
    ]


@pytest.mark.parametrize("scene,path", [
    ("partner_match", "/agent/match"), ("partner_profile", "/partners/partner-1/profile"),
    ("tag_suggestion", "/admin/capability-tags/suggestions/scan"),
])
def test_invalid_binding_returns_actionable_error_without_calling_model(client, scene, path):
    make_partner()
    admin = make_user("unavailable_admin", role="admin")
    make_task(admin, "scan input")
    bind(scene, "missing-config")
    response = client.post(path, headers=auth_headers(admin), json={"requirement": "寻找测试伙伴"})
    assert response.status_code == 503
    assert "请管理员检查模型配置" in response.json()["detail"]
