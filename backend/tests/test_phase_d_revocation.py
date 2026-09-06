"""Current authorization is reapplied even after stop/regrant of historical references."""
import itertools
import json
import pytest
from fastapi import HTTPException
from backend.app import development_engine as engine, development_lifecycle as life, development_views as views, enablement
from backend.app.development_types import Submit, Revise
from backend.app.database import get_db
from backend.tests.test_development_engine import scenario, execute, CANARY
from backend.tests.test_development_lifecycle import prepared, plan
from backend.tests.test_enablement import grant,published
from backend.tests.conftest import auth_headers


@pytest.mark.parametrize('flags',list(itertools.product((False,True),repeat=3)))
def test_plan_candidate_and_transfer_dimensions(scenario,flags):
    user,_,admin,request=scenario[0]
    row=enablement.detail('resource','test-course')
    row=published(grant(row,admin,flags=flags),admin)
    accepted,run,payload=execute(scenario);assert run['status']=='ready'
    items=payload['stages'][0]['items'];assert bool(items)==(flags[0] and flags[1])
    v1=plan(accepted['plan_id'])['current_version_id'];views.confirm(accepted['plan_id'],v1,user)
    external=views.transferable(accepted['plan_id'],user)['text']
    assert ('数据库课程' in external)==all(flags)
    assert CANARY not in external


@pytest.mark.parametrize('sensitive',[False,True])
def test_case_stop_regrant_does_not_restore_old_plan_and_revision_uses_new_pool(scenario,client,sensitive):
    user,_,admin,request=scenario[0]
    metadata=enablement.ShareMetadata(title='受控共享案例',summary='获准共享的合成方法',methods='逐项核验',contributor_role='实施',source_platform='合成',source_url='https://example.com/case',capability_tag_ids=[request.targets[0].capability_tag_id])
    row=enablement.save('case','secret-case',enablement.ShareSave(base_revision=0,metadata=metadata),admin['id']);row=published(grant(row,admin,'case'),admin,'case')
    accepted,_,payload=execute(scenario);pid=accepted['plan_id'];v1=plan(pid)['current_version_id'];views.confirm(pid,v1,user)
    with get_db() as conn:before=conn.execute('SELECT payload_json,dependency_json FROM development_versions WHERE id=?',(v1,)).fetchone();before=tuple(before)
    row=enablement.unpublish('case','secret-case',enablement.Unpublish(base_revision=row['revision'],reason='合成授权撤回',sensitive=sensitive),admin['id'])
    current=views.detail(pid,user);assert current['hidden'] and '重新生成' in current['notice']
    for path in ['/enablement/resources/case/secret-case','/enablement/context?case_id=secret-case']:
        assert client.get(path,headers=auth_headers(user)).status_code==404
    with pytest.raises(HTTPException):views.transferable(pid,user,expected=v1,copy_event=True)
    with get_db() as conn:
        assert not any(r['source_type']=='case' for r in engine.candidates(conn,request.model_dump(),payload['diagnoses']))
    # A real revise after withdrawal must not reuse the old case or its free text.
    next_run=life.revise(pid,Revise(submission_id='revise-without-withdrawn-case',based_on_version_id=v1,instruction='调整资源',request=request),user)
    scenario[1].clear();engine.execute(next_run['run_id'])
    assert 'secret-case' not in json.dumps(scenario[1]) and CANARY not in json.dumps(scenario[1])
    assert views.detail(pid,user)['runs'][0]['status']=='ready'
    assert plan(pid)['confirmed_version_id']==v1
    # Re-publication creates a new shared version; it must not resurrect the old plan snapshot.
    row=published(grant(row,admin,'case'),admin,'case')
    old=views.detail(pid,user,version_id=v1);assert old['hidden']
    with pytest.raises(HTTPException):views.transferable(pid,user,expected=v1,copy_event=True)
    with get_db() as conn:
        assert tuple(conn.execute('SELECT payload_json,dependency_json FROM development_versions WHERE id=?',(v1,)).fetchone())==before
        assert row['published_version']==2


def test_ordinary_course_unpublish_retains_name_but_disables_redirect_and_future_pool(scenario,client):
    user,_,admin,request=scenario[0];accepted,_,payload=execute(scenario);pid=accepted['plan_id'];v1=plan(pid)['current_version_id'];views.confirm(pid,v1,user)
    with get_db() as conn:before=conn.execute('SELECT payload_json FROM development_versions WHERE id=?',(v1,)).fetchone()[0]
    row=enablement.detail('resource','test-course')
    enablement.unpublish('resource','test-course',enablement.Unpublish(base_revision=row['revision'],reason='普通下架'),admin['id'])
    current=views.detail(pid,user);item=current['payload']['stages'][0]['items'][0]
    assert item['title']=='数据库课程' and item['availability']=='unavailable'
    response=client.post('/enablement/resources/course/test-course/redirect',headers=auth_headers(user),json={'source_version':1})
    assert response.status_code==404 and 'https://' not in response.text
    assert '数据库课程' not in views.transferable(pid,user)['text']
    with get_db() as conn:
        assert not engine.candidates(conn,request.model_dump(),payload['diagnoses'])
        assert conn.execute('SELECT payload_json FROM development_versions WHERE id=?',(v1,)).fetchone()[0]==before
