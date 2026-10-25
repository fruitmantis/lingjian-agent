from .support.models import create_model
"""Model selection and recovery contracts, isolated PostgreSQL and synthetic responses only."""
import json,uuid
import httpx,pytest
from fastapi import HTTPException
from backend.app import agent_settings as settings,model_resolver,development_model,development_lifecycle as life,development_engine as engine,development_views as views
from backend.app.database import get_db
from backend.app.routers import model_config,match
from backend.app.routers.development import RetryRun
from backend.app.development_types import Submit,DevelopmentRequest,Revise
from backend.app.task_failures import failure,public_failures
from .conftest import make_user,auth_headers
from .test_development_lifecycle import prepared
from .test_agent_settings import configure
from .support.development_mock import response as development_response
from .test_partner_match_stages import answer


def another(selectable=True):
 return create_model(name='合成模型B',baseUrl='https://synthetic.invalid/v1',modelName='synthetic-b',apiKey='synthetic-only',userSelectable=selectable).id


def test_options_are_authenticated_minimal_and_do_not_open_processing(client):
 user=auth_headers(make_user('choice-user'));admin=auth_headers(make_user('choice-admin',role='admin'));default=settings.read()['agents']['partner_match']['modelConfigId'];hidden=another(False);opened=another()
 assert client.get('/agents/partner_match/models').status_code==401
 assert client.get('/agents/processing/models',headers=user).status_code==404
 data=client.get('/agents/partner_match/models',headers=user).json()
 assert {m['id'] for m in data['models']}=={default,opened}
 assert all(set(m)=={'id','name','isDefault','providerId','providerName'} for m in data['models'])
 with get_db() as conn:
  relations={r['id']:(r['provider_id'],r['provider_name']) for r in conn.execute('SELECT m.id,m.provider_id,p.name AS provider_name FROM model_configs m JOIN model_providers p ON p.id=m.provider_id')}
 assert all((m['providerId'],m['providerName'])==relations[m['id']] for m in data['models'])
 assert 'synthetic-only' not in json.dumps(data) and 'baseUrl' not in json.dumps(data)
 assert client.put('/admin/model-configs/'+hidden,headers=user,json={'userSelectable':True}).status_code==403
 assert client.put('/admin/model-configs/'+hidden,headers=admin,json={'userSelectable':True}).json()['userSelectable']
 assert hidden in {m['id'] for m in settings.model_options('partner_match')['models']}
 model_config.toggle_enable(opened,False)
 assert opened not in {m['id'] for m in settings.model_options('partner_match')['models']}
 configure('partner_match',enabled=False)
 assert not settings.model_options('partner_match')['agentEnabled']



@pytest.mark.parametrize('agent_id',['partner_match','partner_development'])
def test_options_keep_real_provider_identity_for_same_names_without_opening_empty_providers(client,agent_id):
 user=auth_headers(make_user('provider-choice-user'))
 first=model_config.create_provider(model_config.ProviderCreate(name='同名供应商',baseUrl='https://first.invalid/v1',apiKey='synthetic-first'))
 second=model_config.create_provider(model_config.ProviderCreate(name='同名供应商',baseUrl='https://second.invalid/v1',apiKey='synthetic-second'))
 empty=model_config.create_provider(model_config.ProviderCreate(name='空供应商',baseUrl='https://empty.invalid/v1'))
 one=create_model(name='同名模型',modelName='same-model',providerId=first.id,userSelectable=True)
 two=create_model(name='同名模型',modelName='same-model',providerId=second.id,userSelectable=True)
 disabled=create_model(name='停用模型',modelName='disabled',providerId=second.id,userSelectable=True,enabled=False)
 private=create_model(name='未开放模型',modelName='private',providerId=first.id,userSelectable=False)
 before=settings.read()
 response=client.get('/agents/'+agent_id+'/models',headers=user)
 assert response.status_code==200
 data=response.json();rows={m['id']:m for m in data['models']}
 assert {one.id,two.id}.issubset(rows)
 assert rows[one.id]['providerId']==first.id and rows[two.id]['providerId']==second.id
 assert rows[one.id]['providerName']==rows[two.id]['providerName']=='同名供应商'
 assert rows[one.id]['name']==rows[two.id]['name']=='同名模型'
 assert disabled.id not in rows and private.id not in rows
 assert empty.id not in {row['providerId'] for row in rows.values()}
 assert {m['id'] for m in rows.values() if m['isDefault']}=={before['agents'][agent_id]['modelConfigId']}
 assert all(set(m)=={'id','name','isDefault','providerId','providerName'} for m in rows.values())
 assert all(value not in json.dumps(data) for value in ['synthetic-first','synthetic-second','first.invalid','second.invalid','apiKeySource'])
 assert settings.read()==before


def test_selection_does_not_change_default_and_unavailable_selection_rolls_back(prepared,monkeypatch):
 user=prepared[0];before=settings.read();hidden=another(False)
 monkeypatch.setattr(match.executor,'submit',lambda *args:None)
 with get_db() as conn:count=conn.execute('SELECT count(*) FROM match_records').fetchone()[0]
 with pytest.raises(HTTPException) as error:match.create_task(match.TaskCreateRequest(requestId=uuid.uuid4(),requirement='合成需求',modelConfigId=hidden),user)
 assert error.value.status_code==422
 with get_db() as conn:assert conn.execute('SELECT count(*) FROM match_records').fetchone()[0]==count
 assert settings.read()==before


