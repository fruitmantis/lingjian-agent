import sqlite3
from contextlib import contextmanager
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
        connection.commit()
