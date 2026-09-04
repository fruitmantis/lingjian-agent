from concurrent.futures import ThreadPoolExecutor

from backend.app.auth import verify_password
from backend.app.database import get_db
from backend.app.routers import users as users_router

from .conftest import auth_headers, make_user


def application_payload(index: int = 1, **overrides) -> dict:
    payload = {
        "username": f"applicant_{index}",
        "display_name": f"申请人 {index}",
        "department": "解决方案部",
        "contact": f"applicant_{index}@company.example",
        "reason": "验证内部账号申请",
        "password": "ApplicantPass123",
    }
    payload.update(overrides)
    return payload


def test_application_001_public_application_hashes_password(client):
    payload = application_payload()
    response = client.post("/auth/user-applications", json=payload)
    assert response.status_code == 201
    with get_db() as conn:
        row = conn.execute("SELECT * FROM user_applications WHERE id = ?", (response.json()["id"],)).fetchone()
        assert row["status"] == "pending"
        assert row["password_hash"] != payload["password"]
        assert verify_password(payload["password"], row["password_hash"])
        assert payload["password"] not in " ".join(str(value) for value in row)


def test_application_002_duplicate_username_is_rejected(client):
    assert client.post("/auth/user-applications", json=application_payload()).status_code == 201
    duplicate = application_payload(2, username="APPLICANT_1")
    assert client.post("/auth/user-applications", json=duplicate).status_code == 409


def test_application_003_duplicate_contact_is_rejected(client):
    assert client.post("/auth/user-applications", json=application_payload()).status_code == 201
    duplicate = application_payload(2, contact="APPLICANT_1@COMPANY.EXAMPLE")
    assert client.post("/auth/user-applications", json=duplicate).status_code == 409


def test_application_004_admin_approval_creates_first_login_user(client):
    admin = make_user("application_admin", role="admin")
    application_id = client.post("/auth/user-applications", json=application_payload()).json()["id"]
    response = client.post(
        f"/admin/user-applications/{application_id}/approve",
        headers=auth_headers(admin), json={"note": "身份已核验"},
    )
    assert response.status_code == 200
    assert response.json()["must_change_password"] is True
    with get_db() as conn:
        application = conn.execute("SELECT * FROM user_applications WHERE id = ?", (application_id,)).fetchone()
        assert application["status"] == "approved"
        assert application["password_hash"] is None
        assert application["user_id"] == response.json()["id"]
        assert conn.execute("SELECT COUNT(*) FROM users WHERE username = 'applicant_1'").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM user_audit_logs WHERE action = 'admin.user_application_approved'").fetchone()[0] == 1


def test_application_005_rejection_clears_hash_and_creates_no_user(client):
    admin = make_user("reject_admin", role="admin")
    application_id = client.post("/auth/user-applications", json=application_payload()).json()["id"]
    response = client.post(
        f"/admin/user-applications/{application_id}/reject",
        headers=auth_headers(admin), json={"note": "身份未通过"},
    )
    assert response.status_code == 200
    with get_db() as conn:
        application = conn.execute("SELECT * FROM user_applications WHERE id = ?", (application_id,)).fetchone()
        assert application["status"] == "rejected"
        assert application["password_hash"] is None
        assert conn.execute("SELECT COUNT(*) FROM users WHERE username = 'applicant_1'").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM user_audit_logs WHERE action = 'admin.user_application_rejected'").fetchone()[0] == 1


def test_application_006_concurrent_approval_creates_one_user(client):
    admin1 = make_user("approval_admin_1", role="admin")
    admin2 = make_user("approval_admin_2", role="admin")
    application_id = client.post("/auth/user-applications", json=application_payload()).json()["id"]

    def approve(admin):
        return client.post(
            f"/admin/user-applications/{application_id}/approve",
            headers=auth_headers(admin), json={"note": None},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(approve, [admin1, admin2]))
    assert statuses == [200, 409]
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users WHERE username = 'applicant_1'").fetchone()[0] == 1


def test_application_007_rapid_requests_are_rate_limited(client, monkeypatch):
    monkeypatch.setenv("USER_APPLICATION_RATE_LIMIT", "2")
    monkeypatch.setenv("USER_APPLICATION_RATE_WINDOW_SECONDS", "60")
    users_router._APPLICATION_ATTEMPTS.clear()
    assert client.post("/auth/user-applications", json=application_payload(1)).status_code == 201
    assert client.post("/auth/user-applications", json=application_payload(2)).status_code == 201
    response = client.post("/auth/user-applications", json=application_payload(3))
    assert response.status_code == 429
    assert "Retry-After" in response.headers


def test_application_pending_capacity_is_rate_limited(client, monkeypatch):
    monkeypatch.setenv("USER_APPLICATION_PENDING_LIMIT", "1")
    assert client.post("/auth/user-applications", json=application_payload(1)).status_code == 201
    assert client.post("/auth/user-applications", json=application_payload(2)).status_code == 429
