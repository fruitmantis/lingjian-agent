"""Explicit schema 22 -> 23 capacity column. Never called at application startup."""

def migrate(conn):
    conn.lock_writer()
    row = conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()
    if not row or row[0] != '22':
        raise RuntimeError('Model context migration requires schema 22')
    conn.execute('ALTER TABLE model_configs ADD COLUMN context_window_tokens INTEGER')
    conn.execute('ALTER TABLE model_configs ADD CONSTRAINT ck_model_context_window_positive CHECK (context_window_tokens IS NULL OR context_window_tokens > 0)')
    conn.execute("UPDATE app_metadata SET value='23' WHERE key='schema_version'")
    return {'schema_version': '23', 'models': conn.execute('SELECT count(*) FROM model_configs').fetchone()[0]}