def test_match_selection_reaches_both_calls_and_idempotency_includes_model(prepared,monkeypatch):
 user=prepared[0];chosen=another();jobs=[];calls=[];defaults=settings.read()
 monkeypatch.setattr(match.executor,'submit',lambda fn,*args:jobs.append((fn,args)))
 request=match.TaskCreateRequest(requestId=uuid.uuid4(),requirement='合成数据库迁移需求',modelConfigId=chosen);accepted=match.create_task(request,user)
 assert match.create_task(request,user).recordId==accepted.recordId and len(jobs)==1
 with pytest.raises(HTTPException) as error:match.create_task(request.model_copy(update={'modelConfigId':None}),user)
 assert error.value.status_code==409
 def complete(config,messages,schema):
  calls.append(config['id']);assert config['id']==chosen
  if schema['title']=='MatchUnderstanding':return '{"in_scope":true,"facts":{}}'
  with get_db() as conn:name=conn.execute("SELECT name FROM partners WHERE id='partner-1'").fetchone()[0]
  return answer('partner-1',name=name)
 monkeypatch.setattr(development_model,'completion',complete);jobs[0][0](*jobs[0][1])
 detail=match.get_match_record(accepted.recordId,user);assert detail.taskStatus=='ready';assert calls==[chosen,chosen];assert detail.modelSelection=={'id':chosen,'name':'合成模型B'};assert settings.read()==defaults
 with get_db() as conn:conn.execute("UPDATE match_records SET task_status='failed' WHERE id=?",(accepted.recordId,))
 match.retry_match_record(accepted.recordId,user);assert all(x==chosen for x in calls)


def test_development_fixed_selection_failed_followup_keeps_version_and_retry(prepared,monkeypatch):
 user=prepared[0];chosen=another();calls=[]
 def complete(config,messages,schema):
  calls.append(config['id']);assert config['id']==chosen
  return json.dumps(development_response(messages),ensure_ascii=False)
 monkeypatch.setattr(development_model,'completion',complete)
 created=life.create(Submit(submission_id='model-create-once',modelConfigId=chosen,request=DevelopmentRequest(development_direction='合成数据库迁移需求')),user);engine.execute(created['run_id']);detail=views.detail(created['plan_id'],user);current=detail['plan']['current_version_id'];assert current and calls==[chosen,chosen];assert detail['modelSelection']['id']==chosen
 body=Revise(submission_id='model-followup-once',based_on_version_id=current,instruction='  保留方案，只调整实验  ',modelConfigId=chosen);run=life.revise(created['plan_id'],body,user)
 with pytest.raises(HTTPException) as error:life.revise(created['plan_id'],body.model_copy(update={'modelConfigId':None}),user)
 assert error.value.status_code==409
 def timeout(*args):
  error=httpx.ReadTimeout('synthetic-timeout');error.model_call_failure=True;raise error
 monkeypatch.setattr(development_model,'completion',timeout);engine.execute(run['run_id']);failed=views.detail(created['plan_id'],user);assert failed['plan']['current_version_id']==current and failed['payload'];assert failed['failedInput']==body.instruction;assert failed['failureDetails'][0]['modelRelated']
 retry=life.retry(created['plan_id'],RetryRun(submission_id='model-retry-once',based_on_version_id=current,run_id=run['run_id']),user)
 with get_db() as conn:snapshot=json.loads(conn.execute('SELECT input_snapshot FROM development_runs WHERE id=?',(retry['run_id'],)).fetchone()[0])
 assert snapshot['agent_execution']['modelConfigId']==chosen and snapshot['instruction']==body.instruction


@pytest.mark.parametrize('kind',['timeout','rate_limit','connection','provider','authentication','invalid_result'])
def test_model_failure_classified_at_boundary_only(kind):
 request=httpx.Request('POST','https://synthetic.invalid')
 errors={'timeout':httpx.ReadTimeout('synthetic'),'connection':httpx.ConnectError('synthetic'),'invalid_result':ValueError('synthetic')}
 error=errors.get(kind) or httpx.HTTPStatusError('synthetic',request=request,response=httpx.Response({'rate_limit':429,'provider':500,'authentication':401}[kind],request=request))
 error.model_call_failure=True;value=failure('understanding',error);assert value['code']==kind and value['modelRelated'];assert value['action']=='返回并切换模型';assert public_failures('understanding',json.dumps([value]))==[value]
 generic=failure('persistence',error);assert not generic['modelRelated'] and generic['action']!='返回并切换模型'
 assert not failure('understanding',TimeoutError('application timeout'))['modelRelated']


def test_optional_model_preserves_old_submission_hash():
 assert life.fingerprint({'submission_id':'legacy','request':{}})==life.fingerprint({'submission_id':'legacy','request':{},'modelConfigId':None})
