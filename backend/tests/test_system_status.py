"""Read-only status checks report evidence and never probe external models."""
import hashlib
from sqlalchemy.exc import DBAPIError
from .postgres_support import snapshot
from contextlib import contextmanager

import httpx
import pytest

from backend.app import database,model_resolver
from backend.app.database import get_db, get_readonly_db
from backend.app.routers import system
from .conftest import auth_headers, make_user


@pytest.fixture(autouse=True)
def synthetic_configuration(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    with get_db() as conn:
        conn.execute("UPDATE model_usage_configs SET model_config_id = NULL")
        conn.execute("UPDATE model_providers SET api_key = 'synthetic-db-key', api_key_source = 'db', base_url = 'http://127.0.0.1:18180/v1'")
        conn.execute("UPDATE model_configs SET model_name='synthetic-model',enabled=1")
    def must_not_call(*args, **kwargs):
        pytest.fail("read-only system status called a model")
    monkeypatch.setattr(httpx.Client, "post", must_not_call)
    monkeypatch.setattr(httpx.AsyncClient, "post", must_not_call)


def test_repeated_status_does_not_write_database_or_call_model(client):
    admin = make_user("status_admin", role="admin")
    headers = auth_headers(admin)
    with get_db() as conn:conn.execute("DROP TABLE _health_check")
    before = db_snapshot()
    for _ in range(3):
        response = client.get("/admin/system/status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["overallStatus"] == "unknown"
        assert data["summary"]["errorCount"] == 0
        assert all(item["status"] == "unknown" for item in data["businessCapabilities"])
        assert any(item["name"] == "模型调用状态" and item["status"] == "unknown" for item in data["llm"])
        items = data["services"] + data["database"] + data["llm"] + data["businessCapabilities"]
        for value in ("normal", "warning", "error", "unknown"):
            assert data["summary"][f"{value}Count"] == sum(i["status"] == value for i in items)
        assert "synthetic-db-key" not in response.text
    assert db_snapshot() == before
    with get_readonly_db() as conn:
        assert conn.execute("SELECT tablename FROM pg_tables WHERE schemaname=current_schema() AND tablename='_health_check'").fetchone() is None


def test_readonly_connection_refuses_writes():
    with get_readonly_db() as conn:
        with pytest.raises(DBAPIError, match="read-only"):
            conn.execute("CREATE TABLE forbidden_write (id INTEGER)")


def test_missing_database_is_not_created(monkeypatch, tmp_path):
    target = tmp_path / "missing.db"
    monkeypatch.delenv("DATABASE_URL")
    items, has_error = system._check_database()
    assert has_error and items[0].status == "error"
    assert not target.exists()
    assert str(target) not in items[0].message


def test_status_does_not_change_existing_health_table(client):
    admin = make_user("legacy_status_admin", role="admin")
    with get_db() as conn:
        conn.execute("INSERT INTO _health_check VALUES (42)")
    before = db_snapshot()
    assert client.get("/admin/system/status", headers=auth_headers(admin)).status_code == 200
    assert db_snapshot() == before


def test_business_status_uses_fallback_when_scene_preference_is_missing(client):
    admin = make_user("scene_status_admin", role="admin")
    with get_db() as conn:
        conn.execute("UPDATE model_usage_configs SET model_config_id = 'missing' WHERE scene_key = 'partner_profile'")
    data = client.get("/admin/system/status", headers=auth_headers(admin)).json()
    states = {item["name"]: item for item in data["businessCapabilities"]}
    assert states["伙伴画像生成"]["status"] == "unknown"
    assert states["伙伴推荐"]["status"] == "unknown"
    assert data["overallStatus"] == "unknown"


def test_default_binding_error_and_database_error_are_sanitized(client, monkeypatch):
    admin = make_user("error_status_admin", role="admin")
    @contextmanager
    def broken_db():
        raise RuntimeError("synthetic-secret /private/customer-data/app.db")
        yield
    monkeypatch.setattr(system, "get_readonly_db", broken_db)
    data = client.get("/admin/system/status", headers=auth_headers(admin)).json()
    assert data["overallStatus"] == "error"
    assert "synthetic-secret" not in str(data) and "/private/" not in str(data)


def test_connection_address_omits_credentials_path_and_query(client):
    """Valid base URLs may contain a private path; status exposes only the origin."""
    admin = make_user("address_admin", role="admin")
    with get_db() as conn:
        conn.execute("UPDATE model_providers SET base_url = 'https://model.invalid/v1/private'")
    before = db_snapshot()
    response = client.get("/admin/system/status", headers=auth_headers(admin))
    assert response.status_code == 200
    data = response.json()
    endpoint = next(item for item in data["llm"] if item["name"] == "模型接口地址")
    assert endpoint["status"] == "normal"
    assert endpoint["message"] == "https://model.invalid"
    assert data["overallStatus"] == "unknown"  # Configured, never actively probed.
    for marker in ("synthetic-db-key", "synthetic-user", "synthetic-password", "synthetic-query", "/v1/private"):
        assert marker not in response.text
    assert db_snapshot() == before


@pytest.mark.parametrize("url", [
    "malformed-synthetic-secret", "https://model.invalid:bad/private-key", "file:///private/secret",
    "https://synthetic-user:synthetic-password@model.invalid/v1/private?token=synthetic-query",
    "https://synthetic-user:synthetic-password@model.invalid/v1/private",
    "https://model.invalid/v1/private?token=synthetic-query",
    "https://model.invalid/v1/private#synthetic-fragment",
])
def test_invalid_url_is_reported_without_echoing_configuration(client, url):
    """Invalid legacy URLs fail resolution; APIs reject new ones without writing or inference."""
    admin = make_user("invalid_url_admin", role="admin")
    headers = auth_headers(admin)
    with get_db() as conn:
        conn.execute("UPDATE model_providers SET base_url = ?", (url,))
        record = dict(conn.execute(model_resolver.MODEL_SELECT + " LIMIT 1").fetchone())
    before = db_snapshot()
    with pytest.raises(model_resolver.ModelConfigurationError, match="HTTP"):
        model_resolver.model_config_from_record(record)
    response = client.get("/admin/system/status", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["overallStatus"] == "partial"
    config = next(item for item in data["llm"] if item["name"] == "模型配置")
    assert config["status"] == "error"
    assert "暂无可用模型" in config["message"]
    rejected = client.post("/admin/model-providers", headers=headers,
        json={"name": "invalid-synthetic-provider", "baseUrl": url, "apiKey": "synthetic-rejected-key"})
    assert rejected.status_code == 422
    for marker in (url, "synthetic-db-key", "synthetic-rejected-key", "synthetic-user",
                   "synthetic-password", "synthetic-query", "synthetic-fragment", "/v1/private", "/private/secret"):
        assert marker not in response.text
        assert marker not in rejected.text
    assert db_snapshot() == before


def test_status_remains_admin_only(client):
    user = make_user("status_user")
    assert client.get("/admin/system/status").status_code == 401
    assert client.get("/admin/system/status", headers=auth_headers(user)).status_code == 403


@pytest.mark.parametrize("field,value", [("temperature", -1), ("top_p", 2), ("max_tokens", -1)])
def test_legacy_invalid_numeric_configuration_does_not_break_status(client, field, value):
    admin = make_user("numeric_status_admin", role="admin")
    with get_db() as conn:
        conn.execute(f"UPDATE model_configs SET {field} = ?", (value,))
    response = client.get("/admin/system/status", headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()["overallStatus"] == "partial"
    assert "模型参数无效" in response.text
    assert "bad-value" not in response.text


def db_snapshot():
    with get_readonly_db() as conn: return snapshot(conn)
