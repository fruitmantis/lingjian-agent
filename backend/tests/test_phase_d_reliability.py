"""Phase D reliability evidence; every fixture uses pytest's private database."""
import json
from datetime import datetime, timedelta, timezone
import pytest
from fastapi import HTTPException
from backend.app import development_lifecycle as life
from backend.app.database import get_db
from backend.tests.test_development_lifecycle import prepared, start, complete, plan


def test_expired_run_cannot_save_without_a_read_or_restart(prepared):
    accepted, run = start(prepared)
    with get_db() as conn:
        conn.execute('UPDATE development_runs SET started_at=? WHERE id=?',
                     ((datetime.now(timezone.utc)-timedelta(seconds=601)).isoformat(), accepted['run_id']))
    with pytest.raises(HTTPException) as error:
        complete(prepared, accepted, run)
    assert error.value.status_code == 409
    assert plan(accepted['plan_id'])['current_version_id'] is None
    with get_db() as conn:
        assert conn.execute('SELECT count(*) FROM development_versions').fetchone()[0] == 0

import copy
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from backend.app import development_engine as engine, development_model as model, development_views as views
from backend.app.development_types import Submit, Revise
from backend.tests.test_development_engine import scenario, execute, CANARY
from backend.tests.test_development_api import stages
from backend.tests.conftest import auth_headers


def test_default_deadlines_and_bounded_test_overrides(monkeypatch):
    from backend.app.development_deadlines import model_timeout, run_timeout
    for key in ['DEVELOPMENT_MODEL_TIMEOUT_SECONDS','DEVELOPMENT_RUN_TIMEOUT_SECONDS']:
        monkeypatch.delenv(key, raising=False)
    assert (model_timeout(), run_timeout()) == (180, 600)
    for value in ['-1', 'nan', 'inf', 'invalid', '9999']:
        monkeypatch.setenv('DEVELOPMENT_MODEL_TIMEOUT_SECONDS', value)
        monkeypatch.setenv('DEVELOPMENT_RUN_TIMEOUT_SECONDS', value)
        assert (model_timeout(), run_timeout()) == (180, 600)
    monkeypatch.setenv('DEVELOPMENT_RUN_TIMEOUT_SECONDS', '.2')
    assert run_timeout() == .2


def test_run_watchdog_without_polling_preserves_confirmed_and_retries(scenario, monkeypatch):
    accepted, _, payload = execute(scenario)
    user, _, _, request = scenario[0]; pid = accepted['plan_id']
    v1 = plan(pid)['current_version_id']; views.confirm(pid, v1, user)
    held = threading.Event(); entered = threading.Event(); original = scenario[2]
    def slow(*args):
        entered.set(); assert held.wait(5)
        return original(*args)
    monkeypatch.setattr(model, 'completion', slow)
    monkeypatch.setenv('DEVELOPMENT_RUN_TIMEOUT_SECONDS', '.2')
    second = life.revise(pid, Revise(submission_id='watchdog-revise', based_on_version_id=v1, instruction='缩短周期', request=request), user)
    worker = threading.Thread(target=engine.execute, args=(second['run_id'],))
    worker.start()
    try:
        assert entered.wait(3)
        time.sleep(.5)  # no detail/list/recovery calls: the watchdog must act itself
        with get_db() as conn:
            row = conn.execute('SELECT status,error_stage FROM development_runs WHERE id=?',(second['run_id'],)).fetchone()
        assert tuple(row) == ('interrupted', 'run_timeout')
        assert (plan(pid)['current_version_id'], plan(pid)['confirmed_version_id']) == (v1,v1)
        assert plan(pid)['active_run_id'] is None
    finally:
        held.set(); worker.join(5)
    assert not worker.is_alive()
    assert (plan(pid)['current_version_id'], plan(pid)['confirmed_version_id']) == (v1,v1)
    monkeypatch.delenv('DEVELOPMENT_RUN_TIMEOUT_SECONDS')
    monkeypatch.setattr(model, 'completion', original)
    retry = life.revise(pid, Revise(submission_id='watchdog-retry', based_on_version_id=v1, instruction='重试', request=request), user)
    engine.execute(retry['run_id'])
    assert plan(pid)['current_version_id'] != v1 and plan(pid)['confirmed_version_id'] == v1
    with get_db() as conn:
        assert conn.execute('SELECT count(*) FROM development_versions WHERE plan_id=?',(pid,)).fetchone()[0] == 2


