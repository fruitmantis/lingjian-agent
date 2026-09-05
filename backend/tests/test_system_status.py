"""Read-only status checks report evidence and never probe external models."""
import hashlib
import sqlite3
from contextlib import contextmanager

import httpx
import pytest

from backend.app import database
from backend.app.database import get_db, get_readonly_db
from backend.app.routers import system
from .conftest import auth_headers, make_user


@pytest.fixture(autouse=True)
def synthetic_configuration(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "")
    with get_db() as conn:
        conn.execute("UPDATE model_usage_configs SET model_config_id = NULL")
        conn.execute("UPDATE model_configs SET api_key = 'synthetic-db-key', api_key_source = 'db', base_url = 'https://model.invalid/v1', model_name = 'synthetic-model', enabled = 1")
    def must_not_call(*args, **kwargs):
        pytest.fail("read-only system status called a model")
    monkeypatch.setattr(httpx.Client, "post", must_not_call)


def test_repeated_status_does_not_write_database_or_call_model(client):
    admin = make_user("status_admin", role="admin")
    headers = auth_headers(admin)
    before = hashlib.sha256(database.DATABASE_PATH.read_bytes()).hexdigest()
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
    assert hashlib.sha256(database.DATABASE_PATH.read_bytes()).hexdigest() == before
    with get_readonly_db() as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name = '_health_check'").fetchone() is None


def test_readonly_connection_refuses_writes():
    with get_readonly_db() as conn:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("CREATE TABLE forbidden_write (id INTEGER)")


def test_missing_database_is_not_created(monkeypatch, tmp_path):
    target = tmp_path / "missing.db"
    monkeypatch.setattr(database, "DATABASE_PATH", target)
    items, has_error = system._check_database()
    assert has_error and items[0].status == "error"
    assert not target.exists()
    assert str(target) not in items[0].message


def test_status_does_not_change_existing_health_table(client):
    admin = make_user("legacy_status_admin", role="admin")
    with get_db() as conn:
        conn.execute("CREATE TABLE _health_check (id INTEGER)")
        conn.execute("INSERT INTO _health_check VALUES (42)")
    before = database.DATABASE_PATH.read_bytes()
    assert client.get("/admin/system/status", headers=auth_headers(admin)).status_code == 200
    assert database.DATABASE_PATH.read_bytes() == before


def test_business_status_uses_scene_binding_not_environment(client):
    admin = make_user("scene_status_admin", role="admin")
    with get_db() as conn:
        conn.execute("UPDATE model_usage_configs SET model_config_id = 'missing' WHERE scene_key = 'partner_profile'")
    data = client.get("/admin/system/status", headers=auth_headers(admin)).json()
    states = {item["name"]: item for item in data["businessCapabilities"]}
    assert states["伙伴画像生成"]["status"] == "error"
    assert states["智能匹配"]["status"] == "unknown"
    assert data["overallStatus"] == "partial"
    assert "绑定" in states["伙伴画像生成"]["message"]


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
    admin = make_user("address_admin", role="admin")
    with get_db() as conn:
        conn.execute("UPDATE model_configs SET base_url = 'https://synthetic-user:synthetic-password@model.invalid/v1/private?token=synthetic-query'")
    response = client.get("/admin/system/status", headers=auth_headers(admin))
    assert response.status_code == 200
    assert "https://model.invalid" in response.text
    for marker in ("synthetic-user", "synthetic-password", "synthetic-query", "/v1/private"):
        assert marker not in response.text


@pytest.mark.parametrize("url", ["malformed-synthetic-secret", "https://model.invalid:bad/private-key", "file:///private/secret"])
def test_invalid_url_is_reported_without_echoing_configuration(client, url):
    admin = make_user("invalid_url_admin", role="admin")
    with get_db() as conn:
        conn.execute("UPDATE model_configs SET base_url = ?", (url,))
    response = client.get("/admin/system/status", headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()["overallStatus"] == "partial"
    assert url not in response.text


def test_status_remains_admin_only(client):
    user = make_user("status_user")
    assert client.get("/admin/system/status").status_code == 401
    assert client.get("/admin/system/status", headers=auth_headers(user)).status_code == 403


@pytest.mark.parametrize("field,value", [("temperature", "bad-value"), ("top_p", 2), ("max_tokens", 1.5), ("timeout_seconds", -1)])
def test_legacy_invalid_numeric_configuration_does_not_break_status(client, field, value):
    admin = make_user("numeric_status_admin", role="admin")
    with get_db() as conn:
        conn.execute(f"UPDATE model_configs SET {field} = ?", (value,))
    response = client.get("/admin/system/status", headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()["overallStatus"] == "partial"
    assert "模型参数无效" in response.text
    assert "bad-value" not in response.text
