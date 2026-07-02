import sqlite3
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
        now = datetime.now(timezone.utc).isoformat()
        for name, category in preset_tags:
            if name not in existing_tags:
                connection.execute(
                    "INSERT INTO capability_tags (id, name, category, description, enabled, sort_order, is_preset, created_at, updated_at) VALUES (?, ?, ?, ?, 1, 0, 1, ?, ?)",
                    (str(uuid.uuid4()), name, category, "", now, now)
                )
        connection.commit()
