"""Standards, legacy retention and UPDATE-only repair: all records are synthetic /tmp data."""
import json
import sqlite3
import socket
import pytest
from backend.app.business_taxonomy import (STANDARD, INDUSTRIES, REGION_TYPES, ClassificationInput, canonical,
    classify, project_partner, taxonomy_prompt)
from backend.app.database import DATABASE_PATH, get_db
from backend.app.development_engine import profile_context
from backend.app.routers.demand import _count_tags, standard_filter
from scripts.normalize_business_taxonomy import plan, state, checks, update_transaction, run
from .conftest import make_partner, make_user, auth_headers

@pytest.fixture(autouse=True)
def forbid_external_calls(monkeypatch):
    def deny(*args,**kwargs): raise AssertionError('No socket/model call permitted')
    monkeypatch.setattr(socket.socket,'connect',deny)
    from backend.app import ai_client
    monkeypatch.setattr(ai_client,'chat_completion',deny)

@pytest.mark.parametrize('value,kind,expected,pending',[
 ('银行,保险,证券,金融','industry','金融',[]),
 ('电商,文娱','industry','互联网',[]),
 ('深圳,广州,西安,杭州','region','广东,陕西,浙江',[]),
 ('北京,广东,亚太,欧洲','region','北京,广东,亚太,欧洲',[]),
 ('全国,华东,海外地区,俄罗斯','region','',['全国','华东','海外地区','俄罗斯']),
 ('政务,通信,文旅,金融','industry','金融',['政务','通信','文旅']),
])
def test_deterministic_and_pending(value,kind,expected,pending):
 assert canonical(value,kind)==expected
 assert classify(value,kind)[1]==pending

def test_one_authoritative_dictionary():
 from pathlib import Path
 root=Path(__file__).resolve().parents[2]
 assert json.loads((root/'shared/business-taxonomy.json').read_text())==STANDARD
 assert '../../shared/business-taxonomy.json' in (root/'frontend/components/business-taxonomy.tsx').read_text()
 assert len(INDUSTRIES)==12 and len(REGION_TYPES['overseas'])==6 and len(REGION_TYPES['domestic'])==34
 assert '深圳' not in REGION_TYPES['domestic'] and '银行' not in INDUSTRIES
 for item in INDUSTRIES+REGION_TYPES['overseas']:assert item in taxonomy_prompt()

@pytest.mark.parametrize('body',[
 {'industries':'银行'},{'service_areas':'深圳'},{'service_areas':'全国'},
 {'region_groups':[{'region_type':'overseas','regions':['广东']}]},
 {'region_groups':[{'region_type':'domestic','regions':['广东']}],'service_areas':'陕西'},
])
def test_write_rejects_nonstandard(client,body):
 admin=make_user('taxonomy-admin',role='admin')
 response=client.post('/partners',headers=auth_headers(admin),json={'name':'合成标准验证',**body})
 assert response.status_code==422

def test_multiselect_admin_write_and_legacy_retention(client):
 admin=make_user('taxonomy-admin',role='admin');user=make_user('taxonomy-user')
 body={'name':'合成标准验证','industries':['互联网','金融'],'region_groups':[
 {'region_type':'domestic','regions':['广东','陕西']},{'region_type':'overseas','regions':['亚太','欧洲']}]}
 assert client.post('/partners',headers=auth_headers(user),json=body).status_code==403
 r=client.post('/partners',headers=auth_headers(admin),json=body);assert r.status_code==201,r.text
 data=r.json();assert data['service_areas']=='广东,陕西,亚太,欧洲' and data['industries']=='互联网,金融'
 with get_db() as conn:conn.execute("UPDATE partners SET industries='银行,政务',service_areas='深圳,全国' WHERE id=?",(data['id'],))
 detail=client.get('/partners/'+data['id'],headers=auth_headers(user)).json()
 assert detail['industries']=='金融' and detail['service_areas']=='广东'
 assert detail['classification_pending']=={'industries':['政务'],'regions':['全国']}
 r=client.put('/partners/'+data['id'],headers=auth_headers(admin),json={'industries':['金融','零售'],'service_areas':['广东','欧洲']})
 assert r.status_code==200
 with get_db() as conn:
  row=conn.execute('SELECT industries,service_areas FROM partners WHERE id=?',(data['id'],)).fetchone()
 assert tuple(row)==('金融,零售,政务','广东,欧洲,全国')

def test_model_structured_projection_leaves_narrative():
 p=make_partner()
 with get_db() as conn:
  conn.execute("UPDATE partners SET industries='银行,政务',service_areas='深圳,全国',ai_profile='长期深耕深圳银行业务' WHERE id=?",(p['id'],))
  ctx=profile_context(conn,{'target_partner_id':p['id'],'model_input_allowed':True})
 assert ctx['industries']=='金融' and ctx['service_areas']=='广东'
 assert ctx['region_groups']==[{'region_type':'domestic','regions':['广东']}]
 assert ctx['ai_profile']=='长期深耕深圳银行业务'
 assert 'classification_pending' not in ctx

def test_stats_and_filter_only_canonical_values():
 rows=[{'industry_tags':'银行,金融,政务','region_tags':'深圳,广州,全国'}, {'industry_tags':'电商','region_tags':'亚太'}]
 assert _count_tags(rows,'industry_tags')=={'金融':1,'互联网':1}
 assert _count_tags(rows,'region_tags')=={'广东':1,'亚太':1}
 assert len(standard_filter(rows,'金融,互联网','广东','industry_tags','region_tags'))==1

@pytest.mark.parametrize('fault',[1,2,None])
def test_update_only_atomic_rollback_and_no_data_loss(fault):
 make_partner()
 with get_db() as conn:
  conn.execute("UPDATE partners SET industries='银行,政务',service_areas='深圳,广州,全国',ai_profile='深圳银行案例' WHERE id='partner-1'")
 conn=sqlite3.connect(DATABASE_PATH,isolation_level=None)
 try:
  before=state(conn);other=state(conn,True);baseline=checks(conn);changes,pending=plan(conn)
  assert len(changes)==2 and pending
  if fault:
   with pytest.raises(RuntimeError,match='Synthetic'):update_transaction(conn,changes,before,fault)
   assert state(conn)==before
  else:
   update_transaction(conn,changes,before)
   assert conn.execute("SELECT industries,service_areas,ai_profile FROM partners").fetchone()==('金融,政务','广东,全国','深圳银行案例')
   assert not plan(conn)[0]
  assert checks(conn)==baseline and state(conn,True)==other
 finally:conn.close()

def test_dry_run_and_consistent_backup():
 make_partner()
 with get_db() as conn:conn.execute("UPDATE partners SET industries='保险',service_areas='西安'")
 before=DATABASE_PATH.read_bytes();dry=run(DATABASE_PATH)
 assert dry['updates'] and DATABASE_PATH.read_bytes()==before
 result=run(DATABASE_PATH,True)
 with sqlite3.connect(result['backup']) as snap:
  assert snap.execute('SELECT industries,service_areas FROM partners').fetchone()==('保险','西安')
 assert result['checks_after']==result['checks_before']
 assert all(result['before'][t]['count']==result['after'][t]['count'] for t in result['before'])

@pytest.mark.parametrize('path',['/home/yuan/project/lingjian-agent/data/app.db','/home/yuan/project/lingjian-agent-enablement/.isolation/runtime/app.db'])
def test_protected_database_refused(path):
 with pytest.raises(ValueError,match='Only'):run(path,True)
