import sqlite3
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "app.db"
UPLOADS_DIR = DATA_DIR / "uploads"
CHROMA_DIR = DATA_DIR / "chroma"


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT OR IGNORE INTO app_metadata (key, value) VALUES ('schema_version', '6')")
        connection.execute("CREATE TABLE IF NOT EXISTS partners (id TEXT PRIMARY KEY, name TEXT NOT NULL, intro TEXT, created_at TEXT NOT NULL)")
        existing_columns = {row[1] for row in connection.execute("PRAGMA table_info(partners)")}
        for column in ("capabilities", "service_areas", "industries", "ai_profile"):
            if column not in existing_columns:
                connection.execute(f"ALTER TABLE partners ADD COLUMN {column} TEXT")
        connection.execute("CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, partner_id TEXT NOT NULL, title TEXT NOT NULL, description TEXT, created_at TEXT NOT NULL, FOREIGN KEY (partner_id) REFERENCES partners(id))")
        connection.execute("CREATE TABLE IF NOT EXISTS deliverables (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, filename TEXT NOT NULL, file_path TEXT NOT NULL, created_at TEXT NOT NULL, FOREIGN KEY (case_id) REFERENCES cases(id))")
        connection.execute("""CREATE TABLE IF NOT EXISTS partner_documents (
            id TEXT PRIMARY KEY, partner_id TEXT NOT NULL, filename TEXT NOT NULL, file_path TEXT NOT NULL,
            file_type TEXT NOT NULL, doc_category TEXT, extracted_text TEXT, created_at TEXT NOT NULL,
            FOREIGN KEY (partner_id) REFERENCES partners(id))""")
        connection.execute("""CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, hashed_password TEXT NOT NULL,
            display_name TEXT, role TEXT DEFAULT 'user', created_at TEXT NOT NULL)""")
        connection.execute("UPDATE app_metadata SET value = '6' WHERE key = 'schema_version'")
        connection.execute("""CREATE TABLE IF NOT EXISTS match_records (
            id TEXT PRIMARY KEY, requirement TEXT NOT NULL, recommendations_json TEXT NOT NULL,
            created_at TEXT NOT NULL, created_by TEXT)""")
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
        connection.execute("""CREATE TABLE IF NOT EXISTS model_configs (
            id TEXT PRIMARY KEY, name TEXT NOT NULL, provider TEXT DEFAULT 'OpenAI Compatible',
            base_url TEXT, api_key TEXT, api_key_source TEXT DEFAULT 'env',
            api_key_env_name TEXT DEFAULT 'LLM_API_KEY', model_name TEXT,
            temperature REAL DEFAULT 0.3, top_p REAL DEFAULT 1.0, max_tokens INTEGER DEFAULT 4096,
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
                "INSERT INTO model_configs (id, name, provider, base_url, api_key, api_key_source, api_key_env_name, model_name, temperature, top_p, max_tokens, timeout_seconds, enabled, is_default, created_at, updated_at) VALUES (?, ?, ?, ?, NULL, 'env', 'LLM_API_KEY', ?, 0.3, 1.0, 4096, 60, 1, 1, ?, ?)",
                (str(uuid.uuid4()), "当前默认模型配置", "OpenAI Compatible", env_base, env_model, now, now)
            )
        existing_muc = connection.execute("SELECT COUNT(*) FROM model_usage_configs").fetchone()[0]
        if existing_muc == 0:
            scenes = [("partner_profile", "伙伴画像生成"), ("partner_match", "智能匹配"), ("demand_profile", "需求画像分析"), ("tag_suggestion", "AI 标签建议"), ("recommendation_summary", "推荐说明生成"), ("default", "系统默认")]
            for sk, sn in scenes:
                connection.execute("INSERT OR IGNORE INTO model_usage_configs (scene_key, scene_name, model_config_id, description, updated_at) VALUES (?, ?, NULL, '', ?)", (sk, sn, now))
        connection.commit()
