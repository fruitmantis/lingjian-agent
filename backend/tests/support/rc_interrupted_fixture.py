"""Presentation-only fixture. Real process interruption is tested in test_phase_d_process.
Never import into application startup or use outside the dedicated synthetic E2E DB.
"""
import sqlite3,sys
from pathlib import Path

def main():
 db=Path('/tmp/lingjian-enablement-e2e/app.db')
 assert db.resolve()==db and db.is_file() and not db.is_symlink()
 with sqlite3.connect(db) as conn:
  conn.execute('BEGIN IMMEDIATE')
  run=conn.execute("SELECT r.id FROM development_runs r JOIN development_plans p ON p.id=r.plan_id JOIN development_requests q ON q.id=p.request_id WHERE p.id=? AND p.owner_user_id='user-a-id' AND p.active_run_id IS NULL AND p.confirmed_version_id IS NOT NULL AND r.status='failed' AND json_extract(q.payload_json,'$.development_goal') LIKE 'RC 状态合成验证%' ORDER BY r.created_at DESC LIMIT 1",(sys.argv[1],)).fetchone()
  assert run,'Only a completed RC synthetic failed revision may be used'
  conn.execute("UPDATE development_runs SET status='interrupted',error_stage='interrupted' WHERE id=?",(run[0],))
if __name__=='__main__':main()
