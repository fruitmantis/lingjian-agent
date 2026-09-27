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
    model_id = model_config.create_config(model_config.ModelConfigCreate(name=name, modelName=name, **kwargs)).id
    # Tests that need routing explicitly configure a system default in their fixture.
    with get_db() as conn:
        first = conn.execute('SELECT count(*) FROM model_configs').fetchone()[0] == 1
    if first: model_config.set_default(model_id)
    return model_id


def bind(scene, model_id):
    with get_db() as conn:
        conn.execute("UPDATE model_usage_configs SET model_config_id = ? WHERE scene_key = ?", (model_id, scene))


@pytest.mark.parametrize("enabled", [True, False])
def test_delete_model_requires_admin_and_removes_unused_config(client, enabled):
    admin = make_user("delete_admin", role="admin")
    user = make_user("delete_user")
    model_id = add_model(apiKey="synthetic-delete-secret")
    model_config.toggle_enable(model_id, enabled)
    path = f"/admin/model-configs/{model_id}"
    assert client.delete(path).status_code == 401
    assert client.delete(path, headers=auth_headers(user)).status_code == 403
    headers = auth_headers(admin)
    assert client.delete(path, headers=headers).status_code == 204
    assert client.get("/admin/model-configs", headers=headers).json() == []
    assert client.delete(path, headers=headers).status_code == 404
    with get_db() as conn:
        audit = conn.execute("SELECT actor_user_id, summary FROM user_audit_logs WHERE action='model_config_deleted'").fetchone()
        assert audit["actor_user_id"] == admin["id"]
        summary = json.loads(audit["summary"])
        assert summary["model_config_id"] == model_id
        assert summary["historical_run_ids"] == []
        assert "synthetic-delete-secret" not in audit["summary"]


def test_delete_model_clears_preferences_and_requires_explicit_default(client):
    headers = auth_headers(make_user("delete_bound_admin", role="admin"))
    model_id = add_model()
    replacement = add_model("replacement")
    model_config.set_default(model_id)
    bind("partner_match", model_id)
    bind("default", model_id)
    bind("partner_development", model_id)
    path = f"/admin/model-configs/{model_id}"
    assert client.delete(path, headers=headers).status_code == 204
    with pytest.raises(model_resolver.ModelConfigurationError, match="场景首选或系统默认"):
        model_resolver.resolve_model_config("partner_match")
    model_config.set_default(replacement)
    assert model_resolver.resolve_model_config("partner_match").model == "replacement"
    from backend.app import development_model
    assert development_model.configuration()["id"] == replacement
    assert all(u["modelConfigId"] is None for u in client.get("/admin/model-configs/usage", headers=headers).json())
    assert client.put("/admin/model-configs/usage/partner_match", headers=headers, json={"modelConfigId": model_id}).status_code == 400
    assert client.delete(f"/admin/model-configs/{replacement}", headers=headers).status_code == 204
    with pytest.raises(model_resolver.ModelConfigurationError, match="没有启用"):
        development_model.configuration()


