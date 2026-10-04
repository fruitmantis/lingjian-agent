"""Bounded fixed-agent configuration and lifecycle regressions on isolated PostgreSQL."""
import json
import uuid
from datetime import datetime,timezone,timedelta
import pytest
from fastapi import HTTPException
from backend.app import agent_settings as settings,model_resolver as resolver,development_model,development_lifecycle as life,development_engine as engine
from backend.app.ai_client import completion_payload
from backend.app.database import get_db,recover_stale_tasks
from backend.app.model_timeout_settings import get_settings
from backend.app.routers import model_config,match
from backend.app.development_types import Submit,DevelopmentRequest,Revise
from .conftest import make_user,auth_headers
from .test_development_lifecycle import prepared
from .support.development_mock import response as development_response
from .test_partner_match_stages import answer


def configure(agent_id,**changes):
    current=settings.read()['agents'][agent_id]
    return settings.save(agent_id,settings.AgentSettings.model_validate({**current,**changes}))


def another_model():
    return model_config.create_config(model_config.ModelConfigCreate(name='另一合成连接',baseUrl='https://api.deepseek.com',modelName='deepseek-flash',apiKey='synthetic-only')).id


def test_metadata_migration_atomic_idempotent_preserves_connections_and_unrelated_settings():
    with get_db() as conn:
        original=[dict(r) for r in conn.execute('SELECT * FROM model_configs')]
        conn.execute("INSERT INTO app_metadata(key,value) VALUES ('unrelated-setting','keep')")
        conn.execute("INSERT INTO model_usage_configs(scene_key,scene_name,updated_at) VALUES ('unrelated-scene','keep','2026')")
        conn.execute("UPDATE app_metadata SET value=? WHERE key='model_timeout_settings'",(json.dumps({'timeoutSeconds':77,'timeoutRetries':2}),))
    with pytest.raises(RuntimeError):
        with get_db() as conn:
            settings.migrate(conn)
            raise RuntimeError('synthetic rollback')
    with get_db() as conn:
        assert not conn.execute('SELECT value FROM app_metadata WHERE key=?',(settings.KEY,)).fetchone()
        first=settings.migrate(conn);second=settings.migrate(conn)
        assert first==second
        assert [dict(r) for r in conn.execute('SELECT * FROM model_configs')]==original
        assert [r[0] for r in conn.execute('SELECT scene_key FROM model_usage_configs')]==['unrelated-scene']
        assert conn.execute("SELECT value FROM app_metadata WHERE key='unrelated-setting'").fetchone()[0]=='keep'
        archived=json.loads(conn.execute('SELECT value FROM app_metadata WHERE key=?',(settings.LEGACY_KEY,)).fetchone()[0])
        assert len(archived['bindings'])==7 and archived['timeout']['timeoutSeconds']==77
        assert first['agents']['partner_match']['timeoutSeconds']==77
        assert first['agents']['partner_development']['timeoutRetries']==2
        assert first['processing']['modelConfigId']==original[0]['id']


def test_admin_config_persists_isolated_agents_and_public_metadata(client):
    admin=auth_headers(make_user('agent-admin',role='admin'));user=auth_headers(make_user('agent-user'))
    assert client.get('/admin/agents',headers=user).status_code==403
    assert client.get('/agents').status_code==401
    before=client.get('/admin/agents',headers=admin).json();second=another_model()
    body={**before['agents']['partner_match'],'name':'项目伙伴顾问','description':'合成简介','icon':'puzzle','thinking':False,'timeoutSeconds':41,'modelConfigId':second}
    assert client.put('/admin/agents/partner_match',headers=user,json=body).status_code==403
    assert client.put('/admin/agents/arbitrary',headers=admin,json=body).status_code==404
    assert client.put('/admin/agents/partner_match',headers=admin,json={**body,'icon':'https://example.com/icon'}).status_code==422
    saved=client.put('/admin/agents/partner_match',headers=admin,json=body)
    assert saved.status_code==200
    after=client.get('/admin/agents',headers=admin).json()
    assert after['agents']['partner_match']==body
    assert after['agents']['partner_development']==before['agents']['partner_development'] and after['processing']==before['processing']
    public=client.get('/agents',headers=user).json()
    assert public[0]['id']=='partner_match' and public[0]['name']=='项目伙伴顾问'
    assert set(public[0])=={'id','name','description','icon','enabled'}
    assert 'synthetic-only' not in json.dumps(after)
    assert client.get('/admin/model-configs/usage',headers=admin).status_code==410
    assert client.put('/admin/model-configs/usage/partner_match',headers=admin,json={'modelConfigId':second}).status_code==410
    assert client.put('/admin/model-configs/timeout-settings',headers=admin,json={'timeoutSeconds':1.0,'timeoutRetries':0}).status_code==410
    assert client.get('/model-timeout-settings?agent_id=partner_match',headers=user).json()['timeoutSeconds']==41


def test_agent_selection_thinking_and_timeout_reach_wire_options(client):
    second=another_model();configure('partner_match',modelConfigId=second,thinking=False,timeoutSeconds=17)
    matching=resolver.resolve_model_record('partner_match');development=resolver.resolve_model_record('partner_development')
    assert matching['id']==second and development['id']!=second
    wire=completion_payload(resolver.model_config_from_record(matching),[{'role':'user','content':'synthetic'}])
    assert wire['model']=='deepseek-flash' and wire['thinking']=={'type':'disabled'}
    assert completion_payload(resolver.model_config_from_record(development),[])['thinking']=={'type':'enabled'}
    assert get_settings(execution=matching['_agent_execution']).timeoutSeconds==17
    assert resolver.resolve_model_record('partner_profile')['id']==settings.read()['processing']['modelConfigId']
    with get_db() as conn:
        # Obsolete and unrelated bindings cannot override the new routing.
        conn.execute("INSERT INTO model_usage_configs(scene_key,scene_name,model_config_id,updated_at) VALUES ('partner_match','obsolete',?,'2026')",(development['id'],))
    assert resolver.resolve_model_record('partner_match')['id']==second


