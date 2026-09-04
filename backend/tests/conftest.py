import os
import shutil
import sys
import tempfile
import uuid
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest


TEST_ROOT = Path(tempfile.mkdtemp(prefix="lingjian-pytest-"))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
TEST_DB = TEST_ROOT / "app.db"
TEST_UPLOADS = TEST_ROOT / "uploads"
TEST_CHROMA = TEST_ROOT / "chroma"
TEST_JWT_SECRET = "validation-secret-a-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
BOOTSTRAP_PASSWORD = "BootstrapPass12345"

os.environ["LINGJIAN_DATABASE_PATH"] = str(TEST_DB)
os.environ["LINGJIAN_UPLOADS_DIR"] = str(TEST_UPLOADS)
os.environ["LINGJIAN_CHROMA_DIR"] = str(TEST_CHROMA)
os.environ["JWT_SECRET_KEY"] = TEST_JWT_SECRET
os.environ["BOOTSTRAP_ADMIN_USERNAME"] = "bootstrap_admin"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = BOOTSTRAP_PASSWORD
os.environ["USER_APPLICATION_RATE_LIMIT"] = "1000"
os.environ["USER_APPLICATION_PENDING_LIMIT"] = "200"

import httpx  # noqa: E402

from backend.app.auth import create_token, hash_password  # noqa: E402
from backend.app.database import DATABASE_PATH, UPLOADS_DIR, get_db, initialize_storage  # noqa: E402
from backend.app.main import app, initialize_application  # noqa: E402
from backend.app.routers import users as users_router  # noqa: E402


DEFAULT_PASSWORD = "ValidationPass123"


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_root():
    yield
    shutil.rmtree(TEST_ROOT, ignore_errors=True)


@pytest.fixture(autouse=True)
def fresh_database(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_USERNAME", "bootstrap_admin")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", BOOTSTRAP_PASSWORD)
    monkeypatch.setenv("USER_APPLICATION_RATE_LIMIT", "1000")
    monkeypatch.setenv("USER_APPLICATION_PENDING_LIMIT", "200")
    if DATABASE_PATH.exists():
        DATABASE_PATH.unlink()
    shutil.rmtree(UPLOADS_DIR, ignore_errors=True)
    users_router._APPLICATION_ATTEMPTS.clear()
    initialize_storage()
    yield


@pytest.fixture
def client():
    initialize_application()
    yield SyncASGIClient()


@pytest.fixture
def client_no_raise():
    initialize_application()
    yield SyncASGIClient(raise_app_exceptions=False)


class SyncASGIClient:
    """Small synchronous facade over HTTPX's async in-process ASGI transport."""

    def __init__(self, *, raise_app_exceptions: bool = True):
        self.raise_app_exceptions = raise_app_exceptions

    def request(self, method: str, url: str, **kwargs):
        async def send():
            transport = httpx.ASGITransport(
                app=app, raise_app_exceptions=self.raise_app_exceptions,
            )
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver", follow_redirects=False,
            ) as async_client:
                return await async_client.request(method, url, **kwargs)

        return asyncio.run(send())

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs):
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs):
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self.request("DELETE", url, **kwargs)


def make_user(
    username: str,
    *,
    role: str = "user",
    status: str = "active",
    must_change_password: int = 0,
    password: str = DEFAULT_PASSWORD,
    locked_until: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    user_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            """INSERT INTO users
               (id, username, hashed_password, display_name, department, role, status,
                must_change_password, token_version, last_login_at, failed_login_count,
                locked_until, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'Validation', ?, ?, ?, 0, NULL, 0, ?, ?, ?)""",
            (
                user_id, username, hash_password(password), username, role, status,
                must_change_password, locked_until, now, now,
            ),
        )
    return {"id": user_id, "username": username, "role": role, "password": password}


def auth_headers(user: dict, *, token_version: int = 0) -> dict[str, str]:
    token = create_token(user["id"], user["username"], user["role"], token_version)
    return {"Authorization": f"Bearer {token}"}


def recommendation(partner_id: str = "partner-1", partner_name: str = "验证伙伴") -> dict:
    return {
        "partnerId": partner_id,
        "partnerName": partner_name,
        "matchScore": "92",
        "matchedCapabilities": "AI",
        "matchedIndustries": "制造",
        "matchedRegions": "全国",
        "recommendationReason": "验证推荐",
        "evidenceCases": "验证案例",
        "evidenceDeliverables": "验证交付物",
        "riskNotes": "资料需复核",
    }


def make_partner(partner_id: str = "partner-1", name: str = "验证伙伴") -> dict:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO partners
               (id, name, intro, capabilities, service_areas, industries, ai_profile, status, created_at, updated_at)
               VALUES (?, ?, '测试伙伴', 'AI,数据治理', '全国', '制造', NULL, 'active', ?, ?)""",
            (partner_id, name, now, now),
        )
    return {"id": partner_id, "name": name}


def make_task(
    owner: dict,
    label: str,
    *,
    task_status: str = "ready",
    archived: bool = False,
    recommendations: list[dict] | None = None,
    updated_at: str | None = None,
) -> str:
    import json

    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    archived_at = now if archived else None
    recs = [recommendation()] if recommendations is None else recommendations
    with get_db() as conn:
        conn.execute(
            """INSERT INTO match_records
               (id, requirement, recommendations_json, created_at, created_by, owner_user_id,
                archived_at, task_status, last_error_stage, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_id, label, json.dumps(recs, ensure_ascii=False), now, owner["username"],
                owner["id"], archived_at, task_status,
                "partner_match" if task_status == "failed" else ("project_opportunity" if task_status == "partial" else None),
                updated_at or now,
            ),
        )
    return task_id


@pytest.fixture
def identity_set(client):
    admin1 = make_user("admin1", role="admin")
    admin2 = make_user("admin2", role="admin")
    user_a = make_user("user_a")
    user_b = make_user("user_b")
    first_login = make_user("user_first_login", must_change_password=1)
    disabled = make_user("user_disabled", status="disabled")
    locked = make_user(
        "user_locked", locked_until="2999-01-01T00:00:00+00:00",
    )
    return {
        "admin1": admin1,
        "admin2": admin2,
        "user_a": user_a,
        "user_b": user_b,
        "first_login": first_login,
        "disabled": disabled,
        "locked": locked,
    }
