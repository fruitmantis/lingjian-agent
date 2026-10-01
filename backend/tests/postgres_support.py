"""Create and remove only schemas owned by this invocation in the dedicated PG test DB."""
from contextlib import contextmanager
import os
import uuid
import hashlib
import json
from sqlalchemy import text, inspect
from backend.app.postgres_storage import engine_for
from backend.tests.support.model_test_boundary import validation_url


@contextmanager
def empty_postgres_schema():
    parsed = validation_url(os.environ.get('BANFEI_TEST_DATABASE_URL', ''))
    base = parsed.render_as_string(hide_password=False)
    name = 'validation_' + uuid.uuid4().hex
    engine = engine_for(base)
    # No IF NOT EXISTS: collisions fail; a schema we did not create is never removed.
    with engine.begin() as conn:
        conn.execute(text('CREATE SCHEMA ' + name))
    scoped = parsed.update_query_dict({'options': '-csearch_path=' + name}).render_as_string(hide_password=False)
    try:
        yield scoped
    finally:
        engine_for(scoped).dispose()
        with engine.begin() as conn:
            conn.execute(text('DROP SCHEMA ' + name + ' CASCADE'))


def snapshot(conn, exclude_fields=None):
    """Hash every row in the current test schema, including tables not in ORM metadata."""
    from backend.app.postgres_storage import Connection
    raw = conn.connection if isinstance(conn, Connection) else conn
    result = {}
    for table in inspect(raw).get_table_names():
        fields = [c['name'] for c in inspect(raw).get_columns(table) if c['name'] not in (exclude_fields or {}).get(table, ())]
        quoted = ','.join('"' + c + '"' for c in fields)
        rows = [list(r) for r in raw.exec_driver_sql(f'SELECT {quoted} FROM "{table}"')]
        value = json.dumps(sorted(rows, key=lambda r: json.dumps(r, default=str)), ensure_ascii=False, default=str)
        result[table] = {'count': len(rows), 'hash': hashlib.sha256(value.encode()).hexdigest()}
    return result


def install_failure(conn, table, event, *, name='synthetic_failure', when=''):
    """Real server-side exception after earlier writes; PostgreSQL rolls back the transaction."""
    conn.execute(f"CREATE FUNCTION {name}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic failure' USING ERRCODE='23514'; END $$")
    conn.execute(f'CREATE TRIGGER {name} BEFORE {event} ON {table} FOR EACH ROW {when} EXECUTE FUNCTION {name}()')


def foreign_key_violations(conn):
    """Explicit anti-join audit in the disposable schema; PostgreSQL also enforces every FK."""
    raw = conn.connection
    inspector = inspect(raw)
    violations = []
    for table in inspector.get_table_names():
        for fk in inspector.get_foreign_keys(table):
            pairs = list(zip(fk['constrained_columns'], fk['referred_columns']))
            nonnull = ' AND '.join(f'a."{a}" IS NOT NULL' for a, _ in pairs)
            join = ' AND '.join(f'a."{a}"=b."{b}"' for a, b in pairs)
            count = raw.exec_driver_sql(f'SELECT count(*) FROM "{table}" a WHERE {nonnull} AND NOT EXISTS (SELECT 1 FROM "{fk["referred_table"]}" b WHERE {join})').scalar()
            if count: violations.append((table, fk['name'], count))
    return violations
