"""Historical maintenance guards, isolated databases and synthetic model responses."""
from contextlib import closing
import json
import sqlite3

import httpx
import pytest

from backend.app import ai_client, database
from backend.app.routers import match
from backend.scripts import repair_historical_data as repair
from .conftest import auth_headers, make_partner, make_task, make_user


def model_output(messages):
    if "industryTags" in messages[0]["content"]:
        return {"industryTags": "制造", "capabilityTags": "AI,不存在的标签", "deliveryTypeTags": "咨询",
                "regionTags": "全国", "complexityLevel": "中", "urgencyLevel": "低",
                "projectKeywords": "验证", "supplyStatus": "partial", "gapAnalysis": "需补充证据"}
    return {**dict.fromkeys(("customerName", "projectName", "industry", "region", "projectStage",
                            "businessNeeds", "technicalNeeds", "deliveryNeeds", "qualificationRequirements",
                            "caseRequirements", "onsiteRequirement", "timelineRequirement", "cloudPlatformPreference"), "未识别"),
            "followUpQuestions": ["请补充实施时间"]}


@pytest.fixture
def maintenance(tmp_path, monkeypatch, client):
    # The maintenance command deliberately remains v9-only. Recreate that exact
    # legacy schema in this synthetic test DB; do not relax the production guard.
    with database.get_db() as conn:
        for table in ("resource_redirect_events", "resource_capability_map", "enablement_resource_versions", "case_share_versions",
                      "enablement_reviews", "enablement_audit_events", "enablement_resources", "case_share_configs"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
            conn.execute(f"DROP TABLE {table}")
        conn.execute("UPDATE app_metadata SET value='9' WHERE key='schema_version'")

    owner = make_user("repair_owner")
    other = make_user("repair_other")
    make_partner()
    demand_only = make_task(owner, "REPAIR-DEMAND")
    opportunity_only = make_task(owner, "REPAIR-OPPORTUNITY")
    both = make_task(owner, "REPAIR-BOTH")
    make_task(other, "IN-FLIGHT", task_status="enriching")
    make_task(other, "ARCHIVED", archived=True)
    with database.get_db() as conn:
        conn.execute("INSERT INTO demand_profiles(id,match_record_id,requirement_text,created_at) VALUES('existing-demand',?,'REPAIR-OPPORTUNITY','2026-01-01')", (opportunity_only,))
        conn.execute("INSERT INTO project_opportunities(id,match_record_id,requirement_text,created_at,updated_at) VALUES('existing-opp',?,'REPAIR-DEMAND','2026-01-01','2026-01-01')", (demand_only,))
        conn.execute("UPDATE capability_tags SET enabled=0")
        conn.execute("UPDATE capability_tags SET enabled=1 WHERE name='AI'")
    # Preserve a legacy orphan without allowing new FK violations during repair.
    with sqlite3.connect(database.DATABASE_PATH) as conn:
        conn.execute("INSERT INTO cases(id,partner_id,title,created_at) VALUES('orphan','missing-partner','Legacy','2026-01-01')")
    calls = []

    def fake(messages, timeout=None, scene="default"):
        calls.append((scene, timeout))
        return json.dumps(model_output(messages), ensure_ascii=False)

    def forbid(*args, **kwargs):
        raise AssertionError("Unexpected rematch, tags or network request")

    monkeypatch.setattr(match, "chat_completion", fake)
    monkeypatch.setattr(ai_client, "chat_completion", fake)
    monkeypatch.setattr(match, "_perform_partner_match", forbid)
    monkeypatch.setattr(match, "_generate_tag_suggestions", forbid)
    monkeypatch.setattr(httpx.Client, "post", forbid)
    work = tmp_path / "maintenance"
    source_hash = repair.digest(database.DATABASE_PATH)
    plan = repair.prepare(database.DATABASE_PATH, work)
    return {"work": work, "plan": plan, "owner": owner, "other": other,
            "demand": demand_only, "opportunity": opportunity_only, "both": both, "calls": calls,
            "source_hash": source_hash}


def snapshot(path):
    with closing(repair.connect(path)) as conn:
        return {r[0]: repair.rows(conn, r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def generate(data):
    assert repair.generate_missing(data["work"], 4) == {"calls": 4, "failed": []}
    assert len(repair.staged_changes(data["work"], complete=True)) == 4


def test_prepare_readonly_private_and_no_implicit_model_calls(maintenance):
    data = maintenance
    assert data["plan"]["model_calls"] == 4
    assert len(data["plan"]["tasks"]) == 5
    assert len(data["plan"]["orphan_cases"]) == 1
    assert data["calls"] == []
    assert repair.digest(database.DATABASE_PATH) == data["source_hash"]
    assert snapshot(database.DATABASE_PATH) == snapshot(data["work"] / "before.db")
    assert data["work"].stat().st_mode & 0o777 == 0o700
    for name in ("before.db", "staged.db", "plan.json"):
        assert (data["work"] / name).stat().st_mode & 0o777 == 0o600
    assert "REPAIR-DEMAND" not in (data["work"] / "plan.json").read_text()
    with pytest.raises(FileExistsError):
        repair.prepare(database.DATABASE_PATH, data["work"])


def test_roundtrip_preserves_original_rows_and_is_idempotent(maintenance, client):
    data = maintenance
    before = snapshot(database.DATABASE_PATH)
    original_hash = repair.digest(database.DATABASE_PATH)
    generate(data)
    assert repair.digest(database.DATABASE_PATH) == original_hash
    assert data["calls"].count(("demand_profile", 30)) == 2
    assert data["calls"].count(("demand_profile", 60)) == 2
    assert repair.generate_missing(data["work"], 0) == {"calls": 0, "failed": []}
    assert repair.transfer(data["work"], database.DATABASE_PATH) == 4
    assert repair.transfer(data["work"], database.DATABASE_PATH) == 0
    after = snapshot(database.DATABASE_PATH)
    for table in before:
        if table not in repair.DERIVATIVES.values():
            assert after[table] == before[table]
        else:
            assert all(row in after[table] for row in before[table])
    for table in repair.DERIVATIVES.values():
        for row in after[table]:
            task = next(t for t in before["match_records"] if t["id"] == row["match_record_id"])
            if row not in before[table]:
                assert row["requirement_text"] == task["requirement"]
    own = client.get(f"/agent/tasks/{data['demand']}", headers=auth_headers(data["owner"]))
    assert own.status_code == 200
    assert client.get(f"/agent/tasks/{data['demand']}", headers=auth_headers(data["other"])).status_code == 404
    assert repair.transfer(data["work"], database.DATABASE_PATH, rollback=True) == 4
    assert repair.transfer(data["work"], database.DATABASE_PATH, rollback=True) == 0
    assert snapshot(database.DATABASE_PATH) == before


def test_budget_check_makes_zero_calls(maintenance):
    with pytest.raises(repair.RepairConflict, match="额度不足"):
        repair.generate_missing(maintenance["work"], 3)
    assert maintenance["calls"] == []


@pytest.mark.parametrize("field,value", [("industryTags", []), ("supplyStatus", "invented"), ("urgencyLevel", None)])
def test_invalid_demand_output_is_not_replaced_by_fallback(maintenance, monkeypatch, field, value):
    def invalid(messages, **kwargs):
        result = model_output(messages)
        result[field] = value
        return json.dumps(result)
    monkeypatch.setattr(match, "chat_completion", invalid)
    result = repair.generate_missing(maintenance["work"], 4)
    assert result == {"calls": 1, "failed": [{"id": maintenance["demand"], "stage": "demand_profile"}]}
    assert repair.staged_changes(maintenance["work"], complete=False) == []
    with pytest.raises(repair.RepairConflict, match="尚未全部生成"):
        repair.transfer(maintenance["work"], database.DATABASE_PATH)


@pytest.mark.parametrize("payload", ["{}", "[]", "not-json", '{"followUpQuestions":"bad"}'])
def test_invalid_opportunity_stops_then_resumes_only_missing(maintenance, monkeypatch, payload):
    fake = ai_client.chat_completion
    monkeypatch.setattr(ai_client, "chat_completion", lambda *a, **k: payload)
    result = repair.generate_missing(maintenance["work"], 4)
    assert result["calls"] == 2
    assert result["failed"] == [{"id": maintenance["opportunity"], "stage": "project_opportunity"}]
    assert len(repair.staged_changes(maintenance["work"], complete=False)) == 1
    monkeypatch.setattr(ai_client, "chat_completion", fake)
    assert repair.generate_missing(maintenance["work"], 3) == {"calls": 3, "failed": []}
    assert len(repair.staged_changes(maintenance["work"], complete=True)) == 4


def test_empty_dictionary_cannot_accept_model_invented_tags(maintenance):
    generate(maintenance)
    with closing(repair.connect(maintenance["work"] / "staged.db")) as conn:
        enabled = {r[0] for r in conn.execute("SELECT name FROM capability_tags WHERE enabled=1")}
        for r in conn.execute("SELECT capability_tags FROM demand_profiles WHERE id<>'existing-demand'"):
            assert set(filter(None, (r[0] or "").split(", "))) <= enabled


@pytest.mark.parametrize("column,value", [("owner_user_id", "other"), ("requirement", "changed"), ("archived_at", "2026-09-05"), ("task_status", "enriching")])
def test_stale_tasks_block_atomic_apply(maintenance, column, value):
    generate(maintenance)
    if value == "other":
        value = maintenance["other"]["id"]
    with database.get_db() as conn:
        conn.execute(f"UPDATE match_records SET {column}=? WHERE id=?", (value, maintenance["both"]))
    before = snapshot(database.DATABASE_PATH)
    with pytest.raises(repair.RepairConflict, match="任务已被修改"):
        repair.transfer(maintenance["work"], database.DATABASE_PATH)
    assert snapshot(database.DATABASE_PATH) == before


def test_concurrent_derivative_wins_without_being_overwritten(maintenance):
    generate(maintenance)
    with database.get_db() as conn:
        conn.execute("INSERT INTO demand_profiles(id,match_record_id,requirement_text,created_at) VALUES('concurrent',?,'concurrent','2026')", (maintenance["both"],))
    before = snapshot(database.DATABASE_PATH)
    with pytest.raises(repair.RepairConflict):
        repair.transfer(maintenance["work"], database.DATABASE_PATH)
    assert snapshot(database.DATABASE_PATH) == before


def test_edited_existing_derivative_blocks_apply(maintenance):
    generate(maintenance)
    with database.get_db() as conn:
        conn.execute("UPDATE demand_profiles SET region_tags='人工更新' WHERE id='existing-demand'")
    before = snapshot(database.DATABASE_PATH)
    with pytest.raises(repair.RepairConflict, match="已有衍生记录已变化"):
        repair.transfer(maintenance["work"], database.DATABASE_PATH)
    assert snapshot(database.DATABASE_PATH) == before


def test_edited_backfill_blocks_atomic_rollback(maintenance):
    generate(maintenance)
    assert repair.transfer(maintenance["work"], database.DATABASE_PATH) == 4
    with database.get_db() as conn:
        conn.execute("UPDATE project_opportunities SET project_name='用户补全' WHERE match_record_id=?", (maintenance["both"],))
    before = snapshot(database.DATABASE_PATH)
    with pytest.raises(repair.RepairConflict, match="补齐记录已被修改"):
        repair.transfer(maintenance["work"], database.DATABASE_PATH, rollback=True)
    assert snapshot(database.DATABASE_PATH) == before


def test_failure_after_inserts_rolls_back_entire_transaction(maintenance, monkeypatch):
    generate(maintenance)
    before = snapshot(database.DATABASE_PATH)
    real_check = repair.check_integrity

    def fail_after_write(conn):
        if conn.execute("PRAGMA database_list").fetchone()[2] == str(database.DATABASE_PATH):
            assert conn.execute("SELECT count(*) FROM demand_profiles").fetchone()[0] == 3
            raise RuntimeError("Injected failure after inserts")
        real_check(conn)

    monkeypatch.setattr(repair, "check_integrity", fail_after_write)
    with pytest.raises(RuntimeError, match="Injected failure"):
        repair.transfer(maintenance["work"], database.DATABASE_PATH)
    assert snapshot(database.DATABASE_PATH) == before


@pytest.mark.parametrize("sql", ["UPDATE match_records SET recommendations_json='[]'", "DELETE FROM cases", "UPDATE project_opportunities SET project_name='overwrite'", "CREATE TABLE unexpected(id TEXT)"])
def test_staging_cannot_modify_existing_or_unrelated_data(maintenance, sql):
    with sqlite3.connect(maintenance["work"] / "staged.db") as conn:
        conn.execute(sql)
    with pytest.raises(repair.RepairConflict):
        repair.staged_changes(maintenance["work"], complete=False)


def test_changed_configuration_blocks_calls(maintenance):
    with database.get_db() as conn:
        conn.execute("UPDATE model_configs SET temperature=0.7")
    with pytest.raises(repair.RepairConflict, match="模型或业务资料已变化"):
        repair.generate_missing(maintenance["work"], 4)
    assert maintenance["calls"] == []


def test_work_lock_and_backup_protection(maintenance):
    work = maintenance["work"]
    with repair.work_lock(work):
        with pytest.raises(repair.RepairConflict, match="另一维护进程"):
            repair.generate_missing(work, 4)
    with pytest.raises(repair.RepairConflict, match="禁止将备份"):
        repair.transfer(work, work / "before.db")
    with sqlite3.connect(work / "before.db") as conn:
        conn.execute("UPDATE match_records SET requirement='changed'")
    with pytest.raises(repair.RepairConflict, match="备份或清单发生变化"):
        repair.load_plan(work)
