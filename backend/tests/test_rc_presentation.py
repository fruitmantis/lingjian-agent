"""RC presentation: real lifecycle transitions and authorized API projections."""
import pytest
from backend.app import development_lifecycle as life,development_views as views
from backend.app.database import get_db
from backend.app.development_types import Revise
from backend.tests.conftest import auth_headers
from backend.tests.test_development_lifecycle import prepared,start,complete,plan

@pytest.mark.parametrize('state,expected,current,confirmed,run_status',[
 ('first_failed','generation_failed',None,None,'failed'),
 ('generating','generating',None,None,'running'),
 ('draft','draft',1,None,'ready'),
 ('confirmed','available',1,1,'ready'),
 ('v2_draft','available',2,1,'ready'),
 ('failed_revise','available',1,1,'failed'),
 ('interrupted_revise','available',1,1,'interrupted'),
 ('archived','archived',1,1,'ready'),
])
def test_plan_availability_separate_from_run(client,prepared,state,expected,current,confirmed,run_status):
 user,other,admin,request=prepared
 accepted,run=start(prepared);pid=accepted['plan_id']
 if state=='first_failed':life.finish_failure(run['id'],run['execution_token'],'model')
 elif state!='generating':
  v1=complete(prepared,accepted,run)
  if state!='draft':life.confirm(pid,v1,user)
  if state in ('v2_draft','failed_revise','interrupted_revise'):
   second=life.revise(pid,Revise(submission_id='rc-revise',based_on_version_id=v1,instruction='缩短周期',request=request),user)
   second_run=life.claim(second['run_id'])
   if state=='v2_draft':complete(prepared,second,second_run)
   elif state=='failed_revise':life.finish_failure(second_run['id'],second_run['execution_token'],'model')
   else:life.recover(startup=True)
  if state=='archived':life.archive(pid,user)
 archive='archived' if state=='archived' else 'active'
 for actor,url in [(user,'/agent/tasks'),(admin,'/admin/tasks')]:
  response=client.get(url+f'?task_type=development_plan&status={archive}',headers=auth_headers(actor))
  assert response.status_code==200
  row=next(x for x in response.json()['items'] if x['id']==pid)
  p=row['planPresentation']
  assert (p['state'],p['current_version'],p['confirmed_version'],p['latest_run_status'])==(expected,current,confirmed,run_status)
  assert p==views.detail(pid,user)['presentation']
  if state in ('failed_revise','interrupted_revise'):
   assert row['taskStatus']=='failed' # Existing execution/filter contract stays true.
   assert p['state']=='available' and p['confirmed_available']
 assert client.get('/agent/tasks',headers=auth_headers(other)).json()['total']==0
 assert client.get('/development/plans/'+pid,headers=auth_headers(other)).status_code==404
 detail=client.get('/agent/tasks/'+pid,headers=auth_headers(user))
 assert detail.status_code==200 and detail.json()['planPresentation']==p


def test_revoked_version_not_presented_as_available(client,prepared):
 accepted,run=start(prepared);v1=complete(prepared,accepted,run);pid=accepted['plan_id'];life.confirm(pid,v1,prepared[0])
 # A missing dependency is denied by the same read-time guard, without changing snapshots.
 with get_db() as conn:
  # Use a new fixture version instead of mutating an immutable production snapshot.
  version=dict(conn.execute('SELECT * FROM development_versions WHERE id=?',(v1,)).fetchone())
  version['run_id']=None;version['id']='rc-revoked-version';version['version_no']=2;version['dependency_json']='[{"source_type":"case","source_id":"not-authorized","source_version":1}]'
  keys=list(version);conn.execute(f"INSERT INTO development_versions ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",list(version.values()))
  conn.execute('UPDATE development_plans SET current_version_id=?,confirmed_version_id=? WHERE id=?',(version['id'],version['id'],pid))
 assert views.detail(pid,prepared[0])['presentation']['state']=='restricted'
 row=client.get('/agent/tasks',headers=auth_headers(prepared[0])).json()['items'][0]
 assert row['planPresentation']['state']=='restricted'
 assert row['planPresentation']['confirmed_available'] is False
