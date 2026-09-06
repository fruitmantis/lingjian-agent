import sqlite3
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from .config import PROJECT_ROOT, chroma_path, database_path, uploads_path


DATABASE_PATH = database_path()
DATA_DIR = DATABASE_PATH.parent
UPLOADS_DIR = uploads_path()
CHROMA_DIR = chroma_path()


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate_to_v9(connection: sqlite3.Connection) -> None:
    """Rebuild task-related tables with strict ownership and relationship constraints."""
    version_row = connection.execute("SELECT value FROM app_metadata WHERE key = 'schema_version'").fetchone()
    version = int(version_row[0]) if version_row else 0
    if version >= 9:
        return

    invalid_counts = {
        "unowned_tasks": connection.execute("SELECT COUNT(*) FROM match_records WHERE owner_user_id IS NULL").fetchone()[0],
        "missing_owners": connection.execute(
            "SELECT COUNT(*) FROM match_records mr LEFT JOIN users u ON u.id = mr.owner_user_id WHERE mr.owner_user_id IS NOT NULL AND u.id IS NULL"
        ).fetchone()[0],
        "orphan_demands": connection.execute(
            "SELECT COUNT(*) FROM demand_profiles dp LEFT JOIN match_records mr ON mr.id = dp.match_record_id WHERE dp.match_record_id IS NOT NULL AND mr.id IS NULL"
        ).fetchone()[0],
        "orphan_opportunities": connection.execute(
            "SELECT COUNT(*) FROM project_opportunities po LEFT JOIN match_records mr ON mr.id = po.match_record_id WHERE po.match_record_id IS NOT NULL AND mr.id IS NULL"
        ).fetchone()[0],
        "orphan_suggestions": connection.execute(
            "SELECT COUNT(*) FROM capability_tag_suggestions s LEFT JOIN match_records mr ON mr.id = s.source_match_record_id WHERE s.source_match_record_id IS NOT NULL AND mr.id IS NULL"
        ).fetchone()[0],
    }
    if any(invalid_counts.values()):
        details = ", ".join(f"{key}={value}" for key, value in invalid_counts.items() if value)
        raise RuntimeError(f"v9 migration aborted because task ownership is incomplete: {details}")

    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("ALTER TABLE demand_profiles RENAME TO demand_profiles_v8")
        connection.execute("ALTER TABLE project_opportunities RENAME TO project_opportunities_v8")
        connection.execute("ALTER TABLE capability_tag_suggestions RENAME TO capability_tag_suggestions_v8")
        connection.execute("ALTER TABLE match_records RENAME TO match_records_v8")

        connection.execute("""CREATE TABLE match_records (
            id TEXT PRIMARY KEY, requirement TEXT NOT NULL, recommendations_json TEXT NOT NULL,
            created_at TEXT NOT NULL, created_by TEXT, owner_user_id TEXT NOT NULL,
            archived_at TEXT, task_status TEXT NOT NULL DEFAULT 'ready',
            last_error_stage TEXT, updated_at TEXT NOT NULL,
            CHECK (task_status IN ('matching', 'enriching', 'ready', 'partial', 'failed')),
            FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE RESTRICT ON UPDATE RESTRICT)""")
        connection.execute("""INSERT INTO match_records
            (id, requirement, recommendations_json, created_at, created_by, owner_user_id,
             archived_at, task_status, last_error_stage, updated_at)
            SELECT id, requirement, recommendations_json, created_at, created_by, owner_user_id,
                   archived_at, 'ready', NULL, created_at FROM match_records_v8""")

        connection.execute("""CREATE TABLE demand_profiles (
            id TEXT PRIMARY KEY, match_record_id TEXT, requirement_text TEXT NOT NULL,
            industry_tags TEXT, capability_tags TEXT, delivery_type_tags TEXT, region_tags TEXT,
            complexity_level TEXT, urgency_level TEXT, project_keywords TEXT,
            matched_partner_count INTEGER, top_partner_names TEXT, supply_status TEXT, gap_analysis TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (match_record_id) REFERENCES match_records(id) ON DELETE RESTRICT ON UPDATE RESTRICT)""")
        connection.execute("INSERT INTO demand_profiles SELECT * FROM demand_profiles_v8")

        connection.execute("""CREATE TABLE project_opportunities (
            id TEXT PRIMARY KEY, match_record_id TEXT, requirement_text TEXT,
            customer_name TEXT, project_name TEXT, industry TEXT, region TEXT,
            project_stage TEXT, business_needs TEXT, technical_needs TEXT,
            delivery_needs TEXT, qualification_requirements TEXT, case_requirements TEXT,
            onsite_requirement TEXT, timeline_requirement TEXT, cloud_platform_preference TEXT,
            matched_capability_tags TEXT, unmatched_capability_signals TEXT,
            recommended_partner_ids TEXT, recommended_partner_names TEXT,
            supply_status TEXT, completeness_score REAL, missing_fields TEXT,
            follow_up_questions TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY (match_record_id) REFERENCES match_records(id) ON DELETE RESTRICT ON UPDATE RESTRICT)""")
        connection.execute("INSERT INTO project_opportunities SELECT * FROM project_opportunities_v8")

        connection.execute("""CREATE TABLE capability_tag_suggestions (
            id TEXT PRIMARY KEY, suggested_name TEXT NOT NULL, suggested_category_id TEXT,
            suggested_category_name TEXT, description TEXT, evidence_text TEXT,
            source_requirement TEXT, source_match_record_id TEXT, confidence REAL DEFAULT 0.5,
            occurrence_count INTEGER DEFAULT 1, status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, adopted_at TEXT,
            FOREIGN KEY (source_match_record_id) REFERENCES match_records(id) ON DELETE RESTRICT ON UPDATE RESTRICT)""")
        connection.execute("INSERT INTO capability_tag_suggestions SELECT * FROM capability_tag_suggestions_v8")

        connection.execute("DROP TABLE demand_profiles_v8")
        connection.execute("DROP TABLE project_opportunities_v8")
        connection.execute("DROP TABLE capability_tag_suggestions_v8")
        connection.execute("DROP TABLE match_records_v8")
        connection.execute("UPDATE app_metadata SET value = '9' WHERE key = 'schema_version'")

        violations = []
        for table in (
            "match_records", "demand_profiles", "project_opportunities", "capability_tag_suggestions",
        ):
            violations.extend(connection.execute(f"PRAGMA foreign_key_check({table})").fetchall())
        if violations:
            raise RuntimeError(f"v9 migration produced {len(violations)} foreign key violations")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


