import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status

from backend.app.database import get_db
from backend.app.routers import match as match_router

from .conftest import auth_headers, make_partner, make_task, make_user, recommendation


def recommendation_model():
    return match_router.PartnerRecommendation.model_validate(recommendation())


def finish_enrichment(record_id, *_args, **_kwargs):
    match_router._set_task_state(record_id, "ready")
    return "ready"


def task_row(requirement: str):
    with get_db() as conn:
        return conn.execute("SELECT * FROM match_records WHERE requirement = ?", (requirement,)).fetchone()


def test_task_001_match_failure_keeps_retryable_task(client, monkeypatch):
    user = make_user("task_failure_user")
    make_partner()

    def fail(_requirement):
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="fake LLM failure")

    monkeypatch.setattr(match_router, "_perform_partner_match", fail)
    response = client.post("/agent/match", headers=auth_headers(user), json={"requirement": "TASK-001"})
    assert response.status_code == 502
    row = task_row("TASK-001")
    assert row is not None
    assert row["owner_user_id"] == user["id"]
    assert row["task_status"] == "failed"
    assert row["last_error_stage"] == "partner_match"


def test_task_002_enrichment_failure_keeps_recommendations_and_partial_state(client, monkeypatch):
    user = make_user("task_partial_user")
    make_partner()
    monkeypatch.setattr(match_router, "_perform_partner_match", lambda _: [recommendation_model()])
    monkeypatch.setattr(match_router, "_run_task_enrichment", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("injected")))
    response = client.post("/agent/match", headers=auth_headers(user), json={"requirement": "TASK-002"})
    assert response.status_code == 500
    row = task_row("TASK-002")
    assert row["task_status"] == "partial"
    assert row["last_error_stage"] == "persistence"
    assert json.loads(row["recommendations_json"])[0]["partnerName"] == "验证伙伴"


