"""Immediate task acceptance, idempotency and stable sidebar pagination."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import BackgroundTasks, HTTPException

from backend.app.database import get_db
from backend.app.routers import match as match_router
from .conftest import auth_headers, make_task, make_user, make_partner
from .test_tasks import finish_enrichment, recommendation_model


@pytest.fixture
def queued(monkeypatch):
    jobs = []
    monkeypatch.setattr(BackgroundTasks, "add_task", lambda self, func, *args, **kwargs: jobs.append((func, args, kwargs)))
    return jobs


def payload(requirement="即时任务验证"):
    return {"requestId": str(uuid.uuid4()), "requirement": requirement}


def test_acceptance_persists_before_model_and_duplicate_schedules_once(client, queued, monkeypatch):
    make_partner()
    user = make_user("immediate-user")
    body = payload()
    headers = auth_headers(user)
    response = client.post("/agent/tasks", headers=headers, json=body)
    assert response.status_code == 202
    assert response.json() == {"recordId": body["requestId"], "taskStatus": "matching"}
    detail = client.get(f'/agent/tasks/{body["requestId"]}', headers=headers).json()
    assert detail["taskStatus"] == "matching"
    assert detail["recommendations"] == []
    assert client.post("/agent/tasks", headers=headers, json=body).status_code == 202
    assert len(queued) == 1
    monkeypatch.setattr(match_router, "_perform_partner_match", lambda _: [recommendation_model()])
    monkeypatch.setattr(match_router, "_run_task_enrichment", finish_enrichment)
    func, args, kwargs = queued[0]
    func(*args, **kwargs)
    assert client.get(f'/agent/tasks/{body["requestId"]}', headers=headers).json()["taskStatus"] == "ready"
    assert client.post("/agent/tasks", headers=headers, json=body).json()["taskStatus"] == "ready"
    assert len(queued) == 1


def test_concurrent_duplicate_creation_schedules_one_job(client, queued):
    headers = auth_headers(make_user("concurrent-create"))
    body = payload()
    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(lambda _: client.post("/agent/tasks", headers=headers, json=body).status_code, range(10)))
    assert statuses == [202] * 10
    assert len(queued) == 1
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM match_records WHERE id=?", (body["requestId"],)).fetchone()[0] == 1


def test_create_conflicts_preserve_ownership_and_content(client, queued):
    owner = make_user("create-owner")
    other = make_user("create-other")
    body = payload()
    assert client.post("/agent/tasks", headers=auth_headers(owner), json=body).status_code == 202
    assert client.post("/agent/tasks", headers=auth_headers(other), json=body).status_code == 404
    assert client.get(f'/agent/tasks/{body["requestId"]}', headers=auth_headers(other)).status_code == 404
    assert client.post("/agent/tasks", headers=auth_headers(owner), json={**body, "requirement": "different"}).status_code == 409
    assert len(queued) == 1


@pytest.mark.parametrize("body", [{"requirement": "valid"}, {"requestId": "invalid", "requirement": "valid"}, payload("   "), payload("x" * 2001)])
def test_invalid_creations_do_not_leave_empty_tasks(client, queued, body):
    response = client.post("/agent/tasks", headers=auth_headers(make_user("invalid-create")), json=body)
    assert response.status_code == 422
    assert queued == []
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM match_records").fetchone()[0] == 0


def test_creation_requires_authentication(client, queued):
    assert client.post("/agent/tasks", json=payload()).status_code == 401
    assert queued == []


@pytest.mark.parametrize("stage,expected", [("match", "failed"), ("enrich", "partial")])
def test_background_failure_has_real_persisted_status(client, monkeypatch, stage, expected):
    make_partner()
    def fail(*args, **kwargs):
        raise HTTPException(502, "synthetic failure")
    monkeypatch.setattr(match_router, "_perform_partner_match", fail if stage == "match" else lambda _: [recommendation_model()])
    monkeypatch.setattr(match_router, "_run_task_enrichment", fail)
    headers = auth_headers(make_user("background-failure"))
    body = payload()
    assert client.post("/agent/tasks", headers=headers, json=body).status_code == 202
    detail = client.get(f'/agent/tasks/{body["requestId"]}', headers=headers).json()
    assert detail["taskStatus"] == expected
    assert "synthetic failure" not in str(detail)


def test_cursor_survives_new_head_and_archived_boundary_without_duplicates(client):
    owner = make_user("cursor-owner")
    headers = auth_headers(owner)
    ids = [make_task(owner, f"cursor-{index}") for index in range(26)]
    date = datetime.now(timezone.utc)
    with get_db() as conn:
        for index, task_id in enumerate(ids):
            conn.execute("UPDATE match_records SET created_at=? WHERE id=?", ((date - timedelta(minutes=index)).isoformat(), task_id))
    first = client.get("/agent/tasks?pageSize=10", headers=headers).json()
    assert [task["id"] for task in first["items"]] == ids[:10]
    last = first["items"][-1]
    make_task(owner, "new head")
    assert client.patch(f'/agent/tasks/{last["id"]}/archive', headers=headers).status_code == 204
    params = {"pageSize": 10, "beforeCreatedAt": last["createdAt"], "beforeId": last["id"]}
    second = client.get("/agent/tasks", headers=headers, params=params).json()
    assert [task["id"] for task in second["items"]] == ids[10:20]
    assert second["total"] == 16
    last = second["items"][-1]
    third = client.get("/agent/tasks", headers=headers, params={**params, "beforeCreatedAt": last["createdAt"], "beforeId": last["id"]}).json()
    assert [task["id"] for task in third["items"]] == ids[20:]


def test_cursor_breaks_same_timestamp_ties_and_ids_are_owner_scoped(client):
    owner, other = make_user("id-owner"), make_user("id-other")
    ids = [make_task(owner, f"same-{index}") for index in range(12)]
    foreign_id = make_task(other, "foreign")
    with get_db() as conn:
        conn.execute("UPDATE match_records SET created_at='2026-09-05T01:00:00+00:00'")
    headers = auth_headers(owner)
    first = client.get("/agent/tasks?pageSize=10", headers=headers).json()
    last = first["items"][-1]
    rest = client.get("/agent/tasks", headers=headers, params={"beforeCreatedAt": last["createdAt"], "beforeId": last["id"]}).json()
    assert [item["id"] for item in first["items"] + rest["items"]] == sorted(ids, reverse=True)
    result = client.get("/agent/tasks", headers=headers, params=[("ids", ids[0]), ("ids", foreign_id)]).json()
    assert [item["id"] for item in result["items"]] == [ids[0]]
    assert client.get("/agent/tasks?beforeId=only-id", headers=headers).status_code == 422
    assert client.get("/agent/tasks", headers=headers, params=[("ids", str(index)) for index in range(101)]).status_code == 422
