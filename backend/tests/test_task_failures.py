import json,os
import httpx,pytest
from fastapi import HTTPException
from sqlalchemy import inspect
from backend.app.task_failures import failure,public_failures,PublicTaskError
from backend.app.model_resolver import ModelConfigurationError
from backend.app.database import get_db
from backend.app.routers import match
from backend.app import development_lifecycle as life,development_views as views
from backend.app.development_types import Revise
from backend.app.routers.development import RetryRun
from .conftest import make_user,make_partner,make_task,auth_headers,recommendation
from .test_development_lifecycle import prepared,start,complete,plan

SECRET='INTERNAL_SECRET_PHASE_B_DO_NOT_SHARE'
def http_error(status):
 request=httpx.Request('POST','https://provider.invalid/private')
 return httpx.HTTPStatusError(SECRET,request=request,response=httpx.Response(status,request=request,text=SECRET))

@pytest.mark.parametrize('error,code',[(httpx.ReadTimeout(SECRET),'timeout'),(TimeoutError(SECRET),'timeout'),(http_error(429),'rate_limit'),(http_error(401),'authentication'),(http_error(500),'provider'),(httpx.ConnectError(SECRET),'connection'),(ModelConfigurationError(SECRET),'configuration'),(ValueError(SECRET),'invalid_result'),(RuntimeError(SECRET),'unknown')])
def test_fixed_failure_whitelist(error,code):
 value=failure('generation',error)
 assert value['code']==code and SECRET not in json.dumps(value)
 assert failure('partner_match',PublicTaskError(error))['code']==code
 assert SECRET not in json.dumps(public_failures('generation',json.dumps([dict(value,message=SECRET,action=SECRET,extra=SECRET)])))

def test_legacy_and_unrecognized_fields_are_not_guessed():
 assert public_failures('project_opportunity')[0]['code']=='unknown'
 assert public_failures(SECRET,SECRET)[0]['stage']=='unknown'
 assert public_failures('interrupted')[0]['code']=='interrupted'

def test_actual_model_failure_list_detail_owner_and_success_clear(client,monkeypatch):
 a=make_user('errors-a');b=make_user('errors-b');admin=make_user('errors-admin',role='admin');make_partner()
 monkeypatch.setattr(match,'chat_completion',lambda *a,**k:(_ for _ in ()).throw(httpx.ReadTimeout(SECRET)))
 response=client.post('/agent/match',headers=auth_headers(a),json={'requirement':'合成故障场景'})
 assert response.status_code==502 and SECRET not in response.text
 with get_db() as conn:task=conn.execute('SELECT id,last_error_details FROM match_records').fetchone();assert SECRET not in task['last_error_details']
 for actor in (a,admin):
  detail=client.get('/agent/tasks/'+task['id'],headers=auth_headers(actor));assert detail.status_code==200
  assert detail.json()['failureDetails'][0]['code']=='timeout' and SECRET not in detail.text
 assert client.get('/agent/tasks/'+task['id'],headers=auth_headers(b)).status_code==404
 assert client.get('/agent/tasks',headers=auth_headers(b)).json()['total']==0
 listing=client.get('/agent/tasks',headers=auth_headers(a)).json();assert listing['items'][0]['failureDetails'][0]['code']=='timeout'
 match._set_task_state(task['id'],'ready')
 assert client.get('/agent/tasks/'+task['id'],headers=auth_headers(a)).json()['failureDetails']==[]
 with get_db() as conn:assert conn.execute('SELECT last_error_details FROM match_records WHERE id=?',(task['id'],)).fetchone()[0] is None

def test_multiple_partial_reasons_preserve_recommendations(client,monkeypatch):
 from backend.app import ai_client
 a=make_user('partial-reasons');make_partner();task=make_task(a,'synthetic partial')
 monkeypatch.setattr(match,'_generate_demand_profile',lambda *a,**k:(_ for _ in ()).throw(httpx.ReadTimeout(SECRET)))
 monkeypatch.setattr(ai_client,'chat_completion',lambda *a,**k:(_ for _ in ()).throw(http_error(429)))
 recs=[match.PartnerRecommendation.model_validate(recommendation())]
 assert match._run_task_enrichment(task,'synthetic',recs,'2026',include_tag_suggestions=False)=='partial'
 details=client.get('/agent/tasks/'+task,headers=auth_headers(a)).json()
 assert {x['code'] for x in details['failureDetails']}=={'timeout','rate_limit'}
 assert len(details['recommendations'])==1 and SECRET not in json.dumps(details)

