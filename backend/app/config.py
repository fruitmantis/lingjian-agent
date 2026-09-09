"""Runtime configuration shared by the API, workers, and validation tests."""

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Load the project environment before modules such as auth and database read it.
# Existing process-level variables keep precedence over values from .env.
load_dotenv(PROJECT_ROOT / ".env", override=False)


HISTORICAL_JWT_SECRETS = {
    "lingjian-mvp-secret-key-change-in-production",
}


def get_jwt_secret_key() -> str:
    """Return a strong configured signing key or fail closed."""
    secret = os.getenv("JWT_SECRET_KEY", "").strip()
    if not secret:
        raise RuntimeError("JWT_SECRET_KEY is required; refusing to use an implicit signing key")
    if secret in HISTORICAL_JWT_SECRETS or len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY is weak or uses a retired historical value")
    return secret


def database_path() -> Path:
    configured = os.getenv("LINGJIAN_DATABASE_PATH", "").strip()
    return Path(configured).expanduser().resolve() if configured else PROJECT_ROOT / "data" / "app.db"


def uploads_path() -> Path:
    configured = os.getenv("LINGJIAN_UPLOADS_DIR", "").strip()
    return Path(configured).expanduser().resolve() if configured else PROJECT_ROOT / "data" / "uploads"


def chroma_path() -> Path:
    configured = os.getenv("LINGJIAN_CHROMA_DIR", "").strip()
    return Path(configured).expanduser().resolve() if configured else PROJECT_ROOT / "data" / "chroma"


def database_url() -> str:
    """Explicit backend selection; never silently fall back from PostgreSQL to SQLite."""
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("DATABASE_URL is required; no automatic SQLite fallback")
    if not value.startswith(("postgresql://", "postgresql+psycopg://", "sqlite://")):
        raise RuntimeError("Unsupported DATABASE_URL database type")
    return value
