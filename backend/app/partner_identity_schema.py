"""Explicit schema 24 -> 25: nullable, manually maintained partner identities.

No backfill or business-row rewrite. Preserve the verified pre-migration backup for
rollback into a separate database; never discard maintained identities automatically.
"""


def migrate(conn):
    conn.lock_writer()
    version = conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]
    if version == '25':
        return {'schema_version': 25, 'already_current': True}
    if version != '24':
        raise RuntimeError('Partner identity migration requires schema 24')
    conn.execute('ALTER TABLE partners ADD COLUMN identities TEXT')
    conn.execute("UPDATE app_metadata SET value='25' WHERE key='schema_version'")
    return {'schema_version': 25, 'added_column': 'partners.identities'}
