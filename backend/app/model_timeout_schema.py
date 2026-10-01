"""Schema 18 removes the obsolete per-model timeout; policy lives in app_metadata."""
from .model_timeout_settings import KEY, TimeoutSettings


def migrate(conn, fault=None):
    version = str(conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0])
    if version == '18':
        return {'schema_version': 18, 'already_current': True}
    if version != '17':
        raise RuntimeError('Expected schema 17; no automatic historical migration')
    columns = {row[0] for row in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='model_configs'")}
    if 'timeout_seconds' in columns:
        conn.execute('ALTER TABLE model_configs DROP COLUMN timeout_seconds')
    conn.execute('INSERT INTO app_metadata (key,value) VALUES (?,?) ON CONFLICT(key) DO NOTHING',
                 (KEY, TimeoutSettings().model_dump_json()))
    if fault:
        fault()
    conn.execute("UPDATE app_metadata SET value='18' WHERE key='schema_version'")
    return {'schema_version': 18, 'removed_model_timeout_column': 'timeout_seconds' in columns}
