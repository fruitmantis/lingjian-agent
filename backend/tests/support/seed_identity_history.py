"""One private task for identity logout E2E; dedicated validation storage only."""
from datetime import datetime, timezone
import os
import sys
import uuid
from sqlalchemy.engine import make_url

from backend.tests.support.model_test_boundary import require_test_database
os.environ['DATABASE_URL'] = os.environ['PLAYWRIGHT_DATABASE_URL']
require_test_database()
from backend.app.database import get_db
with get_db() as conn:
    conn.lock_writer()
    user = conn.execute("SELECT id FROM users WHERE id=? AND role='user'", (sys.argv[1],)).fetchone()
    if not user:
        raise SystemExit('Synthetic ordinary identity required')
    task_id, now = str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()
    conn.execute("""INSERT INTO match_records(id,requirement,recommendations_json,owner_user_id,created_at,updated_at,task_status)
                    VALUES (?,'退出身份保留的个人任务','[]',?,?,?,'ready')""", (task_id, user['id'], now, now))
print(task_id)
