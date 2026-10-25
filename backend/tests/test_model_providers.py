"""Provider split, migration and shared connection pinning on isolated PostgreSQL."""
import json
import pytest
from backend.app.database import get_db
from backend.app import model_resolver,agent_settings
from backend.app.routers import model_config
from backend.app.model_provider_schema import migrate,LEGACY_COLUMNS
from .conftest import make_user,auth_headers
from .support.models import create_model

def legacy_schema(conn):
    # Reconstruct the exact legacy columns only inside this test's random schema.
    for column in LEGACY_COLUMNS:conn.execute(f'ALTER TABLE model_configs ADD COLUMN {column} TEXT')
    conn.execute("""UPDATE model_configs m SET provider=p.name,base_url=p.base_url,api_key=p.api_key,
        api_key_source=p.api_key_source,api_key_env_name=p.api_key_env_name FROM model_providers p WHERE p.id=m.provider_id""")
    conn.execute('ALTER TABLE model_configs DROP CONSTRAINT fk_model_configs_provider')
    conn.execute('ALTER TABLE model_configs DROP COLUMN provider_id')
    conn.execute('DROP TABLE model_providers')
    conn.execute("UPDATE app_metadata SET value='21' WHERE key='schema_version'")

def test_migration_groups_only_exact_connection_identity_and_preserves_models(client,monkeypatch):
    monkeypatch.setenv('SYNTHETIC_SHARED','synthetic-env')
    with get_db() as conn:
        legacy_schema(conn)
        original=dict(conn.execute('SELECT * FROM model_configs').fetchone())
        conn.execute('DELETE FROM model_configs')
        rows=[]
        for i,changes in enumerate([
            {},{'model_name':'another','temperature':0,'top_p':0,'max_tokens':90000},
            {'provider':'Different vendor'}, {'base_url':'https://other.invalid/v1'},
            {'api_key':'synthetic-stored'}, {'api_key_source':'db'},
            {'api_key_env_name':'ANOTHER_ENV'}, {'api_key_env_name':'SYNTHETIC_SHARED'},
            {'base_url':None}, {'provider':None},
        ]):
            row={**original,'id':'preserved-'+str(i),**changes};rows.append(row)
            conn.execute('INSERT INTO model_configs ('+','.join(row)+') VALUES ('+','.join('?' for _ in row)+')',list(row.values()))
        conn.execute("UPDATE model_usage_configs SET model_config_id='preserved-0'")
        agent_settings.set_selectable(conn,'preserved-1',True)
        settings=agent_settings.read(conn)
        for agent in settings['agents'].values():agent['modelConfigId']='preserved-0'
        settings['processing']['modelConfigId']='preserved-0'
        conn.execute('UPDATE app_metadata SET value=? WHERE key=?',(json.dumps(settings),agent_settings.KEY))
        metadata=[tuple(row) for row in conn.execute("SELECT key,value FROM app_metadata WHERE key!='schema_version' ORDER BY key")]
        usages=[tuple(row) for row in conn.execute('SELECT * FROM model_usage_configs ORDER BY scene_key')]
        rows=[dict(row) for row in conn.execute('SELECT * FROM model_configs ORDER BY id')]
        stamps={row['id']:model_resolver.configuration_stamp(row) for row in rows}
        legacy_agent={**rows[0],'_agent_execution':agent_settings.execution(conn,'partner_match')}
        legacy_stamp=model_resolver.configuration_stamp(legacy_agent)
        result=migrate(conn)
        assert result=={'schema_version':'22','models':10,'providers':9}
        assert 'synthetic-stored' not in json.dumps(result)
        assert [tuple(row) for row in conn.execute("SELECT key,value FROM app_metadata WHERE key!='schema_version' ORDER BY key")]==metadata
        assert [tuple(row) for row in conn.execute('SELECT * FROM model_usage_configs ORDER BY scene_key')]==usages
        current=[dict(row) for row in conn.execute(model_resolver.MODEL_SELECT+' ORDER BY m.id')]
        for row in current:
            old=next(old for old in rows if old['id']==row['id'])
            for key in old:
                if key not in LEGACY_COLUMNS:assert row[key]==old[key]
            assert model_resolver.configuration_stamp(row)==stamps[row['id']]
        assert model_resolver.configuration_stamp(model_resolver.resolve_model_record('partner_match',connection=conn))==legacy_stamp
        assert model_resolver.configuration_stamp(model_resolver.pinned_configuration(legacy_stamp,conn))==legacy_stamp
        assert current[0]['provider_id']==current[1]['provider_id']
        assert len({row['provider_id'] for row in current})==9
        columns={row[0] for row in conn.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='model_configs'")}
        assert 'provider_id' in columns and not columns.intersection(LEGACY_COLUMNS)

def test_provider_migration_is_transactional_and_never_runs_at_startup(client):
    with get_db() as conn:legacy_schema(conn)
    with pytest.raises(RuntimeError,match='synthetic abort'):
        with get_db() as conn:
            migrate(conn)
            raise RuntimeError('synthetic abort')
    with get_db() as conn:
        assert conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]=='21'
        assert conn.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema=current_schema() AND table_name='model_providers'").fetchone()[0]==0
    from backend.app.database import initialize_storage
    with pytest.raises(RuntimeError,match='explicit migration'):initialize_storage()

