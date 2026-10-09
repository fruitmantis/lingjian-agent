"""Explicit additive schema-20 extension; no profiles or source records are rewritten."""
def migrate(conn):
    if conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]!='20':
        raise RuntimeError('Expected schema 20')
    conn.lock_writer()
    conn.execute("ALTER TABLE partners ADD COLUMN IF NOT EXISTS profile_chapter_meta TEXT DEFAULT '{}' ")
    return {'schema_version':20,'profile_chapter_meta_added':True,'existing_profiles_and_sources_retained':True}
