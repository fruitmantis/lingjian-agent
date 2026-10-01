"""One persisted model timeout policy, managed by administrators."""
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


def get_settings(connection=None) -> TimeoutSettings:
    if connection is None:
        with get_readonly_db() as conn:
            return get_settings(conn)
    row = connection.execute('SELECT value FROM app_metadata WHERE key=?', (KEY,)).fetchone()
    return TimeoutSettings.model_validate_json(row[0]) if row else TimeoutSettings()


def describe():
    return get_settings().model_dump()


def save(settings: TimeoutSettings):
    with get_db() as conn:
        conn.execute('INSERT INTO app_metadata (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                     (KEY, settings.model_dump_json()))
    return settings.model_dump()
