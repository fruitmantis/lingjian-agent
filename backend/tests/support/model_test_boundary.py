"""Fail closed before test fixtures can initialize or write a database."""
import os
from pathlib import Path
from urllib.parse import urlsplit


def require_test_database():
    path = Path(os.environ.get("LINGJIAN_DATABASE_PATH", "")).resolve()
    if not path.is_relative_to(Path("/tmp")):
        raise RuntimeError("Test fixtures require a /tmp data directory")
    target = os.environ.get("DATABASE_URL", "")
    if target.startswith("postgresql"):
        parsed = urlsplit(target)
        if parsed.hostname not in ("localhost", "127.0.0.1") or parsed.path != "/banfei_validation":
            raise RuntimeError("Test fixtures require the dedicated local validation database")
    elif target != "sqlite://":
        raise RuntimeError("Test fixtures require an explicit isolated database")
