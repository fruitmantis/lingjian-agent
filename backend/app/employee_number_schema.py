"""Explicit schema 20 -> 21: optional self-reported employee label only."""
def migrate(conn, fault=None):
    conn.lock_writer()
    version = conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]
    if version not in ('20', '21'):
        raise RuntimeError('Expected schema 20 or 21')
    conn.execute('ALTER TABLE users ADD COLUMN IF NOT EXISTS employee_number TEXT')
    if fault:
        fault()
    conn.execute("UPDATE app_metadata SET value='21' WHERE key='schema_version'")
    return {'schema_version': 21, 'employee_number_optional': True, 'existing_identities_preserved': True}
