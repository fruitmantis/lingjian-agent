"""Explicit total capacity, safe legacy data, and matching output budget. Synthetic PG only."""
import hashlib
import json
import os
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import inspect

from backend.app import ai_client, agent_settings, development_model, model_resolver, partner_match_context as context
from backend.app.database import get_db, initialize_storage
from backend.app.model_context_schema import migrate
from backend.app.postgres_storage import initialize_empty_schema, verify_schema, connect
from backend.app.routers import model_config, match
from backend.app.task_failures import MatchInputBudgetError, failure, public_failures
from .conftest import make_user, auth_headers, make_task
from .postgres_support import empty_postgres_schema, snapshot


def schema22(conn):
    conn.execute('ALTER TABLE model_configs DROP COLUMN context_window_tokens')
    conn.execute("UPDATE app_metadata SET value='22' WHERE key='schema_version'")


def selected_record(conn):
    target = agent_settings.read(conn)['agents']['partner_match']['modelConfigId']
    return dict(model_resolver.model_record(conn, target))


def test_new_initialization_leaves_capacity_unknown_without_guessing():
    with empty_postgres_schema() as url:
        initialize_empty_schema(url)
        verify_schema(url)
        with connect(url, readonly=True) as conn:
            assert conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] == '23'
            rows = conn.execute('SELECT context_window_tokens,max_tokens FROM model_configs').fetchall()
            assert rows and all(r['context_window_tokens'] is None and r['max_tokens'] == 131072 for r in rows)
            column = next(c for c in inspect(conn.connection).get_columns('model_configs') if c['name'] == 'context_window_tokens')
            assert column['nullable'] and column['default'] is None


def test_explicit_migration_preserves_every_old_row_binding_and_stamp(client):
    user = make_user('capacity-migration-owner')
    make_task(user, 'synthetic retained history')
    with get_db() as conn:
        schema22(conn)
        old = selected_record(conn)
        stamp = model_resolver.configuration_stamp(old)
        before = snapshot(conn)
        assert migrate(conn) == {'schema_version': '23', 'models': before['model_configs']['count']}
        after = snapshot(conn, {'model_configs': ['context_window_tokens']})
        assert {k:v for k,v in after.items() if k != 'app_metadata'} == {k:v for k,v in before.items() if k != 'app_metadata'}
        assert conn.execute('SELECT count(*) FROM model_configs WHERE context_window_tokens IS NOT NULL').fetchone()[0] == 0
        current = selected_record(conn)
        assert model_resolver.configuration_stamp(current) == stamp
        assert model_resolver.pinned_configuration(stamp, conn)['id'] == old['id']
        assert {k:current[k] for k in old} == old
        col = next(c for c in inspect(conn.connection).get_columns('model_configs') if c['name']=='context_window_tokens')
        assert col['nullable'] and col['default'] is None
    verify_schema(os.environ['DATABASE_URL'])


def test_migration_rolls_back_column_version_and_data_on_failure(client):
    with get_db() as conn:
        schema22(conn)
        before = snapshot(conn)
    with pytest.raises(RuntimeError, match='synthetic abort'):
        with get_db() as conn:
            migrate(conn)
            raise RuntimeError('synthetic abort')
    with get_db() as conn:
        assert snapshot(conn) == before
        assert 'context_window_tokens' not in {c['name'] for c in inspect(conn.connection).get_columns('model_configs')}


@pytest.mark.parametrize('version', ['21', '23'])
def test_migration_refuses_wrong_version_without_writes(client, version):
    with get_db() as conn:
        conn.execute("UPDATE app_metadata SET value=? WHERE key='schema_version'", (version,))
        before = snapshot(conn)
    with pytest.raises(RuntimeError, match='requires schema 22'):
        with get_db() as conn:
            migrate(conn)
    with get_db() as conn:
        assert snapshot(conn) == before


@pytest.mark.parametrize('current_stamp', [False, True])
def test_startup_refuses_old_or_incomplete_schema_without_migration(client, current_stamp):
    with get_db() as conn:
        schema22(conn)
        if current_stamp:
            conn.execute("UPDATE app_metadata SET value='23' WHERE key='schema_version'")
        before = snapshot(conn)
    expected = 'explicit schema-23 migration' if current_stamp else 'schema version is not 23; refusing automatic changes'
    with pytest.raises(RuntimeError, match=expected):
        initialize_storage()
    with get_db() as conn:
        assert snapshot(conn) == before


