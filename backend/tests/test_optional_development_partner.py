"""Isolated PostgreSQL coverage: optional association and durable self-reported baseline."""
import copy,json,uuid
import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from backend.app import development_lifecycle as life, development_engine as engine, development_views as views, development_model as model
from backend.app.database import get_db
from backend.app.development_types import DevelopmentRequest, Submit, Revise, Conversation
from backend.app.routers import development
from backend.app.development_partner_schema import migrate,rollback,verify_optional_partner
from backend.tests.test_development_lifecycle import prepared,plan
from backend.tests.conftest import auth_headers

RAW='我有个伙伴，现在只有基本的上云迁移能力，想往AI agent开发方向发展，请推荐下相应的课程和实验'
BASE='基本的上云迁移能力'
CORRECTED='已经能交付 RAG 知识库，并有 Python 开发经验'

@pytest.fixture
def replay(prepared,monkeypatch):
    calls=[]
    with get_db() as conn:conn.execute("UPDATE model_configs SET api_key='synthetic-only',api_key_source='db'")
    def complete(config,messages,schema):
        from backend.tests.support.development_mock import response
        data=json.loads(messages[-1]['content']);calls.append(copy.deepcopy(data))
        # Independent connection observes the committed task before any model invocation.
        with get_db() as conn:assert conn.execute('SELECT count(*) FROM development_runs').fetchone()[0]>0
        result=response(messages)
        if 'analyze' in messages[0]['content']:
            baseline=data['request'].get('known_baseline','')
            if not data.get('current') and RAW in data['message']:baseline=BASE
            if data['message'].startswith('纠正基础'):baseline=CORRECTED
            if data['message']=='撤回之前的能力自述':baseline=''
            result['effective_baseline']=baseline
        return json.dumps(result,ensure_ascii=False)
    monkeypatch.setattr(model,'completion',complete)
    return prepared,calls,complete

def create(replay,partner=None):
    accepted=life.create(Submit(submission_id=str(uuid.uuid4()),request=DevelopmentRequest(target_partner_id=partner,development_direction=RAW,model_input_allowed=True)),replay[0][0])
    engine.execute(accepted['run_id'])
    detail=views.detail(accepted['plan_id'],replay[0][0])
    assert detail['runs'][0]['status']=='ready',detail['runs']
    return accepted,detail

@pytest.mark.parametrize('partner',[None,'','   ','partner-1'])
def test_optional_create_real_null_exact_original_and_idempotency(replay,partner):
    user=replay[0][0]
    with get_db() as conn:before=[dict(x) for x in conn.execute('SELECT * FROM partners ORDER BY id')]
    req=DevelopmentRequest(target_partner_id=partner,development_direction=RAW,model_input_allowed=True)
    payload=Submit(submission_id='optional-create-repeated',request=req)
    accepted=life.create(payload,user)
    assert life.create(payload,user)['run_id']==accepted['run_id']
    assert replay[1]==[]
    with get_db() as conn:
        row=conn.execute('SELECT target_partner_id,payload_json FROM development_requests').fetchone()
        assert row['target_partner_id']==req.target_partner_id
        assert json.loads(row['payload_json'])['raw_demand']==RAW
        assert conn.execute('SELECT target_partner_id FROM development_plans').fetchone()[0]==req.target_partner_id
    engine.execute(accepted['run_id']);detail=views.detail(accepted['plan_id'],user)
    assert detail['payload']['target_partner_id']==req.target_partner_id
    assert detail['request']['known_baseline']==BASE
    assert detail['partner_name']==('验证伙伴' if req.target_partner_id else None)
    assert replay[1][0]['request']['development_direction']==RAW
    assert replay[1][1]['request']['known_baseline']==BASE
    if not req.target_partner_id:assert replay[1][0]['profile']['shared_evidence']==[] and 'capabilities' not in replay[1][0]['profile']
    with get_db() as conn:assert [dict(x) for x in conn.execute('SELECT * FROM partners ORDER BY id')]==before
    engine.execute(accepted['run_id']);assert len(views.detail(accepted['plan_id'],user)['versions'])==1

