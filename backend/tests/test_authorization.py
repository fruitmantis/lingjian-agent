import re
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.database import get_db
from backend.app.routers import match as match_router

from .conftest import auth_headers, make_partner, make_task, make_user, recommendation


def add_opportunity(task_id: str, suffix: str) -> str:
    opportunity_id = f"opportunity-{suffix}"
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO project_opportunities
               (id, match_record_id, requirement_text, customer_name, project_name,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (opportunity_id, task_id, f"需求-{suffix}", f"客户-{suffix}", f"项目-{suffix}", now, now),
        )
        conn.execute(
            """INSERT INTO demand_profiles
               (id, match_record_id, requirement_text, matched_partner_count, created_at)
               VALUES (?, ?, ?, 1, ?)""",
            (f"demand-{suffix}", task_id, f"需求-{suffix}", now),
        )
    return opportunity_id


def task_matrix(identity_set):
    a = identity_set["user_a"]
    b = identity_set["user_b"]
    result = {}
    for owner, prefix in [(a, "A"), (b, "B")]:
        for status in ["ready", "failed", "partial"]:
            result[f"{prefix}-{status}"] = make_task(
                owner, f"{prefix}-{status}", task_status=status,
                recommendations=[] if status == "failed" else None,
            )
        result[f"{prefix}-archived"] = make_task(owner, f"{prefix}-archived", archived=True)
    add_opportunity(result["A-ready"], "a")
    add_opportunity(result["B-ready"], "b")
    return result


def test_ab_task_lists_are_isolated(client, identity_set):
    tasks = task_matrix(identity_set)
    a = identity_set["user_a"]
    b = identity_set["user_b"]
    admin = identity_set["admin1"]

    a_items = client.get("/agent/tasks?status=active&pageSize=100", headers=auth_headers(a)).json()["items"]
    b_items = client.get("/agent/tasks?status=active&pageSize=100", headers=auth_headers(b)).json()["items"]
    admin_items = client.get("/admin/tasks?status=active&pageSize=100", headers=auth_headers(admin)).json()["items"]
    assert {item["id"] for item in a_items} == {tasks["A-ready"], tasks["A-failed"], tasks["A-partial"]}
    assert {item["id"] for item in b_items} == {tasks["B-ready"], tasks["B-failed"], tasks["B-partial"]}
    assert {tasks["A-ready"], tasks["B-ready"]}.issubset({item["id"] for item in admin_items})
    assert client.get("/agent/tasks?status=archived", headers=auth_headers(a)).json()["items"][0]["id"] == tasks["A-archived"]


def test_ab_detail_and_related_data_are_isolated(client, identity_set):
    tasks = task_matrix(identity_set)
    a_headers = auth_headers(identity_set["user_a"])
    b_headers = auth_headers(identity_set["user_b"])
    admin_headers = auth_headers(identity_set["admin1"])
    own = client.get(f"/agent/tasks/{tasks['A-ready']}", headers=a_headers)
    assert own.status_code == 200
    assert own.json()["demandProfile"]["id"] == "demand-a"
    assert own.json()["opportunity"]["id"] == "opportunity-a"
    assert client.get(f"/agent/tasks/{tasks['B-ready']}", headers=a_headers).status_code == 404
    assert client.get(f"/agent/tasks/{tasks['A-ready']}", headers=b_headers).status_code == 404
    assert client.get(f"/agent/tasks/{tasks['B-ready']}", headers=admin_headers).status_code == 200


def test_ab_archive_restore_are_isolated(client, identity_set):
    tasks = task_matrix(identity_set)
    a_headers = auth_headers(identity_set["user_a"])
    b_headers = auth_headers(identity_set["user_b"])
    assert client.patch(f"/agent/tasks/{tasks['B-ready']}/archive", headers=a_headers).status_code == 404
    assert client.patch(f"/agent/tasks/{tasks['A-ready']}/archive", headers=a_headers).status_code == 204
    assert client.patch(f"/agent/tasks/{tasks['A-ready']}/restore", headers=b_headers).status_code == 404
    assert client.patch(f"/agent/tasks/{tasks['A-ready']}/restore", headers=a_headers).status_code == 204


def test_ab_retry_is_isolated(client, identity_set, monkeypatch):
    make_partner()
    tasks = task_matrix(identity_set)
    a_headers = auth_headers(identity_set["user_a"])
    b_headers = auth_headers(identity_set["user_b"])
    assert client.post(f"/agent/tasks/{tasks['B-failed']}/retry", headers=a_headers).status_code == 404

    rec = match_router.PartnerRecommendation.model_validate(recommendation())
    monkeypatch.setattr(match_router, "_perform_partner_match", lambda _: [rec])

    def finish(record_id, *_args, **_kwargs):
        match_router._set_task_state(record_id, "ready")
        return "ready"

    monkeypatch.setattr(match_router, "_run_task_enrichment", finish)
    assert client.post(f"/agent/tasks/{tasks['B-failed']}/retry", headers=b_headers).status_code == 200