@contextmanager
def get_readonly_db() -> Iterator[sqlite3.Connection]:
    """Open existing storage without creating a database or allowing writes."""
    connection = sqlite3.connect(f"{DATABASE_PATH.resolve().as_uri()}?mode=ro", uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def recover_stale_tasks(
    *, record_id: str | None = None, owner_user_id: str | None = None,
    stale_after_seconds: int | None = None,
) -> int:
    """Make interrupted in-flight tasks retryable without a background queue."""
    if stale_after_seconds is None:
        try:
            stale_after_seconds = int(os.getenv("TASK_STALE_SECONDS", "900"))
        except ValueError:
            stale_after_seconds = 900
    stale_after_seconds = max(stale_after_seconds, 1)
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)).isoformat()
    conditions = ["task_status IN ('matching', 'enriching')", "updated_at < ?"]
    params: list[object] = [cutoff]
    if record_id:
        conditions.append("id = ?")
        params.append(record_id)
    if owner_user_id:
        conditions.append("owner_user_id = ?")
        params.append(owner_user_id)
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.execute(
            f"""UPDATE match_records
                    SET task_status = 'failed', last_error_stage = 'interrupted', updated_at = ?
                  WHERE {' AND '.join(conditions)}""",
            [now, *params],
        )
        return cursor.rowcount