@pytest.mark.parametrize('partner',[None,'partner-1'])
def test_corrected_baseline_reaches_actual_model_after_history_window_and_new_version(replay,partner,tmp_path,record_property):
    accepted,detail=create(replay,partner);pid=accepted['plan_id'];user=replay[0][0];base=detail['plan']['current_version_id']
    messages=['纠正基础：'+CORRECTED,'为什么推荐这个方向？','再解释推荐依据','这些资源适合什么目标','请说明如何选择','重新规划，只要进阶实验']
    for i,message in enumerate(messages):
        run=views.converse(pid,Conversation(submission_id=f'baseline-round-{i}',based_on_version_id=base,message=message),user)
        engine.execute(run['run_id']);after=views.detail(pid,user)
        assert after['runs'][0]['status']=='ready',after['runs']
        assert after['request']['known_baseline']==CORRECTED
        if i<len(messages)-1:assert after['plan']['current_version_id']==base
    assert after['plan']['current_version_id']!=base and len(after['versions'])==2
    actual=[c for c in replay[1] if c.get('message')==messages[-1]][0]
    assert actual['request']['known_baseline']==CORRECTED
    assert len(actual['recent_exchanges'])==3
    assert all('纠正基础' not in x['message'] for x in actual['recent_exchanges'])
    assert after['payload']['effective_request']['known_baseline']==CORRECTED
    capture=tmp_path/'actual-model-baseline.json'
    capture.write_text(json.dumps({'target_partner_id':partner,'initial_model_request':replay[1][0]['request'],'first_generation_request':replay[1][1]['request'],'later_model_request':actual['request'],'recent_messages':[x['message'] for x in actual['recent_exchanges']],'persisted_baseline':after['payload']['effective_request']['known_baseline']},ensure_ascii=False,indent=2))
    record_property('actual_model_baseline_evidence',str(capture))
    assert after['request']['raw_demand']==RAW
    base=after['plan']['current_version_id']
    run=views.converse(pid,Conversation(submission_id='withdraw-baseline',based_on_version_id=base,message='撤回之前的能力自述'),user)
    engine.execute(run['run_id']);assert views.detail(pid,user)['request']['known_baseline']==''


def test_invalid_partner_sources_and_missing_direction_are_not_silently_unlinked(replay):
    user=replay[0][0]
    for request,status in [(DevelopmentRequest(target_partner_id='missing',development_direction=RAW),404),(DevelopmentRequest(development_direction=RAW,source_task_id='missing'),422),(DevelopmentRequest(development_direction=RAW,source_case_id='missing'),422),(DevelopmentRequest(),422)]:
        with pytest.raises(HTTPException) as error:life.create(Submit(submission_id=str(uuid.uuid4()),request=request),user)
        assert error.value.status_code==status
    assert replay[1]==[]
    with get_db() as conn:assert conn.execute('SELECT count(*) FROM development_plans').fetchone()[0]==0

@pytest.mark.parametrize('partner',[None,'partner-1'])
def test_existing_task_cannot_change_partner_or_accept_invented_output(replay,monkeypatch,partner):
    accepted,detail=create(replay,partner);pid=accepted['plan_id'];user=replay[0][0];base=detail['plan']['current_version_id']
    with pytest.raises(HTTPException) as error:
        life.revise(pid,Revise(submission_id='change-association',based_on_version_id=base,instruction='调整',request=DevelopmentRequest(target_partner_id='partner-1' if partner is None else None,development_direction=RAW)),user)
    assert error.value.status_code==409
    def wrong(c,m,s):
        result=json.loads(replay[2](c,m,s));result['target_partner_id']='partner-1' if partner is None else None;return json.dumps(result)
    monkeypatch.setattr(model,'completion',wrong)
    run=views.converse(pid,Conversation(submission_id='invented-association',based_on_version_id=base,message='为什么？'),user)
    engine.execute(run['run_id']);after=views.detail(pid,user)
    assert after['runs'][0]['status']=='failed' and after['plan']['current_version_id']==base


def test_null_history_pagination_search_owner_admin_detail_archive(replay,client):
    user,other,admin,_=replay[0];headers=auth_headers(user)
    ids=[create(replay,partner)[0]['plan_id'] for partner in (None,'partner-1',None)]
    own=client.get('/agent/tasks?task_type=development_plan&pageSize=1',headers=headers).json()
    assert own['total']==3 and own['totalPages']==3
    seen=[]
    for page in range(1,4):
        result=client.get(f'/agent/tasks?task_type=development_plan&pageSize=1&page={page}&keyword=上云迁移',headers=headers).json()
        assert result['total']==3;seen.extend(i['id'] for i in result['items'])
    assert set(seen)==set(ids)
    for id in ids:
        assert client.get('/agent/tasks/'+id,headers=headers).status_code==200
        assert client.get('/development/plans/'+id,headers=auth_headers(other)).status_code==404
        assert client.get('/development/plans/'+id,headers=auth_headers(admin)).status_code==200
    assert client.get('/agent/tasks?task_type=development_plan',headers=auth_headers(other)).json()['total']==0
    assert client.get('/admin/tasks?task_type=development_plan',headers=auth_headers(admin)).json()['total']==3
    assert client.patch('/agent/tasks/'+ids[0]+'/archive',headers=headers).status_code==204
    assert client.get('/agent/tasks?task_type=development_plan&status=archived',headers=headers).json()['items'][0]['id']==ids[0]
    assert client.patch('/agent/tasks/'+ids[0]+'/restore',headers=headers).status_code==204