@pytest.mark.parametrize("run_status,fail_audit", [("running", False), ("ready", False), ("ready", True)])
def test_delete_model_preserves_run_history(client_no_raise, monkeypatch, run_status, fail_audit):
    from backend.app import development_lifecycle, development_engine
    from backend.app.development_types import DevelopmentRequest, Submit
    owner = make_user("history_owner")
    make_partner()
    # Only construct history for deletion checks; no business/model execution.
    monkeypatch.setattr(development_engine, 'prepare', lambda *a, **kw: {})
    task = development_lifecycle.create(Submit(submission_id="history-model", request=DevelopmentRequest(
        target_partner_id="partner-1", development_direction="合成测试方向",
    )), owner)
    model_id = add_model()
    model_config.toggle_enable(model_id, False)
    with get_db() as conn:
        conn.execute("UPDATE development_runs SET model_config_id=?,status=? WHERE id=?", (model_id, run_status, task["run_id"]))
        if run_status == "ready":
            conn.execute("""INSERT INTO development_versions (id,plan_id,version_no,run_id,payload_json,dependency_json,created_by,created_at)
                VALUES ('history-version',?,1,?,'{"summary":"synthetic history"}','{}',?,'2026-09-27')""", (task["plan_id"], task["run_id"], owner["id"]))
            conn.execute("UPDATE development_plans SET current_version_id='history-version',active_run_id=NULL WHERE id=?", (task["plan_id"],))
        original_run = dict(conn.execute("SELECT * FROM development_runs WHERE id=?", (task["run_id"],)).fetchone())
        original_plan = dict(conn.execute("SELECT * FROM development_plans WHERE id=?", (task["plan_id"],)).fetchone())
    headers = auth_headers(make_user("history_admin", role="admin"))
    if fail_audit:
        def unavailable_audit(*args, **kwargs):
            raise RuntimeError("synthetic audit failure")
        monkeypatch.setattr(model_config, "record_audit", unavailable_audit)
    response = client_no_raise.delete(f"/admin/model-configs/{model_id}", headers=headers)
    deleted = not fail_audit
    assert response.status_code == (204 if deleted else 500)
    with get_db() as conn:
        assert dict(conn.execute("SELECT * FROM development_runs WHERE id=?", (task["run_id"],)).fetchone()) == {**original_run, "model_config_id": None if deleted else model_id}
        assert dict(conn.execute("SELECT * FROM development_plans WHERE id=?", (task["plan_id"],)).fetchone()) == original_plan
        assert bool(conn.execute("SELECT id FROM model_configs WHERE id=?", (model_id,)).fetchone()) is not deleted
        if run_status == "ready":
            assert json.loads(conn.execute("SELECT payload_json FROM development_versions WHERE id='history-version'").fetchone()[0]) == {"summary":"synthetic history"}
        audit = conn.execute("SELECT summary FROM user_audit_logs WHERE action='model_config_deleted'").fetchone()
        if deleted:
            assert json.loads(audit[0])["historical_run_ids"] == [task["run_id"]]
            assert json.loads(audit[0])["model_name"] == "model-a"
        else:
            assert audit is None


def test_unbound_priority_is_preserved():
    with pytest.raises(model_resolver.ModelConfigurationError, match="没有启用"):
        model_resolver.resolve_model_config("partner_match")
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
    with pytest.raises(model_resolver.ModelConfigurationError, match="场景首选或系统默认"):
        model_resolver.resolve_model_config("partner_match")


@pytest.mark.parametrize("scene", ["partner_match", "partner_development", "default"])
@pytest.mark.parametrize("missing", [False, True])
def test_unavailable_preference_routes_to_enabled_model(scene, missing):
    model_id = add_model()
    model_config.toggle_enable(model_id, False)
    model_config.set_default(add_model("available-fallback"))
    bind(scene, "missing-id" if missing else model_id)
    assert model_resolver.resolve_model_config(scene).model == "available-fallback"
    from backend.app import development_model
    assert development_model.configuration()["model_name"] == "available-fallback"


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
    assert "暂无可用模型" in message


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


@pytest.mark.parametrize("timeout,expected", [(None, 123), (60, 60), (180, 123)])
def test_client_honors_configured_timeout_and_sends_zero(monkeypatch, timeout, expected):
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


def test_separate_admin_maintenance_calls_use_their_scenes(monkeypatch):
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
    assert calls == [
        ("partner_profile", 60), ("partner_profile", 90), ("demand_profile", 30),
        ("tag_suggestion", 30), ("demand_profile", 60), ("tag_suggestion", 30),
    ]


@pytest.mark.parametrize("scene,path", [
    ("partner_match", "/agent/match"), ("partner_profile", "/partners/partner-1/profile"),
    ("tag_suggestion", "/admin/capability-tags/suggestions/scan"),
])
def test_no_enabled_model_returns_actionable_error_without_calling_model(client, scene, path):
    make_partner()
    admin = make_user("unavailable_admin", role="admin")
    make_task(admin, "scan input")
    bind(scene, "missing-config")
    response = client.post(path, headers=auth_headers(admin), json={"requirement": "寻找测试伙伴"})
    assert response.status_code == 503
    assert response.json()["detail"] == "服务异常，请联系管理员。"
    from backend.app.error_diagnostics import recent_errors
    errors=recent_errors()
    assert any('没有启用的模型配置' in item['message'] for item in errors)