def test_match_disable_blocks_new_requests_but_accepted_run_keeps_model_and_policy(prepared,monkeypatch):
    user=prepared[0];first=resolver.resolve_model_record('partner_match')['id'];second=another_model();jobs=[];calls=[]
    configure('partner_match',timeoutSeconds=51)
    monkeypatch.setattr(match.executor,'submit',lambda fn,*args:jobs.append((fn,args)))
    request=match.TaskCreateRequest(requestId=uuid.uuid4(),requirement='合成数据库迁移需求')
    accepted=match.create_task(request,user)
    configure('partner_match',enabled=False,modelConfigId=second,thinking=False,timeoutSeconds=2)
    assert match.create_task(request,user).recordId==accepted.recordId
    with pytest.raises(HTTPException) as error:match.create_task(match.TaskCreateRequest(requestId=uuid.uuid4(),requirement='新的合成需求'),user)
    assert error.value.status_code==409
    def complete(config,messages,schema):
        calls.append(schema['title']);assert config['id']==first
        assert config['_agent_execution']['thinking'] and get_settings().timeoutSeconds==51
        if schema['title']=='MatchUnderstanding':return '{"in_scope":true,"facts":{}}'
        if schema['title']=='InitialSelection':return '{"candidates":[{"partnerId":"partner-1","verificationFocus":"核实迁移经验"}]}'
        with get_db() as conn:name=conn.execute("SELECT name FROM partners WHERE id='partner-1'").fetchone()[0]
        return answer('partner-1',name=name)
    monkeypatch.setattr(development_model,'completion',complete)
    jobs[0][0](*jobs[0][1])
    assert calls==['MatchUnderstanding','InitialSelection','MatchAnswer']
    assert match.get_match_record(accepted.recordId,user).taskStatus=='ready'
    # Same task ownership/history is readable; a new retry is not admitted.
    with get_db() as conn:conn.execute("UPDATE match_records SET task_status='failed' WHERE id=?",(accepted.recordId,))
    with pytest.raises(HTTPException) as error:match.retry_match_record(accepted.recordId,user)
    assert error.value.status_code==409


def test_development_disable_allows_inflight_and_blocks_followup_and_retry(prepared,monkeypatch):
    user=prepared[0];first=resolver.resolve_model_record('partner_development')['id'];second=another_model();calls=[]
    configure('partner_development',timeoutSeconds=53)
    created=life.create(Submit(submission_id='agent-development-once',request=DevelopmentRequest(development_direction='数据库迁移合成需求')),user)
    configure('partner_development',enabled=False,modelConfigId=second,thinking=False,timeoutSeconds=2)
    def complete(config,messages,schema):
        calls.append(schema['title']);assert config['id']==first
        assert config['_agent_execution']['thinking'] and get_settings().timeoutSeconds==53
        return json.dumps(development_response(messages),ensure_ascii=False)
    monkeypatch.setattr(development_model,'completion',complete)
    engine.execute(created['run_id'])
    from backend.app import development_views
    detail=development_views.detail(created['plan_id'],user)
    assert calls==['Understanding','AdviceOutput'] and detail['runs'][0]['status']=='ready'
    assert len(detail['versions'])==1 and detail['plan']['current_version_id']
    with pytest.raises(HTTPException) as error:
        life.revise(created['plan_id'],Revise(submission_id='agent-follow-up',based_on_version_id=detail['plan']['current_version_id'],instruction='为什么推荐'),user)
    assert error.value.status_code==409
    assert development_views.detail(created['plan_id'],user)['plan']['current_version_id']==detail['plan']['current_version_id']
    configure('partner_development',enabled=True)
    failed=life.revise(created['plan_id'],Revise(submission_id='agent-failed-run',based_on_version_id=detail['plan']['current_version_id'],instruction='调整建议'),user)
    run=life.claim(failed['run_id']);life.finish_failure(run['id'],run['execution_token'],'synthetic')
    configure('partner_development',enabled=False)
    from backend.app.routers.development import RetryRun
    with pytest.raises(HTTPException) as error:
        life.retry(created['plan_id'],RetryRun(submission_id='agent-disabled-retry',run_id=run['id'],based_on_version_id=detail['plan']['current_version_id']),user)
    assert error.value.status_code==409


def test_recovery_uses_accepted_timeout_not_new_settings(prepared,monkeypatch):
    user=prepared[0];configure('partner_match',timeoutSeconds=1000);configure('partner_development',timeoutSeconds=1000)
    monkeypatch.setattr(match.executor,'submit',lambda *_:None)
    matching=match.create_task(match.TaskCreateRequest(requestId=uuid.uuid4(),requirement='合成任务'),user)
    development=life.create(Submit(submission_id='agent-budget',request=DevelopmentRequest(development_direction='合成发展')),user)
    old=(datetime.now(timezone.utc)-timedelta(seconds=1800)).isoformat()
    with get_db() as conn:
        conn.execute('UPDATE match_records SET updated_at=? WHERE id=?',(old,matching.recordId))
        conn.execute('UPDATE development_runs SET created_at=? WHERE id=?',(old,development['run_id']))
    configure('partner_match',timeoutSeconds=1);configure('partner_development',timeoutSeconds=1)
    assert recover_stale_tasks(record_id=matching.recordId)==0
    life.recover(plan_id=development['plan_id'])
    with get_db() as conn:assert conn.execute('SELECT status FROM development_runs WHERE id=?',(development['run_id'],)).fetchone()[0]=='pending'
