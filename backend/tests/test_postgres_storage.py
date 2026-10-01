"""PostgreSQL-specific transaction, migration and runtime regression."""
from backend.tests.support.legacy_development import legacy_confirmed
import json
import os
import sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text,inspect
from sqlalchemy.exc import IntegrityError,DBAPIError
from fastapi import HTTPException
from backend.app.database import get_db,get_readonly_db,initialize_storage
from backend.app.postgres_storage import engine_for,bind_parameters
from backend.app import development_lifecycle as life
from backend.app.routers import partners
from .conftest import make_user,make_partner,auth_headers,make_task
from .test_development_lifecycle import prepared,start,complete,plan,result
from .postgres_support import empty_postgres_schema
from .postgres_support import snapshot
from .test_enablement_migration import assert_initialization_rollback_and_retry



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


def test_administrator_delete_and_history_protection(client):
    admin=make_user('pg-delete-admin',role='admin');user=make_user('pg-delete-user');p=make_partner()
    assert client.delete('/partners/'+p['id'],headers=auth_headers(user)).status_code==403
    task=make_task(user,'Synthetic matching history')
    response=client.delete('/partners/'+p['id'],headers=auth_headers(admin))
    assert response.status_code==409 and response.json()['detail']['counts']['matching_tasks']==1
    unused=make_partner('unused','Synthetic unused')
    assert client.delete('/partners/'+unused['id'],headers=auth_headers(admin)).status_code==204
    with get_db() as conn:assert conn.execute('SELECT id FROM match_records WHERE id=?',(task,)).fetchone()


def test_confirmed_version_survives_revise_failure_and_stale_edit(prepared):
    accepted,run=start(prepared);v1=complete(prepared,accepted,run);pid=accepted['plan_id'];user=prepared[0]
    legacy_confirmed(pid,v1,user)
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


def test_direct_initialization_has_foreign_keys_and_immutable_existing_data(client):
    with get_db() as conn: before=snapshot(conn)
    initialize_storage()
    with engine_for(os.environ['DATABASE_URL']).connect() as conn:
        assert inspect(conn).get_foreign_keys('cases')
        assert snapshot(conn)==before

@pytest.mark.parametrize('fail_after', [1, 7, 15, 30])
def test_initialization_failure_rolls_back_schema_and_rows(fail_after):
    assert_initialization_rollback_and_retry(fail_after)


def test_bad_foreign_key_is_rejected_in_pg(client):
    with pytest.raises(IntegrityError):
        with get_db() as conn:
            conn.execute("INSERT INTO cases (id,partner_id,title,created_at) VALUES ('bad','missing','synthetic','now')")
    with get_db() as conn: assert conn.execute("SELECT 1 FROM cases WHERE id='bad'").fetchone() is None


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
        reader.begin_read()
        before = reader.execute('SELECT intro FROM partners WHERE id=?', (partner['id'],)).fetchone()[0]
        with get_db() as writer:
            writer.execute('UPDATE partners SET intro=? WHERE id=?', ('synthetic concurrent change', partner['id']))
        assert reader.execute('SELECT intro FROM partners WHERE id=?', (partner['id'],)).fetchone()[0] == before
    with get_db() as fresh:
        assert fresh.execute('SELECT intro FROM partners WHERE id=?', (partner['id'],)).fetchone()[0] == 'synthetic concurrent change'


@pytest.mark.parametrize('missing_table', ['feedback_attachment', 'feedback_issue'])
def test_incomplete_schema_refuses_automatic_changes(client, missing_table):
    with get_db() as conn:
        if missing_table=='feedback_issue':conn.execute('DROP TABLE feedback_attachment')
        conn.execute('DROP TABLE '+missing_table)
        before=snapshot(conn)
    with pytest.raises(RuntimeError, match='incomplete'): initialize_storage()
    with get_db() as conn: assert snapshot(conn)==before


@pytest.mark.parametrize('value', ['', 'sqlite://', 'sqlite:////tmp/forbidden.db', 'mysql://user:secret@localhost/db', 'postgresql+asyncpg://localhost/db'])
def test_invalid_database_config_creates_no_file_or_sqlite_connection(monkeypatch,tmp_path,value):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('DATABASE_URL',value)
    monkeypatch.setattr(sqlite3,'connect',lambda *_a,**_k:pytest.fail('SQLite must never be called'))
    with pytest.raises((RuntimeError,ValueError)):
        with get_db():pass
    with pytest.raises((RuntimeError,ValueError)):initialize_storage()
    assert list(tmp_path.iterdir())==[]


def test_schema_cleanup_leaves_other_invocation_untouched():
    with empty_postgres_schema() as other:
        other_engine = engine_for(other)
        with other_engine.begin() as conn:
            conn.execute(text('CREATE TABLE ownership_probe (id integer PRIMARY KEY)'))
            conn.execute(text('INSERT INTO ownership_probe VALUES (7)'))
            other_name = conn.execute(text('SELECT current_schema()')).scalar()
        with empty_postgres_schema() as owned:
            with engine_for(owned).connect() as conn:
                owned_name = conn.execute(text('SELECT current_schema()')).scalar()
            assert owned_name != other_name and owned_name != 'public'
        with other_engine.connect() as conn:
            assert conn.execute(text('SELECT id FROM ownership_probe')).scalar() == 7
            assert conn.execute(text('SELECT 1 FROM pg_namespace WHERE nspname=:name'), {'name': owned_name}).scalar() is None


def test_connection_failure_does_not_fall_back(monkeypatch,tmp_path):
    import socket
    # Keep a local port bound without listening, so it cannot be another database.
    with socket.socket() as unavailable:
        unavailable.bind(('127.0.0.1',0))
        monkeypatch.setenv('DATABASE_URL',f'postgresql+psycopg://synthetic:synthetic@127.0.0.1:{unavailable.getsockname()[1]}/banfei_agent_test')
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sqlite3,'connect',lambda *_a,**_k:pytest.fail('SQLite must never be called'))
        with pytest.raises(DBAPIError):initialize_storage()
        assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('value', ['', 'sqlite://'])
def test_initializer_cli_refuses_invalid_configuration_without_creating_files(tmp_path,value):
    import subprocess, sys
    root=Path(__file__).resolve().parents[2]
    result=subprocess.run([sys.executable,str(root/'scripts/initialize_postgres.py')],
        cwd=tmp_path,env=dict(os.environ,DATABASE_URL=value),capture_output=True,text=True)
    assert result.returncode == 1
    assert ('DATABASE_URL' if not value else 'PostgreSQL') in result.stderr
    assert list(tmp_path.iterdir()) == []