@pytest.mark.parametrize('fault', ['version','item','diagnosis','pointer'])
def test_fault_with_v2_current_and_v1_confirmed_preserves_all_rows(scenario, fault):
    accepted, _, payload = execute(scenario)
    user, _, _, request = scenario[0]; pid=accepted['plan_id']
    v1=plan(pid)['current_version_id']; views.confirm(pid,v1,user)
    second=life.revise(pid,Revise(submission_id='fault-v2-base',based_on_version_id=v1,instruction='调整',request=request),user)
    engine.execute(second['run_id']);v2=plan(pid)['current_version_id'];assert v2 != v1
    third=life.revise(pid,Revise(submission_id='fault-v3-attempt',based_on_version_id=v2,instruction='再次调整',request=request),user)
    tables=['development_versions','development_version_items','development_diagnoses']
    with get_db() as conn:
        before={t:[tuple(r) for r in conn.execute(f'SELECT * FROM {t} ORDER BY rowid')] for t in tables}
        action,table,when={
            'version':('INSERT','development_versions',''),
            'item':('INSERT','development_version_items',''),
            'diagnosis':('INSERT','development_diagnoses',''),
            'pointer':('UPDATE','development_plans','WHEN NEW.current_version_id IS NOT OLD.current_version_id'),
        }[fault]
        conn.execute(f"CREATE TRIGGER d_failure BEFORE {action} ON {table} {when} BEGIN SELECT RAISE(ABORT,'synthetic fault'); END")
    engine.execute(third['run_id'])
    assert (plan(pid)['current_version_id'],plan(pid)['confirmed_version_id'])==(v2,v1)
    assert views.detail(pid,user)['payload'] and views.transferable(pid,user)['text']
    with get_db() as conn:
        assert conn.execute('SELECT status FROM development_runs WHERE id=?',(third['run_id'],)).fetchone()[0]=='failed'
        assert {t:[tuple(r) for r in conn.execute(f'SELECT * FROM {t} ORDER BY rowid')] for t in tables}==before
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
        conn.execute('DROP TRIGGER d_failure')
    retry=life.revise(pid,Revise(submission_id='fault-retry-run',based_on_version_id=v2,instruction='重试',request=request),user)
    engine.execute(retry['run_id']);assert plan(pid)['confirmed_version_id']==v1
    with get_db() as conn:assert conn.execute('SELECT count(*) FROM development_versions WHERE plan_id=?',(pid,)).fetchone()[0]==3


def test_all_owner_mutations_and_canary_boundaries(scenario, client, caplog):
    accepted, _, payload=execute(scenario);pid=accepted['plan_id']
    user,other,admin,request=scenario[0];v1=plan(pid)['current_version_id'];views.confirm(pid,v1,user)
    assert CANARY in client.get('/enablement/context?partner_id=partner-1',headers=auth_headers(user)).text
    bodies={
        'revise':{'submission_id':'b-must-not-revise','based_on_version_id':v1,'instruction':'调整','request':request.model_dump()},
        'edit':{'based_on_version_id':v1,'stages':stages(payload)},
        'confirm':{'version_id':v1},'copy':{'version_id':v1},
    }
    for operation,body in bodies.items():
        response=client.post(f'/development/plans/{pid}/{operation}',headers=auth_headers(other),json=body)
        assert response.status_code==404,(operation,response.status_code)
        assert CANARY not in response.text
    assert client.get('/development/plans/'+pid,headers=auth_headers(admin)).status_code==200
    for actor in [user,admin]:
        response=client.get(f'/development/plans/{pid}/transferable',headers=auth_headers(actor))
        copied=client.post(f'/development/plans/{pid}/copy',headers=auth_headers(actor),json={'version_id':v1})
        assert response.status_code==200 and copied.status_code==200
        assert CANARY not in response.text+copied.text
    with get_db() as conn:
        audit=[dict(r) for r in conn.execute('SELECT * FROM development_audit_events')]
        audit += [dict(r) for r in conn.execute('SELECT * FROM user_audit_logs')]
        raw=conn.execute('SELECT payload_json FROM development_versions WHERE id=?',(v1,)).fetchone()[0]
    for boundary in [json.dumps(audit),raw,json.dumps(scenario[1]),caplog.text]:assert CANARY not in boundary
