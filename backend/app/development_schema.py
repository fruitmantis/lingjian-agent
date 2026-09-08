"""Additive Phase C lifecycle, with database-enforced single-writer runs."""
import sqlite3

DDL = [
'''CREATE TABLE development_requests (
 id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL REFERENCES users(id),
 target_partner_id TEXT NOT NULL REFERENCES partners(id), payload_json TEXT NOT NULL,
 created_at TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id))''',
'''CREATE TABLE development_plans (
 id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL REFERENCES users(id),
 request_id TEXT NOT NULL UNIQUE REFERENCES development_requests(id),
 target_partner_id TEXT NOT NULL REFERENCES partners(id),
 status TEXT NOT NULL CHECK(status IN ('active','archived')), archived_at TEXT,
 current_version_id TEXT REFERENCES development_versions(id),
 confirmed_version_id TEXT REFERENCES development_versions(id),
 active_run_id TEXT REFERENCES development_runs(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''',
'''CREATE TABLE development_runs (
 id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES development_plans(id),
 owner_user_id TEXT NOT NULL REFERENCES users(id),
 run_type TEXT NOT NULL CHECK(run_type IN ('generate','revise')),
 submission_id TEXT NOT NULL, request_hash TEXT NOT NULL,
 based_on_version_id TEXT REFERENCES development_versions(id),
 status TEXT NOT NULL CHECK(status IN ('pending','running','ready','partial','failed','interrupted')),
 input_snapshot TEXT NOT NULL, model_config_id TEXT REFERENCES model_configs(id),
 execution_token TEXT, created_at TEXT NOT NULL, started_at TEXT, ended_at TEXT,
 error_stage TEXT, safe_error_message TEXT, UNIQUE(owner_user_id,submission_id))''',
'''CREATE UNIQUE INDEX idx_development_one_run ON development_runs(plan_id) WHERE status IN ('pending','running')''',
'''CREATE TABLE development_versions (
 id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES development_plans(id),
 version_no INTEGER NOT NULL CHECK(version_no>0), based_on_version_id TEXT REFERENCES development_versions(id),
 run_id TEXT UNIQUE REFERENCES development_runs(id), payload_json TEXT NOT NULL,
 dependency_json TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 UNIQUE(plan_id,version_no))''',
'''CREATE TABLE development_version_items (
 id TEXT PRIMARY KEY, version_id TEXT NOT NULL REFERENCES development_versions(id),
 ordinal INTEGER NOT NULL, payload_json TEXT NOT NULL, UNIQUE(version_id,ordinal))''',
'''CREATE TABLE development_diagnoses (
 version_id TEXT NOT NULL REFERENCES development_versions(id), capability_tag_id TEXT NOT NULL REFERENCES capability_tags(id),
 payload_json TEXT NOT NULL, PRIMARY KEY(version_id,capability_tag_id))''',
'''CREATE TABLE development_audit_events (
 id TEXT PRIMARY KEY,plan_id TEXT NOT NULL REFERENCES development_plans(id),
 version_id TEXT REFERENCES development_versions(id), actor_user_id TEXT NOT NULL REFERENCES users(id),
 action TEXT NOT NULL, created_at TEXT NOT NULL)''',
'''CREATE INDEX idx_development_owner ON development_plans(owner_user_id,status,created_at)''',
'''CREATE TRIGGER development_version_immutable BEFORE UPDATE ON development_versions BEGIN SELECT RAISE(ABORT,'immutable version'); END''',
'''CREATE TRIGGER development_item_immutable BEFORE UPDATE ON development_version_items BEGIN SELECT RAISE(ABORT,'immutable item'); END''',
'''CREATE TRIGGER development_diagnosis_immutable BEFORE UPDATE ON development_diagnoses BEGIN SELECT RAISE(ABORT,'immutable diagnosis'); END''',
]


def migrate_to_v12(conn: sqlite3.Connection):
    version=int(conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0])
    if version>=12:return
    if version!=11:raise RuntimeError('Development migration requires v11')
    conn.commit()
    try:
        conn.execute('BEGIN IMMEDIATE')
        for sql in DDL:conn.execute(sql)
        conn.execute("INSERT OR IGNORE INTO model_usage_configs(scene_key,scene_name,model_config_id,description,updated_at) VALUES ('partner_development','伙伴能力发展',NULL,'需明确绑定模型或配置唯一默认模型；本轮仅 mock 验证',datetime('now'))")
        conn.execute("UPDATE app_metadata SET value='12' WHERE key='schema_version'")
        conn.commit()
    except Exception:
        conn.rollback();raise
