"""Current authorization is reapplied even after stop/regrant of historical references."""
from backend.tests.support.legacy_development import legacy_confirmed
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
    items=[i for s in payload['stages'] for i in s['items']];assert bool(items)==(flags[0] and flags[1])
    v1=plan(accepted['plan_id'])['current_version_id'];legacy_confirmed(accepted['plan_id'],v1,user)
    external=views.transferable(accepted['plan_id'],user)['text']
    assert ('数据库课程' in external)==all(flags)
    assert CANARY not in external


@pytest.mark.parametrize('action',['hide','delete'])
def test_case_hide_or_delete_preserves_task_prose_and_disables_links(scenario,client,action):
    user,_,admin,request=scenario[0]
    with get_db() as conn:
        conn.execute("UPDATE cases SET title='数据库案例',description='数据库迁移的合成方法',category_id='technical-1',visible=1,updated_at='2026-09-25' WHERE id='secret-case'")
    accepted,run,payload=execute(scenario);assert run['status']=='ready'
    pid=accepted['plan_id'];v1=plan(pid)['current_version_id']
    with get_db() as conn: before=tuple(conn.execute('SELECT payload_json,dependency_json FROM development_versions WHERE id=?',(v1,)).fetchone())
    if action=='hide':
        assert client.patch('/cases/secret-case/visibility',headers=auth_headers(admin),json={'visible':False}).status_code==200
    else:
        assert client.delete('/cases/secret-case',headers=auth_headers(admin)).status_code==204
    assert not views.detail(pid,user)['hidden']
    for path in ['/enablement/resources/case/secret-case','/enablement/context?case_id=secret-case']:
        assert client.get(path,headers=auth_headers(user)).status_code==404
    with get_db() as conn:
        assert not any(r['source_type']=='case' for r in engine.candidates(conn,request.model_dump(),payload['diagnoses']))
        assert tuple(conn.execute('SELECT payload_json,dependency_json FROM development_versions WHERE id=?',(v1,)).fetchone())==before
    if action=='hide':
        client.patch('/cases/secret-case/visibility',headers=auth_headers(admin),json={'visible':True})
        assert client.get('/enablement/resources/case/secret-case',headers=auth_headers(user)).status_code==200
        assert not views.detail(pid,user,version_id=v1)['hidden']


def test_ordinary_course_unpublish_retains_name_but_disables_redirect_and_future_pool(scenario,client):
    user,_,admin,request=scenario[0];accepted,_,payload=execute(scenario);pid=accepted['plan_id'];v1=plan(pid)['current_version_id'];legacy_confirmed(pid,v1,user)
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
