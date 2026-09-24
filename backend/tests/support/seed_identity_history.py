"""One private task for identity logout E2E; dedicated validation storage only."""
from datetime import datetime, timezone
import os
import sys
import uuid
from sqlalchemy.engine import make_url

url = os.getenv('PLAYWRIGHT_DATABASE_URL', '')
if url:
    parsed = make_url(url)
    if not parsed.drivername.startswith('postgresql') or parsed.database not in ('banfei_agent_test', 'banfei_validation') or parsed.host not in ('localhost', '127.0.0.1'):
        raise SystemExit('Dedicated local validation database required')
    os.environ['DATABASE_URL'] = url
else:
    os.environ['DATABASE_URL'] = 'sqlite://'
    os.environ['LINGJIAN_DATABASE_PATH'] = '/tmp/lingjian-enablement-e2e/app.db'
from backend.app.database import get_db
with get_db() as conn:
    conn.execute('BEGIN IMMEDIATE')
    user = conn.execute("SELECT id FROM users WHERE id=? AND role='user'", (sys.argv[1],)).fetchone()
    if not user:
        raise SystemExit('Synthetic ordinary identity required')
    task_id, now = str(uuid.uuid4()), datetime.now(timezone.utc).isoformat()
    conn.execute("""INSERT INTO match_records(id,requirement,recommendations_json,owner_user_id,created_at,updated_at,task_status)
                    VALUES (?,'退出身份保留的个人任务','[]',?,?,?,'ready')""", (task_id, user['id'], now, now))
print(task_id)
