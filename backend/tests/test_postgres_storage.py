"""PostgreSQL-specific transaction, migration and runtime regression."""
import json
import os
import sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text,inspect
from sqlalchemy.exc import IntegrityError,DBAPIError
from fastapi import HTTPException
from backend.app.database import get_db,get_readonly_db,initialize_storage,DATABASE_PATH
from backend.app.postgres_storage import engine_for,postgres_sql,bind_parameters
from backend.app import development_lifecycle as life
from backend.app.routers import partners
from .conftest import make_user,make_partner,auth_headers,make_task
from .test_development_lifecycle import prepared,start,complete,plan,result
from .postgres_support import empty_postgres_schema
from scripts.migrate_sqlite_to_postgres import import_snapshot,source_inventory,reconcile,sha

pytestmark=pytest.mark.skipif(not os.environ.get('BANFEI_TEST_DATABASE_URL'),reason='Dedicated PostgreSQL test database required')


def test_postgres_runtime_never_opens_sqlite(client,monkeypatch):
    def no_sqlite(*a,**kw):raise AssertionError('PostgreSQL runtime opened SQLite')
    monkeypatch.setattr(sqlite3,'connect',no_sqlite)
    initialize_storage()
    with get_db() as conn:assert conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]>=1
    with get_readonly_db() as conn:assert conn.execute('SELECT COUNT(*) FROM partners').fetchone()[0]==0
    assert client.get('/health').status_code==200


def test_url_required_and_no_fallback(monkeypatch):
    monkeypatch.delenv('DATABASE_URL')
    # config is already loaded: a missing connection URL fails, not opens data/app.db.
    with pytest.raises(RuntimeError,match='DATABASE_URL'):
        with get_db():pass


def test_readonly_database_rejects_writes(client):
    with pytest.raises(DBAPIError):
        with get_readonly_db() as conn:conn.execute("INSERT INTO partners(id,name,created_at) VALUES ('bad','Synthetic','now')")
    with get_db() as conn:assert conn.execute("SELECT 1 FROM partners WHERE id='bad'").fetchone() is None


def test_json_null_integer_datetime_values_preserved(client):
    admin=make_user('pg-admin',role='admin');partner=make_partner()
    with get_db() as conn:
        conn.execute('UPDATE partners SET ai_profile=?,intro=NULL WHERE id=?',('中文 Agent 123 "quotes" ? %',partner['id']))
        row=conn.execute('SELECT ai_profile,intro,created_at FROM partners WHERE id=?',(partner['id'],)).fetchone()
        assert row['ai_profile']=='中文 Agent 123 "quotes" ? %' and row['intro'] is None
        assert isinstance(row['created_at'],str)
    assert client.get('/partners',headers=auth_headers(admin)).status_code==200


def test_confirmed_version_survives_revise_failure_and_stale_edit(prepared):
    accepted,run=start(prepared);v1=complete(prepared,accepted,run);pid=accepted['plan_id'];user=prepared[0]
    life.confirm(pid,v1,user)
    from backend.app.development_types import Revise
    body=Revise(submission_id='pg-revise',based_on_version_id=v1,instruction='更多实验')
    second=life.revise(pid,body,user);run2=life.claim(second['run_id']);v2=complete(prepared,second,run2)
    assert (plan(pid)['current_version_id'],plan(pid)['confirmed_version_id'])==(v2,v1)
    with pytest.raises(HTTPException):life.revise(pid,body.model_copy(update={'submission_id':'stale'}),user)
    third=life.revise(pid,body.model_copy(update={'submission_id':'fail','based_on_version_id':v2}),user)
    failed=life.claim(third['run_id']);life.finish_failure(third['run_id'],failed['execution_token'],'model')
    assert (plan(pid)['current_version_id'],plan(pid)['confirmed_version_id'])==(v2,v1)
    with pytest.raises(IntegrityError):
        with get_db() as conn:conn.execute('UPDATE development_versions SET payload_json=? WHERE id=?',('{}',v1))


