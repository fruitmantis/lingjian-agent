"""Disposable PostgreSQL schemas in the dedicated validation database only."""
from contextlib import contextmanager
import os
import uuid
from sqlalchemy import text
from sqlalchemy.engine import make_url
from backend.app.postgres_storage import engine_for


@contextmanager
def empty_postgres_schema():
    base=os.environ['BANFEI_TEST_DATABASE_URL']
    parsed=make_url(base)
    if parsed.database!='banfei_validation' or parsed.host not in ('127.0.0.1','localhost'):
        raise RuntimeError('Tests require the dedicated local banfei_validation database')
    name='validation_'+uuid.uuid4().hex
    engine=engine_for(base)
    with engine.begin() as conn:conn.execute(text('CREATE SCHEMA '+name))
    scoped=parsed.update_query_dict({'options':'-csearch_path='+name}).render_as_string(hide_password=False)
    try:yield scoped
    finally:
        engine_for(scoped).dispose()
        with engine.begin() as conn:conn.execute(text('DROP SCHEMA '+name+' CASCADE'))
