"""Schema 24: per-task requirement attachment (name + extracted text).

Explicit, additive and reversible: two nullable columns on match_records. Old rows keep
NULL, so no backfill and no business-row changes.
"""

TABLES = ('match_records',)


def _version(conn):
    return str(conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0])


def _columns(conn, table):
    rows = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name=? AND table_schema=current_schema()",
        (table,),
    ).fetchall()
    return {row[0] for row in rows}


def migrate(conn):
    version = _version(conn)
    if version == '24':
        return {'schema_version': 24, 'already_current': True}
    if version != '23':
        raise RuntimeError('Expected schema 23 before adding attachment columns')
    added = []
    for table in TABLES:
        existing = _columns(conn, table)
        for column in ('attachment_name', 'attachment_text'):
            if column not in existing:
                conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} TEXT')
                added.append(f'{table}.{column}')
    conn.execute("UPDATE app_metadata SET value='24' WHERE key='schema_version'")
    return {'schema_version': 24, 'added_columns': added}


def rollback(conn):
    version = _version(conn)
    if version == '23':
        return {'schema_version': 23, 'already_current': True}
    if version != '24':
        raise RuntimeError('Expected schema 24 before dropping attachment columns')
    removed = []
    for table in TABLES:
        existing = _columns(conn, table)
        for column in ('attachment_name', 'attachment_text'):
            if column in existing:
                conn.execute(f'ALTER TABLE {table} DROP COLUMN {column}')
                removed.append(f'{table}.{column}')
    conn.execute("UPDATE app_metadata SET value='23' WHERE key='schema_version'")
    return {'schema_version': 23, 'removed_columns': removed}