def test_same_submission_and_concurrent_revise_serialized(prepared):
    from backend.app.development_types import Submit,Revise
    payload=Submit(submission_id='pg-idempotent',request=prepared[3])
    with ThreadPoolExecutor(max_workers=3) as pool:accepted=list(pool.map(lambda _:life.create(payload,prepared[0]),range(3)))
    assert len({a['plan_id'] for a in accepted})==1
    first=accepted[0];run=life.claim(first['run_id']);version=complete(prepared,first,run)
    def revise(i):
        try:return life.revise(first['plan_id'],Revise(submission_id='parallel-'+str(i),based_on_version_id=version,instruction='调整实验'),prepared[0])
        except HTTPException as exc:return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:out=list(pool.map(revise,range(2)))
    assert sum(isinstance(x,dict) for x in out)==1 and 409 in out


@pytest.mark.parametrize('table,event', [('development_versions','INSERT'),('development_version_items','INSERT'),('development_diagnoses','INSERT'),('development_plans','UPDATE')])
def test_postgres_fault_rolls_back_entire_version(prepared,table,event):
    accepted,run=start(prepared);data=result(prepared);data['stages'][0]['items']=[{'synthetic':'fault-item'}]
    engine=engine_for(os.environ['DATABASE_URL'])
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE FUNCTION synthetic_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'synthetic failure' USING ERRCODE='23514'; END $$")
        conn.exec_driver_sql(f'CREATE TRIGGER synthetic_fault BEFORE {event} ON {table} FOR EACH ROW EXECUTE FUNCTION synthetic_failure()')
    with pytest.raises(IntegrityError):life.complete(accepted['run_id'],run['execution_token'],data,[],lambda *_:None)
    with get_db() as conn:
        for name in ['development_versions','development_version_items','development_diagnoses']:assert conn.execute('SELECT count(*) FROM '+name).fetchone()[0]==0
    assert plan(accepted['plan_id'])['current_version_id'] is None


def test_migration_success_and_immutable_source():
    before=sha(DATABASE_PATH)
    with empty_postgres_schema() as target:
        result=import_snapshot(DATABASE_PATH,target)
        assert result['table_count']==32 and result['row_value_reconciliation']=='PASS'
        with engine_for(target).connect() as conn:assert inspect(conn).get_foreign_keys('cases')
        with pytest.raises(RuntimeError,match='empty'):import_snapshot(DATABASE_PATH,target)
    assert sha(DATABASE_PATH)==before


@pytest.mark.parametrize('fail_after',['partners','case_share_versions','development_runs','users'])
def test_migration_failure_rolls_back_schema_and_rows(fail_after):
    def fault(name):
        if name==fail_after:raise RuntimeError('synthetic migration failure')
    with empty_postgres_schema() as target:
        with pytest.raises(RuntimeError,match='synthetic'):import_snapshot(DATABASE_PATH,target,fault=fault)
        with engine_for(target).connect() as conn:assert inspect(conn).get_table_names()==[]


def test_bad_foreign_key_source_is_rejected(tmp_path):
    bad=tmp_path/'orphan.db'
    with sqlite3.connect(DATABASE_PATH) as src,sqlite3.connect(bad) as dst:src.backup(dst)
    with sqlite3.connect(bad) as conn:conn.execute("INSERT INTO cases VALUES ('bad','missing','Synthetic',NULL,'now')")
    with pytest.raises(RuntimeError,match='foreign-key'):source_inventory(bad)


def test_native_postgres_identity_in_disposable_transaction():
    with empty_postgres_schema() as url:
        engine=engine_for(url)
        with engine.begin() as conn:
            conn.exec_driver_sql('CREATE TABLE synthetic_sequence (id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY)')
            first=conn.exec_driver_sql('INSERT INTO synthetic_sequence DEFAULT VALUES RETURNING id').scalar()
            second=conn.exec_driver_sql('INSERT INTO synthetic_sequence DEFAULT VALUES RETURNING id').scalar()
            assert (first,second)==(1,2)


def test_explicit_read_transaction_keeps_consistent_snapshot(client):
    partner = make_partner()
    with get_db() as reader:
        reader.execute('BEGIN')
        before = reader.execute('SELECT intro FROM partners WHERE id=?', (partner['id'],)).fetchone()[0]
        with get_db() as writer:
            writer.execute('UPDATE partners SET intro=? WHERE id=?', ('synthetic concurrent change', partner['id']))
        assert reader.execute('SELECT intro FROM partners WHERE id=?', (partner['id'],)).fetchone()[0] == before
    with get_db() as fresh:
        assert fresh.execute('SELECT intro FROM partners WHERE id=?', (partner['id'],)).fetchone()[0] == 'synthetic concurrent change'
