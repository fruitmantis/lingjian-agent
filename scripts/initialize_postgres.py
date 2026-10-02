"""Explicitly initialize a NEW, empty PostgreSQL schema. Never reset an existing database."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.config import database_url
from backend.app.postgres_storage import initialize_empty_schema

if __name__ == '__main__':
    try:
        initialize_empty_schema(database_url())
        print('Initialized empty PostgreSQL schema to version 19')
    except (RuntimeError, ValueError) as error:
        print('PostgreSQL initialization refused: ' + str(error), file=sys.stderr)
        raise SystemExit(1)
    except Exception as error:
        print('PostgreSQL connection or initialization failed (' + type(error).__name__ + '); check private DATABASE_URL, database permissions and server availability; no fallback or reset', file=sys.stderr)
        raise SystemExit(1)
