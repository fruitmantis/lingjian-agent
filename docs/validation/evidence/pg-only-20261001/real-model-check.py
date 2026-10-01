"""Bounded current-code check; synthetic PG records, existing model settings, no runtime writes."""
import json,os,sys,tempfile,time,uuid
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path('/home/yuan/project/lingjian-agent-enablement');sys.path.insert(0,str(ROOT));os.chdir(ROOT)
private=json.loads((ROOT/'.isolation/runtime/dev/environment.json').read_text());os.environ.update(private)
validation=json.loads((ROOT/'.isolation/runtime/dev/validation-environment.json').read_text())
os.environ['BANFEI_TEST_DATABASE_URL']=validation['BANFEI_TEST_DATABASE_URL']
root=Path(tempfile.mkdtemp(prefix='banfei-pg-real-'));report={'kind':'bounded-real-provider-synthetic-PG','max_http_requests':12,'planned_http_requests':8,'calls':[],'checks':{},'input_sha256':'c5e404f8b974bdddeaae4b8d5d59c05e74dc2fd1a58839faf344a91a5a75050b'}
output=ROOT/'docs/validation/evidence/pg-only-20261001/real-model-final.json'
assert not output.exists(), 'Do not overwrite previous real-provider evidence'
def save():output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
from backend.app.database import get_db,get_readonly_db
from backend.app.model_resolver import resolve_model_record
from backend.app.model_timeout_settings import get_settings
# These reads do not touch runtime business rows or write its model configuration.
selected={scene:resolve_model_record(scene,read_only=True) for scene in ('partner_development','partner_match')}
policy=get_settings()
from backend.tests.postgres_support import empty_postgres_schema
from backend.app.postgres_storage import initialize_empty_schema
from cryptography.fernet import Fernet
os.environ.update(LINGJIAN_UPLOADS_DIR=str(root/'uploads'),BANFEI_ERROR_LOG_PATH=str(root/'errors.jsonl'),JWT_SECRET_KEY='synthetic-real-provider-check-0123456789',BANFEI_IDENTITY_ENCRYPTION_KEY=Fernet.generate_key().decode())
# database.py was imported for read-only configuration: redirect its captured file paths too.
import backend.app.database as database
database.UPLOADS_DIR=root/'uploads';database.CHROMA_DIR=root/'chroma'
for name in ('VALIDATION_FAKE_LLM_BASE_URL','BANFEI_MATCH_DELAY_PROXY_URL','BANFEI_MATCH_DELAY_UPSTREAM'):os.environ.pop(name,None)
from backend.app import development_model as model,development_lifecycle as life,development_engine as engine,development_views as views,enablement as resources
from backend.app.development_types import Submit,DevelopmentRequest,Conversation
from backend.app.routers import development,match
from backend.app.model_network_policy import install_model_network_policy
install_model_network_policy([x['base_url'] for x in selected.values()])
original_client=model.httpx.AsyncClient
class AuditedClient(original_client):
 async def send(self,request,**kwargs):
  assert len(report['calls'])<report['max_http_requests'],'Bounded real request budget reached'
  item={'stage':report['stage'],'provider':urlsplit(str(request.url)).hostname,'model':json.loads(request.content)['model'],'status':'started'};report['calls'].append(item);save();started=time.monotonic()
  try:
   response=await super().send(request,**kwargs);item['http_status']=response.status_code;item['status']='received' if response.is_success else 'http_error'
   if response.is_success:item['usage']=response.json().get('usage')
   return response
  except Exception as error:item['status']=type(error).__name__;raise
  finally:item['seconds']=round(time.monotonic()-started,3);save()