def initialize_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE_PATH, timeout=30) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT OR IGNORE INTO app_metadata (key, value) VALUES ('schema_version', '8')")
        connection.execute("CREATE TABLE IF NOT EXISTS partners (id TEXT PRIMARY KEY, name TEXT NOT NULL, intro TEXT, created_at TEXT NOT NULL)")
        existing_columns = {row[1] for row in connection.execute("PRAGMA table_info(partners)")}
        for column in ("capabilities", "service_areas", "industries", "ai_profile"):
            if column not in existing_columns:
                connection.execute(f"ALTER TABLE partners ADD COLUMN {column} TEXT")
        _ensure_column(connection, "partners", "status", "TEXT NOT NULL DEFAULT 'active'")
        _ensure_column(connection, "partners", "updated_at", "TEXT")
        connection.execute("CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, partner_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT, created_at TEXT NOT NULL, FOREIGN KEY (partner_id) REFERENCES partners(id))")
        connection.execute("CREATE TABLE IF NOT EXISTS deliverables (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, filename TEXT NOT NULL, file_path TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY (case_id) REFERENCES cases(id))")
        connection.execute("""CREATE TABLE IF NOT EXISTS partner_documents (
            id TEXT PRIMARY KEY, partner_id TEXT NOT NULL, filename TEXT NOT NULL, file_path TEXT NOT NULL,
            file_type TEXT NOT NULL, doc_category TEXT, extracted_text TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY (partner_id) REFERENCES partners(id))""")
        connection.execute("""CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, hashed_password TEXT NOT NULL,
            display_name TEXT, role TEXT DEFAULT 'user', created_at TEXT NOT NULL)""")
        _ensure_column(connection, "users", "department", "TEXT")
        _ensure_column(connection, "users", "status", "TEXT NOT NULL DEFAULT 'active'")
        _ensure_column(connection, "users", "must_change_password", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "users", "token_version", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "users", "last_login_at", "TEXT")
        _ensure_column(connection, "users", "failed_login_count", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "users", "locked_until", "TEXT")
        _ensure_column(connection, "users", "password_changed_at", "TEXT")
        _ensure_column(connection, "users", "created_by", "TEXT")
        _ensure_column(connection, "users", "updated_at", "TEXT")
        connection.execute("UPDATE users SET status = 'active' WHERE status IS NULL OR status = ''")
        connection.execute("UPDATE users SET role = 'user' WHERE role NOT IN ('user', 'admin')")
        connection.execute("UPDATE users SET updated_at = created_at WHERE updated_at IS NULL")
        connection.execute("""CREATE TABLE IF NOT EXISTS match_records (
            id TEXT PRIMARY KEY, requirement TEXT NOT NULL, recommendations_json TEXT NOT NULL,
            created_at TEXT NOT NULL, created_by TEXT)""")
        _ensure_column(connection, "match_records", "owner_user_id", "TEXT")
        _ensure_column(connection, "match_records", "archived_at", "TEXT")
        connection.execute("""CREATE TABLE IF NOT EXISTS user_audit_logs (
            id TEXT PRIMARY KEY, actor_user_id TEXT, action TEXT NOT NULL,
            target_user_id TEXT, summary TEXT, ip_address TEXT, created_at TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS user_applications (
            id TEXT PRIMARY KEY, username TEXT NOT NULL, display_name TEXT NOT NULL,
            department TEXT, contact TEXT, reason TEXT, password_hash TEXT,
            status TEXT NOT NULL DEFAULT 'pending', review_note TEXT,
            reviewed_by TEXT, reviewed_at TEXT, user_id TEXT,
            applicant_ip TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY (reviewed_by) REFERENCES users(id), FOREIGN KEY (user_id) REFERENCES users(id))""")
        users = connection.execute("SELECT id, username FROM users").fetchall()
        for user_id, username in users:
            connection.execute(
                "UPDATE match_records SET owner_user_id = ? WHERE owner_user_id IS NULL AND (created_by = ? OR created_by = ?)",
                (user_id, user_id, username),
            )
        connection.execute("""CREATE TABLE IF NOT EXISTS demand_profiles (
            id TEXT PRIMARY KEY, match_record_id TEXT, requirement_text TEXT NOT NULL,
            industry_tags TEXT, capability_tags TEXT, delivery_type_tags TEXT, region_tags TEXT,
            complexity_level TEXT, urgency_level TEXT, project_keywords TEXT,
            matched_partner_count INTEGER, top_partner_names TEXT, supply_status TEXT, gap_analysis TEXT,
            created_at TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS capability_tags (
            id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, category TEXT NOT NULL,
            description TEXT, enabled INTEGER DEFAULT 1, sort_order INTEGER DEFAULT 0,
            is_preset INTEGER DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        now = datetime.now(timezone.utc).isoformat()

        connection.execute("""CREATE TABLE IF NOT EXISTS capability_tag_suggestions (
            id TEXT PRIMARY KEY, suggested_name TEXT NOT NULL, suggested_category_id TEXT,
            suggested_category_name TEXT, description TEXT, evidence_text TEXT,
            source_requirement TEXT, source_match_record_id TEXT, confidence REAL DEFAULT 0.5,
            occurrence_count INTEGER DEFAULT 1, status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, adopted_at TEXT)""")

        # Seed preset capability tag categories
        connection.execute("""CREATE TABLE IF NOT EXISTS capability_tag_categories (
            id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL, code TEXT,
            description TEXT, enabled INTEGER DEFAULT 1, sort_order INTEGER DEFAULT 0,
            is_preset INTEGER DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        existing_cats = {row[0] for row in connection.execute("SELECT name FROM capability_tag_categories")}
        preset_cats = [
            ("AI 与智能体", "ai"), ("云平台与迁移", "cloud"), ("数据与数据库", "data"),
            ("应用开发与现代化", "dev"), ("运维与安全", "ops"), ("咨询与项目管理", "consulting"), ("其他", "other"),
        ]
        for cname, ccode in preset_cats:
            if cname not in existing_cats:
                connection.execute(
                    "INSERT INTO capability_tag_categories (id, name, code, description, enabled, sort_order, is_preset, created_at, updated_at) VALUES (?, ?, ?, ?, 1, 0, 1, ?, ?)",
                    (str(uuid.uuid4()), cname, ccode, "", now, now)
                )

        # Seed preset capability tags
        existing_tags = {row[0] for row in connection.execute("SELECT name FROM capability_tags")}
        preset_tags = [
            ("数据库", "数据与数据库"), ("昇腾云", "云平台与迁移"), ("盘古大模型", "AI 与智能体"),
            ("软件开发生产线（CodeArts）", "应用开发与现代化"), ("智能物联与制造平台", "其他"),
            ("数据仓库", "数据与数据库"), ("大数据", "数据与数据库"), ("集成与治理", "数据与数据库"),
            ("工业智能平台", "其他"), ("云桌面（Workspace）", "云平台与迁移"),
            ("上云规划实施", "云平台与迁移"), ("应用现代化", "应用开发与现代化"),
            ("解决方案集成实施", "应用开发与现代化"), ("容器", "应用开发与现代化"),
            ("数据管理分析与流通", "数据与数据库"), ("安全", "运维与安全"),
            ("公有云云运维", "运维与安全"), ("卓越运营", "运维与安全"),
            ("数字化转型咨询规划", "咨询与项目管理"), ("HCS基础设施规划设计与实施", "云平台与迁移"),
            ("HCS云运维", "运维与安全"), ("开发者技术支持", "咨询与项目管理"),
            ("SAP", "应用开发与现代化"), ("企业协同", "应用开发与现代化"),
        ]
        for name, category in preset_tags:
            if name not in existing_tags:
                connection.execute(
                    "INSERT INTO capability_tags (id, name, category, description, enabled, sort_order, is_preset, created_at, updated_at) VALUES (?, ?, ?, ?, 1, 0, 1, ?, ?)",
                    (str(uuid.uuid4()), name, category, "", now, now)
                )
        connection.execute("""CREATE TABLE IF NOT EXISTS project_opportunities (
            id TEXT PRIMARY KEY, match_record_id TEXT, requirement_text TEXT,
            customer_name TEXT, project_name TEXT, industry TEXT, region TEXT,
            project_stage TEXT, business_needs TEXT, technical_needs TEXT,
            delivery_needs TEXT, qualification_requirements TEXT, case_requirements TEXT,
            onsite_requirement TEXT, timeline_requirement TEXT, cloud_platform_preference TEXT,
            matched_capability_tags TEXT, unmatched_capability_signals TEXT,
            recommended_partner_ids TEXT, recommended_partner_names TEXT,
            supply_status TEXT, completeness_score REAL, missing_fields TEXT,
            follow_up_questions TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS model_configs (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, provider TEXT DEFAULT 'OpenAI Compatible',
            base_url TEXT, api_key TEXT, api_key_source TEXT DEFAULT 'env',
            api_key_env_name TEXT DEFAULT 'LLM_API_KEY', model_name TEXT,
            temperature REAL DEFAULT 0.3, top_p REAL DEFAULT 1.0, max_tokens INTEGER DEFAULT 131072,
            timeout_seconds INTEGER DEFAULT 60, enabled INTEGER DEFAULT 1, is_default INTEGER DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
        connection.execute("""CREATE TABLE IF NOT EXISTS model_usage_configs (
            scene_key TEXT PRIMARY KEY, scene_name TEXT NOT NULL, model_config_id TEXT,
            description TEXT, updated_at TEXT NOT NULL)""")
        existing_mc = connection.execute("SELECT COUNT(*) FROM model_configs").fetchone()[0]
        if existing_mc == 0:
            env_base = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
            env_model = os.getenv("LLM_MODEL", "gpt-4o")
            connection.execute(
                "INSERT INTO model_configs (id, name, provider, base_url, api_key, api_key_source, api_key_env_name, model_name, temperature, top_p, max_tokens, timeout_seconds, enabled, is_default, created_at, updated_at) VALUES (?, ?, ?, ?, NULL, 'env', 'LLM_API_KEY', ?, 0.3, 1.0, 131072, 60, 1, 1, ?, ?)",
                (str(uuid.uuid4()), "当前默认模型配置", "OpenAI Compatible", env_base, env_model, now, now)
            )
        existing_muc = connection.execute("SELECT COUNT(*) FROM model_usage_configs").fetchone()[0]
        if existing_muc == 0:
            scenes = [("partner_profile", "伙伴画像生成"), ("partner_match", "智能匹配"), ("demand_profile", "需求画像分析"), ("tag_suggestion", "AI 标签建议"), ("recommendation_summary", "推荐说明生成"), ("default", "系统默认")]
            for sk, sn in scenes:
                connection.execute("INSERT OR IGNORE INTO model_usage_configs (scene_key, scene_name, model_config_id, description, updated_at) VALUES (?, ?, NULL, '', ?)", (sk, sn, now))
        connection.execute("UPDATE partners SET status = 'active' WHERE status IS NULL OR status = ''")
        connection.execute("UPDATE partners SET updated_at = created_at WHERE updated_at IS NULL")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_users_status_role ON users(status, role)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_user_audit_created ON user_audit_logs(created_at DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_user_applications_status_created ON user_applications(status, created_at DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_user_applications_username ON user_applications(username)")
        _migrate_to_v9(connection)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_match_records_owner_archive_created ON match_records(owner_user_id, archived_at, created_at DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_match_records_archive_created ON match_records(archived_at, created_at DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_demand_profiles_match ON demand_profiles(match_record_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_project_opportunities_match ON project_opportunities(match_record_id)")
        connection.commit()
        from .enablement_schema import migrate_to_v10, migrate_to_v11
        migrate_to_v10(connection)
        migrate_to_v11(connection)
        from .development_schema import migrate_to_v12
        migrate_to_v12(connection)
