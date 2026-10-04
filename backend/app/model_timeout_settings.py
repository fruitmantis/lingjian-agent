"""Execution-local timeout policies for fixed agents and independent processing."""
from pydantic import BaseModel, ConfigDict, Field
from .database import get_db, get_readonly_db

KEY = 'model_timeout_settings'


class TimeoutSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    timeoutSeconds: float = Field(default=300, gt=0, allow_inf_nan=False, strict=True)
    timeoutRetries: int = Field(default=3, ge=0, strict=True)

    def call_budget(self):
        return self.timeoutSeconds * (self.timeoutRetries + 1)

    def run_budget(self):
        # Understanding + answer, including retries and persistence headroom.
        return max(600, 2 * self.call_budget() + 60)

    def match_run_budget(self):
        # Task creation performs understanding before persistence; leave room for
        # all three calls and final writes when recovering an interrupted match.
        return max(900, 3 * self.call_budget() + 90)


def get_settings(connection=None, *, agent_id=None, execution=None) -> TimeoutSettings:
    from . import agent_settings
    selected=execution or agent_settings.current_execution()
    if selected is None or (agent_id and selected['agentId']!=agent_id):
        if connection is None:
            with get_readonly_db() as conn:return get_settings(conn,agent_id=agent_id,execution=execution)
        selected=agent_settings.execution(connection,agent_id or 'processing')
    return TimeoutSettings(timeoutSeconds=float(selected['timeoutSeconds']),timeoutRetries=selected['timeoutRetries'])


def describe():
    return get_settings().model_dump()


def save(settings: TimeoutSettings):
    """Compatibility helper for processing only; no global policy remains effective."""
    from . import agent_settings
    import json
    with get_db() as conn:
        conn.lock_writer();current=agent_settings.migrate(conn)
        current['processing'].update(settings.model_dump())
        conn.execute('UPDATE app_metadata SET value=? WHERE key=?',(json.dumps(current,ensure_ascii=False),agent_settings.KEY))
    return settings.model_dump()
