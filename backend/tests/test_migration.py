import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
V8_BACKUP = PROJECT_ROOT / "data" / "app.db.bak-before-task-hardening-v9-20260904"
CORE_TABLES = [
    "users", "user_applications", "user_audit_logs", "match_records", "demand_profiles",
    "project_opportunities", "capability_tag_suggestions", "partners", "cases",
    "partner_documents", "deliverables",
]


def snapshot(path: Path) -> dict:
    connection = sqlite3.connect(path)
    try:
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in CORE_TABLES
        }
        return {
            "version": connection.execute("SELECT value FROM app_metadata WHERE key = 'schema_version'").fetchone()[0],
            "counts": counts,
            "foreign_keys": connection.execute("PRAGMA foreign_key_check").fetchall(),
            "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
            "unowned": connection.execute("SELECT COUNT(*) FROM match_records WHERE owner_user_id IS NULL").fetchone()[0],
        }
    finally:
        connection.close()


def run_migration(path: Path, uploads: Path) -> None:
    env = os.environ.copy()
    env.update({
        "LINGJIAN_DATABASE_PATH": str(path),
        "LINGJIAN_UPLOADS_DIR": str(uploads),
        "LINGJIAN_CHROMA_DIR": str(uploads.parent / "chroma"),
        "JWT_SECRET_KEY": "migration-validation-secret-0123456789-ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    })
    subprocess.run(
        [sys.executable, "-c", "from backend.app.database import initialize_storage; initialize_storage()"],
        cwd=PROJECT_ROOT, env=env, check=True, capture_output=True, text=True,
    )


def test_v8_backup_migrates_to_current_schema_idempotently_without_new_violations(tmp_path):
    assert V8_BACKUP.exists()
    migrated = tmp_path / "migration-replay.db"
    shutil.copy2(V8_BACKUP, migrated)
    before = snapshot(migrated)
    assert before["version"] == "8"
    assert before["counts"]["match_records"] == 48
    assert before["foreign_keys"] == [("cases", 3, "partners", 0), ("cases", 4, "partners", 0)]

    run_migration(migrated, tmp_path / "uploads")
    first = snapshot(migrated)
    assert first["version"] == "12"
    assert first["integrity"] == "ok"
    assert first["counts"] == before["counts"]
    assert first["unowned"] == 0
    assert first["foreign_keys"] == before["foreign_keys"]

    run_migration(migrated, tmp_path / "uploads")
    second = snapshot(migrated)
    assert second == first

    connection = sqlite3.connect(migrated)
    try:
        for table in ["match_records", "demand_profiles", "project_opportunities", "capability_tag_suggestions"]:
            assert connection.execute(f"PRAGMA foreign_key_check({table})").fetchall() == []
    finally:
        connection.close()