def test_null_retry_keeps_current_baseline_and_idempotency(replay,monkeypatch):
    accepted,detail=create(replay);user=replay[0][0];pid=accepted['plan_id'];base=detail['plan']['current_version_id']
    def fail(c,m,s):
        if 'plan' in m[0]['content'].split('。')[0]:raise RuntimeError('synthetic generation failure')
        return replay[2](c,m,s)
    monkeypatch.setattr(model,'completion',fail)
    run=views.converse(pid,Conversation(submission_id='nullable-failed',based_on_version_id=base,message='重新规划，只给实验'),user)
    engine.execute(run['run_id']);assert plan(pid)['current_version_id']==base
    monkeypatch.setattr(model,'completion',replay[2])
    body=development.RetryRun(submission_id='nullable-retry',run_id=run['run_id'],based_on_version_id=base)
    retry=life.retry(pid,body,user);engine.execute(retry['run_id'])
    after=views.detail(pid,user);assert len(after['versions'])==2 and after['request']['known_baseline']==BASE
    assert life.retry(pid,body,user)['replayed']

@pytest.fixture
def schema18_existing_development(prepared):
    # History: 727e122 has two non-null partner columns; 0fda85c makes them
    # nullable (schema 19); 9cbb660 adds only partner_profile_sources (schema 20).
    accepted=life.create(Submit(submission_id='existing-before-upgrade',request=prepared[3]),prepared[0])
    with get_db() as conn:
        assert conn.execute('SELECT current_database()').fetchone()[0] in ('banfei_agent_test','banfei_validation')
        assert conn.execute('SELECT current_schema()').fetchone()[0].startswith('validation_')
        assert conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]=='20'
        assert conn.execute('SELECT count(*) FROM partner_profile_sources').fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM app_metadata WHERE key LIKE 'profile_source_legacy:%'").fetchone()[0]==0
        # Rebuild the historical structure in this invocation's disposable schema.
        conn.execute('DROP TABLE partner_profile_sources')
        for table in ('development_plans','development_requests'):
            conn.execute(f'ALTER TABLE {table} ALTER COLUMN target_partner_id SET NOT NULL')
        conn.execute("UPDATE app_metadata SET value='18' WHERE key='schema_version'")
        assert conn.execute("SELECT to_regclass('partner_profile_sources')").fetchone()[0] is None
        nulls=dict(conn.execute("SELECT table_name,is_nullable FROM information_schema.columns WHERE table_schema=current_schema() AND table_name IN ('development_plans','development_requests') AND column_name='target_partner_id'"))
        assert nulls=={'development_plans':'NO','development_requests':'NO'}
        assert conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]=='18'
    return accepted


@pytest.mark.parametrize('fault',[False,True])
def test_existing_schema_migration_is_atomic_preserves_rows_and_foreign_keys(prepared,schema18_existing_development,fault):
    accepted=schema18_existing_development
    with get_db() as conn:
        before={t:[dict(x) for x in conn.execute(f'SELECT * FROM {t} ORDER BY id')] for t in ('partners','development_plans','development_requests','development_runs')}
    def injected():raise RuntimeError('synthetic migration failure')
    try:
        with get_db() as conn:migrate(conn,injected if fault else None)
    except RuntimeError:
        assert fault
    with get_db() as conn:
        assert conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]==('18' if fault else '19')
        for t,rows in before.items():assert [dict(x) for x in conn.execute(f'SELECT * FROM {t} ORDER BY id')]==rows
        nulls=[x[0] for x in conn.execute("SELECT is_nullable FROM information_schema.columns WHERE table_schema=current_schema() AND table_name IN ('development_plans','development_requests') AND column_name='target_partner_id'")]
        assert nulls==(['NO','NO'] if fault else ['YES','YES'])
        if fault:migrate(conn)
        verify_optional_partner(conn);assert migrate(conn)['already_current']
    with pytest.raises(IntegrityError):
        with get_db() as conn:conn.execute("UPDATE development_plans SET target_partner_id='invented' WHERE id=?",(accepted['plan_id'],))
    with pytest.raises(IntegrityError):
        with get_db() as conn:conn.execute("UPDATE development_requests SET target_partner_id='invented'")
    with get_db() as conn:rollback(conn);migrate(conn)
    life.create(Submit(submission_id='unlinked-after-upgrade',request=DevelopmentRequest(development_direction=RAW)),prepared[0])
    with pytest.raises(RuntimeError,match='Unlinked tasks'):
        with get_db() as conn:rollback(conn)
    with get_db() as conn:verify_optional_partner(conn);assert conn.execute('SELECT count(*) FROM development_plans').fetchone()[0]==2