def admin_payload(conn):
    record = selected_record(conn)
    return {'name':'synthetic capacity model','modelName':'synthetic-unknown-id','providerId':record['provider_id'],'maxTokens':131072}


def test_capacity_crud_is_independent_and_omission_preserves_known_or_null(client, monkeypatch):
    admin = auth_headers(make_user('capacity-admin', role='admin'))
    user = auth_headers(make_user('capacity-user'))
    with get_db() as conn:
        body = admin_payload(conn)
        target = selected_record(conn)['id']
        conn.execute('UPDATE model_configs SET context_window_tokens=NULL WHERE id=?', (target,))
    calls=[]
    monkeypatch.setattr(development_model, 'completion', lambda *a,**k: calls.append(a) or '{"ok":true}')
    for headers, code in [({},401),(user,403)]:
        assert client.post('/admin/model-configs', headers=headers, json={**body,'contextWindowTokens':262144}).status_code == code
    listing=client.get('/admin/model-configs', headers=admin)
    assert listing.status_code==200 and listing.headers['X-Model-Context-Window']=='tokens'
    assert next(r for r in listing.json() if r['id']==target)['contextWindowTokens'] is None
    ordinary=client.put('/admin/model-configs/'+target,headers=admin,json={'name':'renamed legacy'})
    assert ordinary.status_code==200 and ordinary.json()['contextWindowTokens'] is None
    created=client.post('/admin/model-configs',headers=admin,json={**body,'contextWindowTokens':262144})
    assert created.status_code==201
    data=created.json();assert data['contextWindowTokens']==262144 and data['maxTokens']==131072
    target=data['id']
    updated=client.put('/admin/model-configs/'+target,headers=admin,json={'maxTokens':384000})
    assert updated.json()['maxTokens']==384000 and updated.json()['contextWindowTokens']==262144
    updated=client.put('/admin/model-configs/'+target,headers=admin,json={'contextWindowTokens':1048576})
    assert updated.json()['contextWindowTokens']==1048576 and updated.json()['maxTokens']==384000
    assert calls==[]
    assert client.delete('/admin/model-configs/'+target, headers=admin).status_code==204


@pytest.mark.parametrize('method', ['post','put'])
@pytest.mark.parametrize('value', [None,0,-1,1.5,True,False,'131072',1.0,2147483648])
def test_capacity_requires_a_real_positive_integer_without_mutating_rows(client, method, value):
    headers=auth_headers(make_user('capacity-numeric-admin',role='admin'))
    with get_db() as conn:
        body=admin_payload(conn);target=selected_record(conn)['id'];before=snapshot(conn)
    path='/admin/model-configs'+('/'+target if method=='put' else '')
    response=getattr(client,method)(path,headers=headers,json={**body,'contextWindowTokens':value})
    assert response.status_code==422
    assert any(entry['loc'][-1]=='contextWindowTokens' for entry in response.json()['detail'])
    if value == 2147483648:
        assert any(entry['loc'][-1]=='contextWindowTokens' and entry['type']=='less_than_equal' and entry['ctx']['le']==2147483647 for entry in response.json()['detail'])
    with get_db() as conn:
        assert snapshot(conn)==before


@pytest.mark.parametrize('method', ['post','put'])
@pytest.mark.parametrize('capacity', [1,2147483647])
def test_capacity_storage_boundaries_are_saved_exactly_without_changing_output_limit(client,method,capacity):
    headers=auth_headers(make_user('capacity-boundary-admin',role='admin'))
    with get_db() as conn:
        body=admin_payload(conn);target=selected_record(conn)['id']
    path='/admin/model-configs'+('/'+target if method=='put' else '')
    response=getattr(client,method)(path,headers=headers,json={**body,'contextWindowTokens':capacity})
    assert response.status_code==(201 if method=='post' else 200)
    saved=response.json()
    assert saved['contextWindowTokens']==capacity and saved['maxTokens']==131072
    with get_db() as conn:
        row=conn.execute('SELECT context_window_tokens,max_tokens FROM model_configs WHERE id=?',(saved['id'],)).fetchone()
        assert row['context_window_tokens']==capacity and row['max_tokens']==131072
    listed=client.get('/admin/model-configs',headers=headers)
    assert listed.status_code==200
    assert next(model for model in listed.json() if model['id']==saved['id'])['contextWindowTokens']==capacity


