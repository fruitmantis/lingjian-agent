"""Create a clean, synthetic E2E database in the dedicated /tmp directory."""

import os
import json
import shutil
from pathlib import Path


def main() -> None:
    database = Path(os.environ["LINGJIAN_DATABASE_PATH"]).resolve()
    validation_root = Path("/tmp/lingjian-enablement-e2e").resolve()
    if database.parent != validation_root or database.name != "app.db":
        raise RuntimeError("refusing to reset a database outside the dedicated E2E directory")
    shutil.rmtree(validation_root, ignore_errors=True)
    validation_root.mkdir(parents=True)
    target = os.environ.get("DATABASE_URL", "sqlite://")
    os.environ["DATABASE_URL"] = "sqlite://"
    from backend.tests.support.seed_validation_db import seed
    seed()
    if target.startswith("postgresql"):
        from sqlalchemy.engine import make_url
        parsed = make_url(target)
        if parsed.database != "banfei_validation" or parsed.host not in ("127.0.0.1", "localhost"):
            raise RuntimeError("E2E requires the dedicated PostgreSQL validation database")
        import sqlite3
        with sqlite3.connect(database) as staged_fixture:
            staged_fixture.execute("CREATE TABLE IF NOT EXISTS _health_check (id INTEGER)")
        from scripts.migrate_sqlite_to_postgres import import_snapshot
        import_snapshot(database, target)
    os.environ["DATABASE_URL"] = target
    # Private, ephemeral browser credential: never stored in the repository.
    from backend.app.auth import create_token
    from backend.app.database import get_db
    with get_db() as conn:
        user = dict(conn.execute("SELECT id, username, display_name, department, role, status, must_change_password, token_version FROM users WHERE username = 'admin1'").fetchone())
    session = {"database": "postgresql:banfei_validation" if target.startswith("postgresql") else str(database), "access_token": create_token(user["id"], user["username"], user["role"], user["token_version"]), "user": user}
    with os.fdopen(os.open(validation_root / "visual-session.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        json.dump(session, stream)


if __name__ == "__main__":
    main()
