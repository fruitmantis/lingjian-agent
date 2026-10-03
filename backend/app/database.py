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
    """Make interrupted in-flight tasks retryable without a background queue."""
    if stale_after_seconds is None:
        from .model_timeout_settings import get_settings
        policy = get_settings()
        matching_budget = max(900, policy.match_run_budget())
        enriching_budget = max(900, policy.run_budget())
    else:
        matching_budget = enriching_budget = max(stale_after_seconds, 1)
    current = datetime.now(timezone.utc)
    matching_cutoff = (current - timedelta(seconds=matching_budget)).isoformat()
    enriching_cutoff = (current - timedelta(seconds=enriching_budget)).isoformat()
    conditions = ["((task_status = 'matching' AND updated_at < ?) OR (task_status = 'enriching' AND updated_at < ?))"]
    params: list[object] = [matching_cutoff, enriching_cutoff]
    if startup:
        conditions = ["task_status IN ('matching','enriching')"]
        params = []
    if record_id:
        conditions.append("id = ?")
        params.append(record_id)
    if owner_user_id:
        conditions.append("owner_user_id = ?")
        params.append(owner_user_id)
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.execute(
            f"""UPDATE match_records
                    SET task_status = 'failed', last_error_stage = 'interrupted', last_error_details = NULL, updated_at = ?
                  WHERE {' AND '.join(conditions)} RETURNING id""",
            [now, *params],
        )
        rows = cursor.fetchall()
        from .error_diagnostics import record_error
        for row in rows:
            from . import match_understanding, task_progress
            snapshot = match_understanding.load(conn, row['id'])
            if snapshot:
                from .runtime_bridge import interrupt_operations
                interrupt_operations(conn,(snapshot.get('progress') or {}).get('run_id'))
                task_progress.finish(snapshot.get('progress'), failed=True, finished_at=now)
                match_understanding.save(conn, row['id'], snapshot)
            record_error(RuntimeError('Service restart interrupted unfinished matching' if startup else 'Unfinished matching exceeded the recovery deadline'), 'interrupted', task_id=row['id'])
        return len(rows)


def initialize_storage() -> None:
    verify_schema(database_url())
