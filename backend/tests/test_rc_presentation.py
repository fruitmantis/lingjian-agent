"""Current-only task presentation, using real lifecycle transitions and authorization."""
import pytest
from fastapi import HTTPException
from backend.app import development_lifecycle as life,development_views as views
from backend.app.database import get_db
from backend.app.development_types import Revise
from backend.tests.conftest import auth_headers
from backend.tests.test_development_lifecycle import prepared,start,complete,plan
from backend.tests.support.legacy_development import legacy_confirmed

@pytest.mark.parametrize('legacy',[False,True])
@pytest.mark.parametrize('state,expected,current,run_status',[
 ('first_failed','generation_failed',None,'failed'),
 ('generating','generating',None,'running'),
 ('v1','available',1,'ready'),
 ('v2','available',2,'ready'),
 ('revising','generating',1,'running'),
 ('failed_revise','available',1,'failed'),
 ('interrupted_revise','available',1,'interrupted'),
 ('archived','archived',1,'ready'),
])
def test_current_task_states_ignore_legacy_confirmation(client,prepared,state,expected,current,run_status,legacy):
 user,other,admin,request=prepared
 accepted,run=start(prepared);pid=accepted['plan_id'];legacy_pointer=None
 if state=='first_failed':life.finish_failure(run['id'],run['execution_token'],'model')
 elif state!='generating':
  v1=complete(prepared,accepted,run)
  if legacy:
   legacy_confirmed(pid,v1,user);legacy_pointer=v1
  if state in ('v2','revising','failed_revise','interrupted_revise'):
   second=life.revise(pid,Revise(submission_id='rc-revise',based_on_version_id=v1,instruction='缩短周期',request=request),user)
   second_run=life.claim(second['run_id'])
   if state=='v2':complete(prepared,second,second_run)
   elif state=='failed_revise':life.finish_failure(second_run['id'],second_run['execution_token'],'model')
   elif state=='interrupted_revise':life.recover(startup=True)
  if state=='archived':life.archive(pid,user)
 archive='archived' if state=='archived' else 'active'
 task_status={'generating':'matching','generation_failed':'failed','available':'ready','archived':'ready'}[expected]
 for actor,url in [(user,'/agent/tasks'),(admin,'/admin/tasks')]:
  response=client.get(url+f'?task_type=development_plan&status={archive}',headers=auth_headers(actor))
  assert response.status_code==200
  row=next(x for x in response.json()['items'] if x['id']==pid)
  p=row['planPresentation']
  assert (p['state'],p['current_version'],p['latest_run_status'])==(expected,current,run_status)
  assert p==views.detail(pid,user)['presentation']
  assert not any('confirmed' in key for key in p)
  assert row['taskStatus']==task_status
  filtered=client.get(url+f'?task_type=development_plan&status={archive}&taskStatus={task_status}',headers=auth_headers(actor)).json()
  assert any(item['id']==pid for item in filtered['items'])
 assert client.get('/agent/tasks',headers=auth_headers(other)).json()['total']==0
 assert client.get('/development/plans/'+pid,headers=auth_headers(other)).status_code==404
 detail=client.get('/development/plans/'+pid,headers=auth_headers(user)).json()
 assert 'confirmed_version_id' not in detail['plan']
 assert plan(pid)['confirmed_version_id']==legacy_pointer
 if current:assert detail['payload'] is not None and len(detail['versions'])==current


def test_revoked_current_does_not_fall_back_to_legacy_confirmed(client,prepared):
 accepted,run=start(prepared);v1=complete(prepared,accepted,run);pid=accepted['plan_id'];legacy_confirmed(pid,v1,prepared[0])
 with get_db() as conn:
  version=dict(conn.execute('SELECT * FROM development_versions WHERE id=?',(v1,)).fetchone())
  version['run_id']=None;version['id']='rc-revoked-version';version['version_no']=2;version['dependency_json']='[{"source_type":"course","source_id":"not-authorized","source_version":1}]'
  keys=list(version);conn.execute(f"INSERT INTO development_versions ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",list(version.values()))
  conn.execute('UPDATE development_plans SET current_version_id=? WHERE id=?',(version['id'],pid))
 detail=views.detail(pid,prepared[0])
 assert detail['presentation']['state']=='available' and detail['presentation']['current_available'] is False
 assert detail['payload'] is None and detail['hidden']
 with pytest.raises(HTTPException) as error:views.transferable(pid,prepared[0])
 assert error.value.status_code==409
 row=client.get('/agent/tasks',headers=auth_headers(prepared[0])).json()['items'][0]
 assert row['planPresentation']==detail['presentation']
 assert row['requirement']=='发展方案（来源授权已变化）'
 assert plan(pid)['confirmed_version_id']==v1