def test_new_model_requires_capacity_but_legacy_connection_test_does_not(client, monkeypatch):
    headers=auth_headers(make_user('capacity-required-admin',role='admin'))
    with get_db() as conn:
        body=admin_payload(conn);target=selected_record(conn)['id']
        conn.execute('UPDATE model_configs SET context_window_tokens=NULL WHERE id=?',(target,))
        conn.execute("UPDATE model_providers SET api_key='synthetic-only',api_key_source='db'")
    missing=client.post('/admin/model-configs',headers=headers,json=body)
    assert missing.status_code==422 and missing.json()['detail'][0]['loc'][-1]=='contextWindowTokens'
    calls=[]
    monkeypatch.setattr(development_model,'completion',lambda *a,**k:calls.append(a) or '{"ok":true}')
    assert client.post('/admin/model-configs/'+target+'/test',headers=headers).json()['success']
    assert len(calls)==1


@pytest.mark.parametrize('endpoint,model', [('https://api.deepseek.com','deepseek-flash'),('https://maas.invalid/v1','deepseek-flash'),('http://127.0.0.1:18888/v1','arbitrary-model')])
@pytest.mark.parametrize('capacity,expected', [(131072,110855),(262144,131072),(1048576,131072)])
def test_budget_uses_explicit_capacity_instead_of_endpoint_or_model_name(monkeypatch,endpoint,model,capacity,expected):
    record={'id':'synthetic','api_key':'synthetic','base_url':endpoint,'model_name':model,'max_tokens':131072,'context_window_tokens':capacity}
    monkeypatch.setattr(context,'input_metrics',lambda *args:(17000,20217))
    selected,chars,tokens=context.checked_config(record,[],{},25000)
    assert selected['_match_output_tokens']==expected and (chars,tokens)==(17000,20217)
    assert '_match_output_tokens' not in record
    assert model_resolver.configuration_stamp(selected)==model_resolver.configuration_stamp(record)
    body,_=ai_client.prepared_completion(selected,[],{})
    wire=json.loads(body)
    assert wire['max_tokens']==expected
    assert not {'context_window_tokens','contextWindowTokens'}.intersection(wire)


@pytest.mark.parametrize('capacity', [0,None])
def test_missing_capacity_fails_before_input_budget_without_inferring_default(monkeypatch,capacity):
    record={'api_key':'synthetic','base_url':'https://api.deepseek.com','model_name':'deepseek-flash','max_tokens':131072,'context_window_tokens':capacity}
    monkeypatch.setattr(context,'input_metrics',lambda *args:pytest.fail('Capacity must be known before calculating matching budget'))
    with pytest.raises(model_resolver.ModelContextCapacityError,match='总上下文容量') as error:
        context.checked_config(record,[],{},25000)
    reason=failure('understanding',error.value)
    assert reason['code']=='context_capacity' and reason['modelRelated']
    assert reason['action']=='返回并切换模型' and '总上下文容量' in reason['message']
    assert public_failures('understanding',json.dumps([reason]))==[reason]


def test_character_limit_and_nonpositive_output_still_fail_before_transport(monkeypatch):
    record={'api_key':'synthetic','base_url':'https://model.invalid','model_name':'synthetic','max_tokens':131072,'context_window_tokens':1048576}
    with pytest.raises(MatchInputBudgetError,match='字符'):
        context.checked_config(record,[{'role':'user','content':'甲'*25000}],{},25000)
    monkeypatch.setattr(context,'input_metrics',lambda *args:(100,20217))
    for changes in [{'context_window_tokens':20217},{'context_window_tokens':10000},{'max_tokens':0},{'max_tokens':-1}]:
        with pytest.raises(MatchInputBudgetError):
            context.checked_config({**record,**changes},[],{},25000)


def test_null_capacity_preserves_historical_digest_and_actual_value_invalidates_pins(client):
    with get_db() as conn:
        record=selected_record(conn);record['context_window_tokens']=None
        conn.execute('UPDATE model_configs SET context_window_tokens=NULL WHERE id=?',(record['id'],))
        stamp=model_resolver.configuration_stamp(record)
        old_fields=vars(model_resolver.model_config_from_record(record)).copy()
        old_fields.pop('context_window_tokens');old_fields.pop('thinking')
        assert stamp['fingerprint']==hashlib.sha256(json.dumps(old_fields,sort_keys=True).encode()).hexdigest()
        absent=dict(record);absent.pop('context_window_tokens')
        assert model_resolver.configuration_stamp(absent)==stamp
        assert model_resolver.pinned_configuration(stamp,conn)['id']==record['id']
        conn.execute('UPDATE model_configs SET context_window_tokens=262144 WHERE id=?',(record['id'],))
    with pytest.raises(model_resolver.ModelConfigurationError,match='变化'):
        model_resolver.pinned_configuration(stamp)
    with pytest.raises(model_resolver.ModelConfigurationError,match='变化'):
        model_resolver.validate_model_retry(record)