def test_provider_crud_auth_safe_output_and_nonempty_delete(client,monkeypatch):
    admin=auth_headers(make_user('provider-admin',role='admin'));user=auth_headers(make_user('provider-user'))
    path='/admin/model-providers'
    for method in ('get','post','put','delete'):
        target=path+('/missing' if method in ('put','delete') else '')
        args={'json':{'name':'synthetic','baseUrl':'https://model.invalid/v1'}} if method in ('post','put') else {}
        assert getattr(client,method)(target,**args).status_code==401
        assert getattr(client,method)(target,headers=user,**args).status_code==403
    calls=[]
    monkeypatch.setattr(model_config.development_model,'completion',lambda *a,**k:calls.append(a) or '{"ok":true}')
    response=client.post(path,headers=admin,json={'name':'合成提供商','baseUrl':'https://model.invalid/v1','apiKey':'synthetic-provider-private'})
    assert response.status_code==201
    p=response.json();assert p['apiKeyConfigured'] and p['apiKeySource']=='db'
    assert p['protocol']=='openai_chat_completions' and p['modelCount']==0
    assert 'synthetic-provider-private' not in response.text and 'apiKey' not in p
    assert 'apiKeyEnvName' not in p
    m=client.post('/admin/model-configs',headers=admin,json={'providerId':p['id'],'name':'合成模型','modelName':'synthetic-id','userSelectable':True})
    assert m.status_code==201 and m.json()['providerId']==p['id']
    assert not {'apiKey','apiKeyConfigured','baseUrl'}.intersection(m.json())
    assert client.delete(path+'/'+p['id'],headers=admin).status_code==409
    assert client.put(path+'/'+p['id'],headers=admin,json={'apiKey':''}).json()['apiKeyConfigured']
    assert calls==[]  # Saving a provider or model cannot perform inference.
    test=client.post('/admin/model-configs/'+m.json()['id']+'/test',headers=admin)
    assert test.json()['success'] and len(calls)==1
    config=calls[0][0];assert config['id']==m.json()['id'] and config['base_url']=='https://model.invalid/v1'
    assert client.put('/admin/model-configs/'+m.json()['id'],headers=admin,json={'baseUrl':'https://override.invalid'}).status_code==422
    assert client.post(path,headers=admin,json={'name':'bad','baseUrl':'https://model.invalid','protocol':'unsupported'}).status_code==422
    assert client.delete('/admin/model-configs/'+m.json()['id'],headers=admin).status_code==204
    assert client.delete(path+'/'+p['id'],headers=admin).status_code==204

@pytest.mark.parametrize('mutation',[{'baseUrl':'https://model.invalid/another/v1'},{'apiKey':'synthetic-new-key'}])
def test_shared_provider_change_invalidates_all_pinned_models_without_switch(client,mutation):
    p=model_config.create_provider(model_config.ProviderCreate(name='shared',baseUrl='https://model.invalid/v1',apiKey='synthetic-original'))
    first=create_model(name='first',modelName='first',providerId=p.id)
    second=create_model(name='second',modelName='second',providerId=p.id)
    with get_db() as conn:
        configs=[dict(model_resolver.model_record(conn,m.id)) for m in (first,second)]
    stamps=[model_resolver.configuration_stamp(config) for config in configs]
    model_config.update_provider(p.id,model_config.ProviderUpdate(**mutation))
    for config,stamp in zip(configs,stamps):
        with pytest.raises(model_resolver.ModelConfigurationError,match='变化'):model_resolver.pinned_configuration(stamp)
        with pytest.raises(model_resolver.ModelConfigurationError,match='变化'):model_resolver.validate_model_retry(config)
    with get_db() as conn:
        assert model_resolver.model_record(conn,first.id)['provider_id']==p.id
        assert model_resolver.model_record(conn,second.id)['provider_id']==p.id

def test_provider_name_edit_preserves_effective_pin_and_environment_source(client,monkeypatch):
    monkeypatch.setenv('SYNTHETIC_PROVIDER_KEY','synthetic-env-key')
    with get_db() as conn:
        row=conn.execute('SELECT * FROM model_providers').fetchone()
        conn.execute("UPDATE model_providers SET api_key=NULL,api_key_source='env',api_key_env_name='SYNTHETIC_PROVIDER_KEY' WHERE id=?",(row['id'],))
        m=conn.execute('SELECT id FROM model_configs').fetchone()[0]
        config=dict(model_resolver.model_record(conn,m))
    stamp=model_resolver.configuration_stamp(config)
    model_config.update_provider(row['id'],model_config.ProviderUpdate(name='renamed',apiKey=''))
    assert model_resolver.configuration_stamp(model_resolver.pinned_configuration(stamp))==stamp
    with get_db() as conn:
        provider=conn.execute('SELECT * FROM model_providers WHERE id=?',(row['id'],)).fetchone()
        assert provider['api_key'] is None and provider['api_key_source']=='env'
        assert provider['api_key_env_name']=='SYNTHETIC_PROVIDER_KEY'
