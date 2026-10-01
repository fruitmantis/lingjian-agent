"""Fail closed before fixtures write anything outside their disposable PostgreSQL schema."""
import os
import re
from pathlib import Path
from backend.app.postgres_storage import validated_url

POSTGRES_TEST_DATABASES = frozenset({'banfei_validation', 'banfei_agent_test'})
SCHEMA_PATTERN = re.compile(r'validation_[0-9a-f]{32}')


def validation_url(value, *, scoped=False):
    if not value:
        raise RuntimeError('BANFEI_TEST_DATABASE_URL is required; no test database fallback')
    try:
        parsed = validated_url(value)
    except ValueError:
        raise RuntimeError('Tests require PostgreSQL with psycopg') from None
    if parsed.database not in POSTGRES_TEST_DATABASES or parsed.host not in ('127.0.0.1', 'localhost'):
        raise RuntimeError('Tests require the dedicated local PostgreSQL validation database')
    # Query overrides must not redirect a verified host/database or inherit public search_path.
    if set(parsed.query) - {'options'}:
        raise RuntimeError('Unsupported validation database URL options')
    options = parsed.query.get('options', '')
    if scoped:
        if not isinstance(options, str) or not options.startswith('-csearch_path=') or not SCHEMA_PATTERN.fullmatch(options.removeprefix('-csearch_path=')):
            raise RuntimeError('Tests require a unique validation schema; public is forbidden')
    elif options:
        raise RuntimeError('Base validation URL must not specify a schema')
    return parsed


def require_test_database():
    parsed = validation_url(os.environ.get('DATABASE_URL', ''), scoped=True)
    uploads = os.environ.get('LINGJIAN_UPLOADS_DIR', '')
    if not uploads or not Path(uploads).resolve().is_relative_to('/tmp'):
        raise RuntimeError('Test fixtures require a /tmp uploads directory')
    return parsed