def test_missing_capacity_preserves_accepted_task_raw_text_and_original_switch_action(client,monkeypatch):
    user=make_user('capacity-failed-task-owner');jobs=[];calls=[]
    with get_db() as conn:
        selected=selected_record(conn)['id']
        conn.execute('UPDATE model_configs SET context_window_tokens=NULL WHERE id=?',(selected,))
    monkeypatch.setattr(match.executor,'submit',lambda fn,*args:jobs.append((fn,args)))
    monkeypatch.setattr(development_model,'completion',lambda *args:calls.append(args) or pytest.fail('No model call when capacity missing'))
    text='  合成数据库迁移需求，保留原文。  '
    task=match.create_task(match.TaskCreateRequest(requestId=uuid.uuid4(),requirement=text,modelConfigId=selected),user)
    assert len(jobs)==1
    jobs[0][0](*jobs[0][1])
    detail=match.get_match_record(task.recordId,user)
    assert detail.taskStatus=='failed' and detail.requirement==text and detail.modelSelection['id']==selected
    assert detail.failureDetails[0]['code']=='context_capacity'
    assert detail.failureDetails[0]['modelRelated'] and detail.failureDetails[0]['action']=='返回并切换模型'
    assert '总上下文容量' in detail.failureDetails[0]['message'] and calls==[]


def test_explicit_cli_backs_up_and_verifies_entire_dump_before_migration(client,tmp_path):
    from sqlalchemy.engine import make_url
    from pathlib import Path
    url=make_url(os.environ['DATABASE_URL'])
    assert url.database in ('banfei_agent_test','banfei_validation')
    with get_db() as conn:
        schema22(conn);before=snapshot(conn)
    backup=tmp_path/'private-capacity-backup'
    result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[2]/'scripts/migrate_model_context.py'),
        '--database-name',url.database,'--backup-dir',str(backup)],capture_output=True,text=True,env=dict(os.environ))
    assert result.returncode==0, result.stderr
    assert json.loads(result.stdout)['business_row_counts_unchanged']
    assert (backup/'before.pgdump').stat().st_size>0 and (backup/'before.pgdump').stat().st_mode & 0o077 == 0
    assert backup.stat().st_mode & 0o077 == 0
    with get_db() as conn:
        after=snapshot(conn,{'model_configs':['context_window_tokens']})
        assert {k:v for k,v in after.items() if k!='app_metadata'}=={k:v for k,v in before.items() if k!='app_metadata'}
        assert conn.execute('SELECT count(*) FROM model_configs WHERE context_window_tokens IS NOT NULL').fetchone()[0]==0
    verify_schema(os.environ['DATABASE_URL'])


@pytest.mark.parametrize('failed_command',['pg_dump','pg_restore_list','pg_restore_read'])
def test_cli_never_migrates_when_backup_or_complete_read_fails(client,tmp_path,monkeypatch,failed_command):
    from scripts import migrate_model_context as cli
    from sqlalchemy.engine import make_url
    with get_db() as conn:
        schema22(conn);before=snapshot(conn)
    def run(args,**kwargs):
        command='pg_dump' if args[0]=='pg_dump' else 'pg_restore_list' if '--list' in args else 'pg_restore_read'
        if command==failed_command:
            raise subprocess.CalledProcessError(1,args)
        if args[0]=='pg_dump':kwargs['stdout'].write(b'synthetic backup')
        return subprocess.CompletedProcess(args,0)
    monkeypatch.setattr(cli.subprocess,'run',run)
    monkeypatch.setattr(cli,'migrate',lambda *args:pytest.fail('No migration without verified full backup'))
    monkeypatch.setattr(sys,'argv',['migrate_model_context','--database-name',make_url(os.environ['DATABASE_URL']).database,'--backup-dir',str(tmp_path/'failed-backup')])
    with pytest.raises(subprocess.CalledProcessError):cli.main()
    with get_db() as conn:assert snapshot(conn)==before
