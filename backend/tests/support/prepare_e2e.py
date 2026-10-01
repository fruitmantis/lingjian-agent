"""Seed the owned PostgreSQL E2E schema; uploads and credentials use a private /tmp directory."""

import os
import json
from pathlib import Path


def main() -> None:
    from backend.tests.support.model_test_boundary import require_test_database
    parsed = require_test_database()
    validation_root = Path(os.environ['BANFEI_TEST_ROOT']).resolve()
    if validation_root.parent != Path('/tmp') or not validation_root.name.startswith('banfei-e2e-'):
        raise RuntimeError('Owned temporary browser directory required')
    from backend.app.postgres_storage import initialize_empty_schema
    initialize_empty_schema(os.environ['DATABASE_URL'])
    from backend.tests.support.seed_validation_db import seed
    seed()
    # Private, ephemeral browser credential: never stored in the repository.
    from backend.app.auth import create_token
    from backend.app.database import get_db
    with get_db() as conn:
        user = dict(conn.execute("SELECT id, username, display_name, department, role, status, must_change_password, token_version FROM users WHERE username = 'admin1'").fetchone())
    session = {"database": f"postgresql:{parsed.database}", "access_token": create_token(user["id"], user["username"], user["role"], user["token_version"]), "user": user}
    with get_db() as conn:
        fixture_users = [dict(row) for row in conn.execute("SELECT * FROM users")]
    sessions = {}
    with get_db() as conn:
        for u in fixture_users:
            sid = None
            if u['role'] == 'user':
                sid = 'fixture-session-'+u['id']
            u['identity_method'] = 'password' if u['role'] == 'admin' else 'key'
            sessions[u['username']] = {'access_token': create_token(u['id'], u['username'], u['role'], u['token_version'], session_id=sid), 'user': u}
    # Never persist password hashes in frontend fixture material.
    for value in sessions.values():
        value['user'].pop('hashed_password', None)
    with os.fdopen(os.open(validation_root / "identity-sessions.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        json.dump(sessions, stream)
    with os.fdopen(os.open(validation_root / "visual-session.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as stream:
        json.dump(session, stream)


if __name__ == "__main__":
    main()
