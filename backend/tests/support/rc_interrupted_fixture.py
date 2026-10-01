"""Presentation-only fixture. Real process interruption is tested in test_phase_d_process.
Never import into application startup or use outside the dedicated synthetic E2E DB.
"""
import sys,os
from contextlib import contextmanager
from pathlib import Path

def main():
 from backend.tests.support.model_test_boundary import require_test_database
 require_test_database()
 from backend.app.database import get_db
 connection=get_db()
 with connection as conn:
  conn.lock_writer()
  run=conn.execute("SELECT r.id FROM development_runs r JOIN development_plans p ON p.id=r.plan_id JOIN development_requests q ON q.id=p.request_id WHERE p.id=? AND p.owner_user_id='user-a-id' AND p.active_run_id IS NULL AND p.current_version_id IS NOT NULL AND r.status='failed' AND (q.payload_json::jsonb ->> 'development_goal') ILIKE 'RC 状态合成验证%' ORDER BY r.created_at DESC LIMIT 1",(sys.argv[1],)).fetchone()
  assert run,'Only a completed RC synthetic failed revision may be used'
  conn.execute("UPDATE development_runs SET status='interrupted',error_stage='interrupted' WHERE id=?",(run[0],))
if __name__=='__main__':main()