def test_task_003_failed_retry_can_complete(client, monkeypatch):
    user = make_user("failed_retry_user")
    make_partner()
    task_id = make_task(user, "TASK-003", task_status="failed", recommendations=[])
    monkeypatch.setattr(match_router, "_perform_partner_match", lambda _: [recommendation_model()])
    monkeypatch.setattr(match_router, "_run_task_enrichment", finish_enrichment)
    response = client.post(f"/agent/tasks/{task_id}/retry", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json()["taskStatus"] == "ready"
    with get_db() as conn:
        row = conn.execute("SELECT task_status, recommendations_json FROM match_records WHERE id = ?", (task_id,)).fetchone()
    assert row["task_status"] == "ready"
    assert len(json.loads(row["recommendations_json"])) == 1


def test_task_004_partial_retry_reuses_valid_recommendations(client, monkeypatch):
    user = make_user("partial_retry_user")
    task_id = make_task(user, "TASK-004", task_status="partial")
    monkeypatch.setattr(match_router, "_perform_partner_match", lambda _: (_ for _ in ()).throw(AssertionError("must not rematch")))
    monkeypatch.setattr(match_router, "_run_task_enrichment", finish_enrichment)
    response = client.post(f"/agent/tasks/{task_id}/retry", headers=auth_headers(user))
    assert response.status_code == 200
    assert response.json()["taskStatus"] == "ready"


def test_task_005_retry_does_not_duplicate_derivative_records(client, monkeypatch):
    user = make_user("idempotent_retry_user")
    task_id = make_task(user, "TASK-005", task_status="partial")
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO demand_profiles
               (id, match_record_id, requirement_text, matched_partner_count, created_at)
               VALUES ('existing-demand', ?, 'TASK-005', 1, ?)""",
            (task_id, now),
        )

    def create_opportunity(requirement, record_id, recommendations):
        with get_db() as conn:
            conn.execute(
                """INSERT INTO project_opportunities
                   (id, match_record_id, requirement_text, created_at, updated_at)
                   VALUES ('generated-opportunity', ?, ?, ?, ?)""",
                (record_id, requirement, now, now),
            )
        return True

    monkeypatch.setattr(match_router, "_perform_partner_match", lambda _: (_ for _ in ()).throw(AssertionError("must not rematch")))
    monkeypatch.setattr(match_router, "_generate_demand_profile", lambda *_args: (_ for _ in ()).throw(AssertionError("must not duplicate demand")))
    monkeypatch.setattr(match_router, "_extract_project_opportunity", create_opportunity)
    response = client.post(f"/agent/tasks/{task_id}/retry", headers=auth_headers(user))
    assert response.status_code == 200
    assert client.post(f"/agent/tasks/{task_id}/retry", headers=auth_headers(user)).status_code == 409
    with get_db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM demand_profiles WHERE match_record_id = ?", (task_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM project_opportunities WHERE match_record_id = ?", (task_id,)).fetchone()[0] == 1


def test_task_006_only_one_of_ten_concurrent_retries_executes(client, monkeypatch):
    make_partner()
    user = make_user("concurrent_retry_user")
    task_id = make_task(user, "TASK-006", task_status="failed", recommendations=[])
    calls = 0
    lock = threading.Lock()

    def slow_match(_requirement):
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.25)
        return [recommendation_model()]

    monkeypatch.setattr(match_router, "_perform_partner_match", slow_match)
    monkeypatch.setattr(match_router, "_run_task_enrichment", finish_enrichment)
    headers = auth_headers(user)
    with ThreadPoolExecutor(max_workers=10) as pool:
        statuses = list(pool.map(lambda _: client.post(f"/agent/tasks/{task_id}/retry", headers=headers).status_code, range(10)))
    assert statuses.count(200) == 1
    assert statuses.count(409) == 9
    assert calls == 1


def test_task_007_archive_during_retry_has_consistent_final_state(client, monkeypatch):
    make_partner()
    user = make_user("archive_retry_user")
    task_id = make_task(user, "TASK-007", task_status="failed", recommendations=[])
    started = threading.Event()

    def slow_match(_requirement):
        started.set()
        time.sleep(0.2)
        return [recommendation_model()]

    monkeypatch.setattr(match_router, "_perform_partner_match", slow_match)
    monkeypatch.setattr(match_router, "_run_task_enrichment", finish_enrichment)
    headers = auth_headers(user)
    with ThreadPoolExecutor(max_workers=2) as pool:
        retry_future = pool.submit(client.post, f"/agent/tasks/{task_id}/retry", headers=headers)
        assert started.wait(timeout=2)
        archive_response = client.patch(f"/agent/tasks/{task_id}/archive", headers=headers)
        retry_response = retry_future.result(timeout=5)
    assert retry_response.status_code == 200
    assert archive_response.status_code == 204
    with get_db() as conn:
        row = conn.execute("SELECT task_status, archived_at FROM match_records WHERE id = ?", (task_id,)).fetchone()
    assert row["task_status"] == "ready"
    assert row["archived_at"] is not None


def test_stale_matching_and_enriching_tasks_become_retryable(client, monkeypatch):
    user = make_user("stale_user")
    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    matching_id = make_task(user, "STALE-MATCHING", task_status="matching", recommendations=[], updated_at=old)
    enriching_id = make_task(user, "STALE-ENRICHING", task_status="enriching", updated_at=old)
    monkeypatch.setenv("TASK_STALE_SECONDS", "1")
    response = client.get("/agent/tasks?pageSize=100", headers=auth_headers(user))
    assert response.status_code == 200
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, task_status, last_error_stage FROM match_records WHERE id IN (?, ?)",
            (matching_id, enriching_id),
        ).fetchall()
    assert {(row["task_status"], row["last_error_stage"]) for row in rows} == {("failed", "interrupted")}


def test_empty_partial_recommendations_force_rematch(client, monkeypatch):
    make_partner()
    user = make_user("empty_partial_user")
    task_id = make_task(user, "EMPTY-PARTIAL", task_status="partial", recommendations=[])
    calls = 0

    def rematch(_requirement):
        nonlocal calls
        calls += 1
        return [recommendation_model()]

    monkeypatch.setattr(match_router, "_perform_partner_match", rematch)
    monkeypatch.setattr(match_router, "_run_task_enrichment", finish_enrichment)
    response = client.post(f"/agent/tasks/{task_id}/retry", headers=auth_headers(user))
    assert response.status_code == 200
    assert calls == 1


def test_persist_failure_then_retry_rematches_instead_of_reusing_empty(client, monkeypatch):
    user = make_user("persist_failure_user")
    make_partner()
    calls = 0

    def match(_requirement):
        nonlocal calls
        calls += 1
        return [recommendation_model()]

    original_set_state = match_router._set_task_state
    injected = False

    def fail_recommendation_persist(record_id, task_status, error_stage=None, recommendations=None):
        nonlocal injected
        if task_status == "enriching" and recommendations is not None and not injected:
            injected = True
            raise RuntimeError("injected recommendation persistence failure")
        return original_set_state(record_id, task_status, error_stage, recommendations)

    monkeypatch.setattr(match_router, "_perform_partner_match", match)
    monkeypatch.setattr(match_router, "_set_task_state", fail_recommendation_persist)
    response = client.post("/agent/match", headers=auth_headers(user), json={"requirement": "PERSIST-FAILURE"})
    assert response.status_code == 500
    row = task_row("PERSIST-FAILURE")
    assert row["task_status"] == "partial"
    assert json.loads(row["recommendations_json"]) == []

    monkeypatch.setattr(match_router, "_set_task_state", original_set_state)
    monkeypatch.setattr(match_router, "_run_task_enrichment", finish_enrichment)
    retry = client.post(f"/agent/tasks/{row['id']}/retry", headers=auth_headers(user))
    assert retry.status_code == 200
    assert calls == 2
