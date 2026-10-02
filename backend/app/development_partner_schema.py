"""Schema 19: development tasks may use self-reported context without a partner."""

TABLES = ('development_plans', 'development_requests')


def verify_optional_partner(conn):
    for table in TABLES:
        nullable = conn.execute("SELECT is_nullable FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=? AND column_name='target_partner_id'", (table,)).fetchone()
        if not nullable or nullable[0] != 'YES':
            raise RuntimeError('Optional development partner requires explicit schema 19 migration')
        # PostgreSQL keeps validating every non-NULL real ID after DROP NOT NULL.
        foreign_keys = conn.execute("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid=to_regclass(?) AND contype='f' AND convalidated", (table,))
        if not any('FOREIGN KEY (target_partner_id) REFERENCES partners(id)' in row[0] for row in foreign_keys):
            raise RuntimeError('Development partner foreign key is missing')


def migrate(conn, fault=None):
    version = str(conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0])
    if version == '19':
        verify_optional_partner(conn)
        return {'schema_version': 19, 'already_current': True}
    if version != '18':
        raise RuntimeError('Expected schema 18; no automatic historical migration')
    for table in TABLES:
        conn.execute(f'ALTER TABLE {table} ALTER COLUMN target_partner_id DROP NOT NULL')
    verify_optional_partner(conn)
    if fault:
        fault()
    conn.execute("UPDATE app_metadata SET value='19' WHERE key='schema_version'")
    return {'schema_version': 19, 'nullable_partner_tables': list(TABLES), 'partner_foreign_keys_preserved': True}


def rollback(conn):
    """Operator-only transaction: refuse rollback once unlinked tasks exist; never rewrite rows."""
    version = str(conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0])
    if version != '19':
        raise RuntimeError('Expected schema 19')
    # Lock before checking so no concurrent unlinked task can enter between check and DDL.
    conn.execute('LOCK TABLE development_plans, development_requests IN ACCESS EXCLUSIVE MODE')
    for table in TABLES:
        if conn.execute(f'SELECT 1 FROM {table} WHERE target_partner_id IS NULL LIMIT 1').fetchone():
            raise RuntimeError('Unlinked tasks exist; rollback would require data loss and is refused')
    for table in TABLES:
        conn.execute(f'ALTER TABLE {table} ALTER COLUMN target_partner_id SET NOT NULL')
    conn.execute("UPDATE app_metadata SET value='18' WHERE key='schema_version'")
    return {'schema_version': 18, 'business_rows_unchanged': True}