model.httpx.AsyncClient=AuditedClient
try:
 with empty_postgres_schema() as url:
  os.environ['DATABASE_URL']=url;initialize_empty_schema(url)
  from backend.tests.support.seed_validation_db import seed
  seed()
  with get_db() as conn:
   conn.execute('UPDATE model_configs SET enabled=0,is_default=0')
   for row in {v['id']:v for v in selected.values()}.values():
    columns=list(row);conn.execute('INSERT INTO model_configs ('+','.join(columns)+') VALUES ('+','.join('?' for _ in columns)+') ON CONFLICT(id) DO UPDATE SET '+','.join(c+'=excluded.'+c for c in columns if c!='id'),list(row.values()))
   for scene,row in selected.items():conn.execute('UPDATE model_usage_configs SET model_config_id=? WHERE scene_key=?',(row['id'],scene))
   conn.execute("UPDATE app_metadata SET value=? WHERE key='model_timeout_settings'",(policy.model_dump_json(),))
   conn.execute("UPDATE partners SET name='合成数据库伙伴',intro='合成测试公司，已有数据库迁移实施经验',capabilities='数据库迁移,回退验证',industries='金融',service_areas='北京市',ai_profile='合成资料：实施过数据库迁移与回退验证项目，能够提供迁移方案及演练报告。仅具备中小规模经验，大规模项目和交付排期需核实。' WHERE id='partner-1'")
   conn.execute("UPDATE cases SET title='合成数据库迁移案例',description='合成测试：完成数据库迁移和回退演练，交付迁移方案和演练报告。规模为中小型。' WHERE id='case-1'")
   user=dict(conn.execute("SELECT * FROM users WHERE id='user-a-id'").fetchone())
  for i,title in enumerate(('数据库迁移验证实验','数据库回退演练实验','数据库监控实验'),1):
   row=resources.save('resource','real-check-lab-'+str(i),resources.ResourceSave(base_revision=0,metadata=resources.ResourceMetadata(resource_type='lab',title=title,summary=title+'，合成验证资源',lab_goals=title,level='advanced',source_url='https://example.com/labs/'+str(i))),'admin-1-id')
   row=resources.permissions('resource',row['source_id'],resources.Permissions(base_revision=row['revision'],system_visible=True,model_allowed=True,partner_allowed=True,reason='合成验证授权'),'admin-1-id')
   resources.publish('resource',row['source_id'],resources.Revision(base_revision=row['revision']),'admin-1-id')
  report['stage']='partner-match';jobs=[];original_submit=match.executor.submit;match.executor.submit=lambda fn,*args:jobs.append((fn,args))
  try:accepted=match.create_task(match.TaskCreateRequest(requestId=uuid.uuid4(),requirement='合成测试：北京金融行业的中小型数据库迁移项目，寻找具备数据库迁移及回退演练经验的合作伙伴；交付排期和大规模经验须核实。'),user)
  finally:match.executor.submit=original_submit
  assert not report['calls'];assert match.get_match_record(accepted.recordId,user).recommendations==[]
  report['checks']['match_committed_before_model']=True
  jobs[0][0](*jobs[0][1]);result=match.get_match_record(accepted.recordId,user)
  assert result.taskStatus=='ready' and any(r.partnerId=='partner-1' for r in result.recommendations), 'Matching failed or synthetic matching partner omitted'
  report['checks']['match_recommendation_saved']=True;save()
  report['stage']='development-first';before=len(report['calls'])
  created=life.create(Submit(submission_id='real-check-development',request=DevelopmentRequest(target_partner_id='partner-1',development_direction='合成测试：希望提升数据库迁移及回退验证能力。请按顺序只推荐数据库迁移验证实验、数据库回退演练实验这两个实验，并说明先后关系。')),user)
  assert len(report['calls'])==before and views.detail(created['plan_id'],user)['versions']==[]
  report['checks']['development_committed_before_model']=True
  engine.execute(created['run_id']);initial=views.detail(created['plan_id'],user);base=initial['plan']['current_version_id']
  assert base and len(initial['versions'])==1, 'Initial real generation failed'
  def items(detail):return [i for s in detail['payload']['stages'] for i in s['items']]
  assert [i['source_id'] for i in items(initial)]==['real-check-lab-1','real-check-lab-2'], 'Initial real resource selection/order mismatch'
  from backend.tests.support.legacy_development import legacy_confirmed
  legacy_confirmed(created['plan_id'],base,user)
  report['checks']['initial_version_and_two_labs_saved']=True;save()
  report['stage']='explanation';explain=views.converse(created['plan_id'],Conversation(submission_id='real-explain',based_on_version_id=base,message='为什么推荐第一个实验？'),user)
  engine.execute(explain['run_id']);after=views.detail(created['plan_id'],user)
  assert after['runs'][0]['status']=='ready' and after['conversation'][-1]['answer']
  assert len(after['versions'])==1 and after['plan']['current_version_id']==base
  report['checks']['explanation_answer_without_new_version']=True;save()
  report['stage']='modification-understanding';change=views.converse(created['plan_id'],Conversation(submission_id='real-modify',based_on_version_id=base,message='请只把第二个实验替换为数据库监控实验，第一项以及其余无关内容保持原样。'),user)
  original_completion=model.completion;injected=[]
  def failed_patch(config,messages,schema):
   if messages[0]['content'].startswith('partner_development:patch'):
    injected.append(True);raise TimeoutError('Synthetic fault after real understanding, before patch supplier request')
   return original_completion(config,messages,schema)
  model.completion=failed_patch
  try:engine.execute(change['run_id'])
  finally:model.completion=original_completion
  failed=views.detail(created['plan_id'],user)
  assert injected==[True] and failed['runs'][0]['status']=='failed' and failed['plan']['current_version_id']==base and len(failed['versions'])==1
  report['checks']['injected_patch_failure_kept_old_version']=True
  report['stage']='modification-retry';payload=development.RetryRun(submission_id='real-modify-retry',based_on_version_id=base,run_id=change['run_id'])
  retry=life.retry(created['plan_id'],payload,user);engine.execute(retry['run_id']);changed=views.detail(created['plan_id'],user)
  assert changed['runs'][0]['status']=='ready' and len(changed['versions'])==2 and changed['plan']['current_version_id']!=base
  assert items(changed)[0]==items(initial)[0] and items(changed)[1]['source_id']=='real-check-lab-3' and items(changed)[1]['item_id']==items(initial)[1]['item_id']
  with get_db() as conn:
   assert conn.execute('SELECT confirmed_version_id FROM development_plans WHERE id=?',(created['plan_id'],)).fetchone()[0]==base
   assert conn.execute('SELECT run_id FROM development_versions WHERE id=?',(changed['plan']['current_version_id'],)).fetchone()[0]==retry['run_id']
  before=len(report['calls']);again=life.retry(created['plan_id'],payload,user);engine.execute(again['run_id'])
  assert len(report['calls'])==before and len(views.detail(created['plan_id'],user)['versions'])==2
  report['checks']['real_retry_saved_modified_version_current_and_confirmed_correct']=True
  report['checks']['successful_retry_replay_no_new_version_or_model_call']=True
  report['result']='PASS';save()
 report['owned_schema_removed']=True
except Exception as error:
 report['result']='FAIL';report['safe_error_type']=type(error).__name__;report['failed_stage']=report.get('stage')
 # Record assertion labels only, never arbitrary provider or connection messages.
 if isinstance(error,AssertionError):report['assertion']=str(error)
finally:
 model.httpx.AsyncClient=original_client
 if 'url' in globals():
  from backend.app.postgres_storage import engine_for
  from sqlalchemy import text
  from sqlalchemy.engine import make_url
  schema=make_url(url).query['options'].removeprefix('-csearch_path=')
  with engine_for(os.environ['BANFEI_TEST_DATABASE_URL']).connect() as check:
   report['owned_schema_removed']=not bool(check.execute(text('SELECT 1 FROM pg_namespace WHERE nspname=:schema'),{'schema':schema}).first())
 save();print(json.dumps({'result':report.get('result'),'calls':len(report['calls']),'checks':report['checks'],'failed_stage':report.get('failed_stage')},ensure_ascii=False))
sys.exit(0 if report.get('result')=='PASS' else 1)
