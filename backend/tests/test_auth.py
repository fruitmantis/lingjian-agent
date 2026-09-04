import os
from datetime import datetime, timezone

import jwt
import pytest

from backend.app.auth import ALGORITHM, create_token
from backend.app.database import get_db
from backend.app.main import initialize_application

from .conftest import BOOTSTRAP_PASSWORD, TEST_JWT_SECRET, auth_headers, make_user


def test_auth_001_secret_rotation_invalidates_old_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    token = create_token("user-1", "user", "user")
    assert jwt.decode(token, TEST_JWT_SECRET, algorithms=[ALGORITHM])["sub"] == "user-1"
    monkeypatch.setenv("JWT_SECRET_KEY", "validation-secret-b-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, os.environ["JWT_SECRET_KEY"], algorithms=[ALGORITHM])


def test_auth_002_historical_secret_cannot_forge_admin(client, monkeypatch):
    admin = make_user("secure_admin", role="admin")
    forged = jwt.encode(
        {
            "sub": admin["id"], "username": admin["username"], "role": "admin", "ver": 0,
            "exp": datetime(2999, 1, 1, tzinfo=timezone.utc),
        },
        "lingjian-mvp-secret-key-change-in-production",
        algorithm=ALGORITHM,
    )
    response = client.get("/admin/users", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_auth_003_missing_or_weak_secret_fails_startup(monkeypatch):
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY is required"):
        initialize_application()
    monkeypatch.setenv("JWT_SECRET_KEY", "too-short")
    with pytest.raises(RuntimeError, match="weak"):
        initialize_application()


def test_auth_004_005_bootstrap_requires_config_and_forces_password_change(client):
    response = client.post("/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 401
    response = client.post(
        "/auth/login",
        json={"username": "bootstrap_admin", "password": BOOTSTRAP_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["user"]["must_change_password"] is True
    token = response.json()["access_token"]
    assert client.get("/admin/users", headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_auth_005_empty_database_without_bootstrap_password_fails(monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="BOOTSTRAP_ADMIN_PASSWORD"):
        initialize_application()
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_auth_010_login_success(client):
    user = make_user("login_user")
    response = client.post("/auth/login", json={"username": user["username"], "password": user["password"]})
    assert response.status_code == 200
    assert response.json()["user"]["username"] == user["username"]


def test_auth_011_012_five_failures_lock_account(client):
    user = make_user("lock_me")
    for _ in range(5):
        assert client.post("/auth/login", json={"username": user["username"], "password": "wrong"}).status_code == 401
    response = client.post("/auth/login", json={"username": user["username"], "password": user["password"]})
    assert response.status_code == 423


def test_auth_013_admin_unlock_restores_login(client):
    admin = make_user("unlock_admin", role="admin")
    user = make_user("unlock_user", locked_until="2999-01-01T00:00:00+00:00")
    assert client.post("/auth/login", json={"username": user["username"], "password": user["password"]}).status_code == 423
    response = client.post(f"/admin/users/{user['id']}/unlock", headers=auth_headers(admin))
    assert response.status_code == 200
    assert client.post("/auth/login", json={"username": user["username"], "password": user["password"]}).status_code == 200


def test_auth_014_first_login_cannot_use_business_routes(client):
    user = make_user("first_login", must_change_password=1)
    login = client.post("/auth/login", json={"username": user["username"], "password": user["password"]})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert client.get("/agent/tasks", headers=headers).status_code == 403
    assert client.get("/auth/me", headers=headers).status_code == 200


def test_auth_015_password_change_invalidates_old_token(client):
    user = make_user("change_password")
    old_headers = auth_headers(user)
    response = client.post(
        "/auth/change-password", headers=old_headers,
        json={"current_password": user["password"], "new_password": "NewValidationPass456"},
    )
    assert response.status_code == 200
    assert client.get("/auth/me", headers=old_headers).status_code == 401
    new_token = response.json()["access_token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {new_token}"}).status_code == 200


def test_auth_016_reset_password_invalidates_old_token(client):
    admin = make_user("reset_admin", role="admin")
    user = make_user("reset_user")
    old_headers = auth_headers(user)
    response = client.post(f"/admin/users/{user['id']}/reset-password", headers=auth_headers(admin))
    assert response.status_code == 200
    assert client.get("/auth/me", headers=old_headers).status_code == 401


def test_auth_017_disable_invalidates_old_token(client):
    admin = make_user("disable_admin", role="admin")
    user = make_user("disable_user")
    old_headers = auth_headers(user)
    response = client.patch(
        f"/admin/users/{user['id']}/status", headers=auth_headers(admin), json={"status": "disabled"},
    )
    assert response.status_code == 200
    assert client.get("/auth/me", headers=old_headers).status_code == 401


def test_auth_018_role_change_invalidates_old_token(client):
    admin = make_user("role_admin", role="admin")
    user = make_user("role_user")
    old_headers = auth_headers(user)
    response = client.patch(
        f"/admin/users/{user['id']}", headers=auth_headers(admin), json={"role": "admin"},
    )
    assert response.status_code == 200
    assert client.get("/auth/me", headers=old_headers).status_code == 401


def test_auth_019_020_admin_cannot_disable_or_demote_self(client):
    admin = make_user("self_admin", role="admin")
    headers = auth_headers(admin)
    assert client.patch(f"/admin/users/{admin['id']}/status", headers=headers, json={"status": "disabled"}).status_code == 400
    assert client.patch(f"/admin/users/{admin['id']}", headers=headers, json={"role": "user"}).status_code == 400


def test_auth_021_last_active_admin_is_preserved(client):
    with get_db() as conn:
        conn.execute("DELETE FROM users")
    admin = make_user("only_admin", role="admin")
    other = make_user("ordinary")
    headers = auth_headers(admin)
    assert client.patch(f"/admin/users/{admin['id']}/status", headers=headers, json={"status": "disabled"}).status_code == 400
    assert client.patch(f"/admin/users/{admin['id']}", headers=headers, json={"role": "user"}).status_code == 400
    assert client.patch(f"/admin/users/{other['id']}", headers=headers, json={"role": "admin"}).status_code == 200
