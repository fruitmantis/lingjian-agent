"""PostgreSQL runtime storage. Startup verifies an explicitly initialized schema."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator
from .config import uploads_path, chroma_path, database_url
from .postgres_storage import Connection, connect, verify_schema

UPLOADS_DIR = uploads_path()
CHROMA_DIR = chroma_path()

@contextmanager
def get_readonly_db() -> Iterator[Connection]:
    with connect(database_url(), readonly=True) as connection:
        yield connection

@contextmanager
def get_db() -> Iterator[Connection]:
    with connect(database_url()) as connection:
        yield connection

def recover_stale_tasks(
    *, record_id: str | None = None, owner_user_id: str | None = None,
    stale_after_seconds: int | None = None, startup: bool = False,
) -> int:
    """Recover only expired runs, using their accepted execution timeout snapshot."""
    from .model_timeout_settings import get_settings
    from . import match_understanding, task_progress
    from .error_diagnostics import record_error
    current=datetime.now(timezone.utc);stamp=current.isoformat();recovered=0
    with get_db() as conn:
        conn.lock_writer()
        rows=conn.execute("SELECT id,task_status,updated_at FROM match_records WHERE task_status IN ('matching','enriching') AND (? IS NULL OR id=?) AND (? IS NULL OR owner_user_id=?)",(record_id,record_id,owner_user_id,owner_user_id)).fetchall()
        for row in rows:
            snapshot=match_understanding.load(conn,row['id']) or {}
            policy=get_settings(conn,agent_id='partner_match',execution=snapshot.get('agent_execution'))
            budget=max(stale_after_seconds,1) if stale_after_seconds is not None else max(900,policy.match_run_budget() if row['task_status']=='matching' else policy.run_budget())
            if not startup and (current-datetime.fromisoformat(row['updated_at'])).total_seconds()<budget:continue
            conn.execute("UPDATE match_records SET task_status='failed',last_error_stage='interrupted',last_error_details=NULL,updated_at=? WHERE id=?",(stamp,row['id']))
            if snapshot:
                from .runtime_bridge import interrupt_operations
                interrupt_operations(conn,(snapshot.get('progress') or {}).get('run_id'))
                task_progress.finish(snapshot.get('progress'),failed=True,finished_at=stamp)
                match_understanding.save(conn,row['id'],snapshot)
            record_error(RuntimeError('Service restart interrupted unfinished matching' if startup else 'Unfinished matching exceeded the recovery deadline'),'interrupted',task_id=row['id'])
            recovered+=1
    return recovered


def initialize_storage() -> None:
    verify_schema(database_url())