def test_ab_opportunity_edit_is_isolated(client, identity_set):
    tasks = task_matrix(identity_set)
    a_headers = auth_headers(identity_set["user_a"])
    b_headers = auth_headers(identity_set["user_b"])
    assert client.patch(
        f"/agent/tasks/{tasks['B-ready']}/opportunity", headers=a_headers,
        json={"projectName": "越权修改"},
    ).status_code == 404
    response = client.patch(
        f"/agent/tasks/{tasks['A-ready']}/opportunity", headers=a_headers,
        json={"projectName": "A 更新项目"},
    )
    assert response.status_code == 200
    assert response.json()["projectName"] == "A 更新项目"
    assert client.patch(
        f"/agent/tasks/{tasks['A-ready']}/opportunity", headers=b_headers,
        json={"projectName": "B 越权修改"},
    ).status_code == 404


def test_every_admin_operation_rejects_ordinary_user(client, identity_set):
    headers = auth_headers(identity_set["user_a"])
    schema = client.get("/openapi.json").json()
    checked = []
    for path, path_item in schema["paths"].items():
        if not path.startswith("/admin"):
            continue
        concrete = re.sub(r"\{[^}]+\}", "validation-id", path)
        for method in path_item:
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            kwargs = {"headers": headers}
            if method.lower() in {"post", "put", "patch"}:
                kwargs["json"] = {}
            response = client.request(method.upper(), concrete, **kwargs)
            assert response.status_code == 403, f"{method.upper()} {path} returned {response.status_code}"
            checked.append((method, path))
    assert len(checked) >= 30


@pytest.mark.parametrize("task_status", ["matching", "enriching"])
@pytest.mark.parametrize("action", ["detail", "retry"])
def test_cross_owner_stale_task_request_does_not_write(client, monkeypatch, task_status, action):
    owner = make_user("stale_owner")
    other = make_user("stale_other")
    task_id = make_task(
        owner, "stale private task", task_status=task_status,
        updated_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    )
    with get_db() as conn:
        before = dict(conn.execute("SELECT * FROM match_records WHERE id = ?", (task_id,)).fetchone())

    def unexpected_recovery(**_kwargs):
        pytest.fail("An unauthorized request must not reach task recovery")

    monkeypatch.setattr(match_router, "recover_stale_tasks", unexpected_recovery)
    url = f"/agent/tasks/{task_id}"
    response = client.get(url, headers=auth_headers(other)) if action == "detail" else client.post(f"{url}/retry", headers=auth_headers(other))
    assert response.status_code == 404
    with get_db() as conn:
        after = dict(conn.execute("SELECT * FROM match_records WHERE id = ?", (task_id,)).fetchone())
    assert after == before


@pytest.mark.parametrize("reader_role", ["owner", "admin"])
def test_authorized_detail_recovers_only_requested_task(client, reader_role):
    owner = make_user("recovery_owner")
    reader = owner if reader_role == "owner" else make_user("recovery_admin", role="admin")
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    task_id = make_task(owner, "requested stale task", task_status="matching", updated_at=old)
    untouched_id = make_task(owner, "another stale task", task_status="enriching", updated_at=old)
    response = client.get(f"/agent/tasks/{task_id}", headers=auth_headers(reader))
    assert response.status_code == 200
    assert response.json()["taskStatus"] == "failed"
    assert response.json()["lastErrorStage"] == "interrupted"
    with get_db() as conn:
        untouched = conn.execute("SELECT task_status, updated_at FROM match_records WHERE id = ?", (untouched_id,)).fetchone()
    assert tuple(untouched) == ("enriching", old)


def test_owner_can_retry_stale_task(client, monkeypatch):
    owner = make_user("stale_retry_owner")
    task_id = make_task(
        owner, "retry stale task", task_status="matching", recommendations=[],
        updated_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
    )
    monkeypatch.setattr(match_router, "_perform_partner_match", lambda _: [])

    def finish(record_id, *_args, **_kwargs):
        match_router._set_task_state(record_id, "ready")
        return "ready"

    monkeypatch.setattr(match_router, "_run_task_enrichment", finish)
    response = client.post(f"/agent/tasks/{task_id}/retry", headers=auth_headers(owner))
    assert response.status_code == 200
    assert response.json()["taskStatus"] == "ready"