def test_failed_revise_retry_preserves_input_and_confirmed_version(prepared):
 accepted,run=start(prepared);v1=complete(prepared,accepted,run);user=prepared[0];pid=accepted['plan_id']
 views.confirm(pid,v1,user)
 revised=life.revise(pid,Revise(submission_id='failed-change',based_on_version_id=v1,instruction='不要基础课，多给实验'),user)
 running=life.claim(revised['run_id']);life.finish_failure(running['id'],running['execution_token'],'generation',error=httpx.ReadTimeout(SECRET))
 detail=views.detail(pid,user);assert detail['failureDetails'][0]['code']=='timeout'
 assert detail['plan']['confirmed_version_id']==v1==detail['plan']['current_version_id']
 body=RetryRun(submission_id='retry-change',based_on_version_id=v1,run_id=running['id'])
 with pytest.raises(HTTPException) as denied:life.retry(pid,body,prepared[1])
 assert denied.value.status_code==404
 retry=life.retry(pid,body,user);assert life.retry(pid,body,user)['run_id']==retry['run_id']
 with pytest.raises(HTTPException) as conflict:life.retry(pid,body.model_copy(update={'submission_id':'concurrent'}),user)
 assert conflict.value.status_code==409
 with get_db() as conn:
  new=conn.execute('SELECT input_snapshot FROM development_runs WHERE id=?',(retry['run_id'],)).fetchone()[0]
 assert json.loads(new)['instruction']=='不要基础课，多给实验'
 assert plan(pid)['confirmed_version_id']==v1==plan(pid)['current_version_id']
 assert SECRET not in json.dumps(views.detail(pid,user))

@pytest.mark.skipif(not os.environ.get('BANFEI_TEST_DATABASE_URL'),reason='Dedicated PostgreSQL required')
def test_additive_migration_idempotence_and_rollback(client):
 from scripts.migrate_task_failure_details import migrate
 from backend.app.postgres_storage import engine_for
 engine=engine_for(os.environ['DATABASE_URL'])
 assert '/banfei_validation' in os.environ['DATABASE_URL']
 user=make_user('migration-errors');make_partner();task=make_task(user,'retained')
 with engine.begin() as conn:conn.exec_driver_sql('ALTER TABLE match_records DROP COLUMN last_error_details')
 with pytest.raises(RuntimeError):
  with engine.begin() as conn:migrate(conn,fault=lambda:(_ for _ in ()).throw(RuntimeError('synthetic fault')))
 with engine.connect() as conn:assert 'last_error_details' not in {r['name'] for r in inspect(conn).get_columns('match_records')}
 with engine.begin() as conn:assert migrate(conn)['added'] is True
 with engine.begin() as conn:assert migrate(conn)['added'] is False
 with get_db() as conn:assert conn.execute('SELECT requirement,last_error_details FROM match_records WHERE id=?',(task,)).fetchone()[0]=='retained'


def test_successful_real_matching_path_still_returns_recommendations(client,monkeypatch):
 make_partner()
 monkeypatch.setattr(match,'chat_completion',lambda *a,**k:json.dumps([recommendation()]))
 result=match._perform_partner_match('synthetic success')
 assert len(result)==1 and result[0].partnerId=='partner-1'


def test_initial_generation_retry_and_untrusted_history(prepared):
 accepted,run=start(prepared);user=prepared[0];pid=accepted['plan_id']
 life.finish_failure(run['id'],run['execution_token'],'generation',error=ValueError(SECRET))
 with get_db() as conn:
  conn.execute('UPDATE development_runs SET safe_error_message=? WHERE id=?',(SECRET,run['id']))
 assert SECRET not in json.dumps(views.detail(pid,user))
 retry=life.retry(pid,RetryRun(submission_id='retry-initial',run_id=run['id']),user)
 with get_db() as conn:
  assert conn.execute('SELECT run_type FROM development_runs WHERE id=?',(retry['run_id'],)).fetchone()[0]=='generate'
 assert plan(pid)['current_version_id'] is None and plan(pid)['confirmed_version_id'] is None


def test_retry_api_dispatches_once_and_blocks_archived_plan(prepared,client,monkeypatch):
 from backend.app.routers import development
 accepted,run=start(prepared);pid=accepted['plan_id'];user=prepared[0]
 life.finish_failure(run['id'],run['execution_token'],'generation',error=httpx.ReadTimeout(SECRET))
 dispatched=[]
 monkeypatch.setattr(development.executor,'submit',lambda function,run_id:dispatched.append(run_id))
 body={'submission_id':'retry-api','run_id':run['id'],'based_on_version_id':None}
 assert client.post(f'/development/plans/{pid}/retry',headers=auth_headers(prepared[1]),json=body).status_code==404
 for _ in range(2):
  response=client.post(f'/development/plans/{pid}/retry',headers=auth_headers(user),json=body)
  assert response.status_code==202
 assert len(dispatched)==1
 retry=life.claim(dispatched[0]);life.finish_failure(retry['id'],retry['execution_token'],'generation')
 life.archive(pid,user)
 response=client.post(f'/development/plans/{pid}/retry',headers=auth_headers(user),json={**body,'submission_id':'archived-retry','run_id':retry['id']})
 assert response.status_code==409 and len(dispatched)==1
