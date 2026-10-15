"""Prompt/paragraph preservation only, using original effective source snapshot."""
import importlib.util,json,os
from pathlib import Path
import pytest
from backend.app import profile_sources as sources,development_model as model
from backend.app.database import get_db
from backend.tests.conftest import make_user,auth_headers

@pytest.fixture
def captured():
 location=os.environ.get('BANFEI_PROFILE_PARAGRAPH_EVIDENCE_DIR')
 if not location:pytest.skip('Original partner snapshot requires BANFEI_PROFILE_PARAGRAPH_EVIDENCE_DIR.')
 root=Path(location);snapshot=json.loads((root/'BIGU-BEFORE.json').read_text())
 spec=importlib.util.spec_from_file_location('paragraph_snapshot_fixture',root/'snapshot_fixture.py')
 helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
 return root,snapshot,helper

def test_original_sources_merge_once_preserves_paragraphs_and_repeat_zero(client,captured,monkeypatch):
 root,snapshot,helper=captured;admin=make_user('paragraph-admin',role='admin')
 with get_db() as conn:
  pid=helper.seed(conn,snapshot,admin['id'],pending=True)
  native_before=sources.sources(conn,pid)
  source_before=[dict(r) for r in conn.execute('SELECT * FROM partner_profile_sources WHERE partner_id=? ORDER BY source_kind,source_id',(pid,))]
 calls=[];sent_bodies={}
 def complete(config,messages,schema):
  frame=json.loads(messages[-1]['content']);calls.append({'prompt':messages[0]['content'],'input':frame})
  assert schema['title']=='ChapterMerge' and '当前画像' not in frame and 'current_report' not in frame
  assert '段间空行' in messages[0]['content']
  sections=[]
  for chapter in frame['chapters']:
   word=next(row for row in chapter['sources'] if 'body' in row)
   body=word['body']
   if chapter['chapter']==5:
    body='合成产品甲提供能力甲，限定在既有交付范围内。\n\n合成产品乙提供能力乙，可用于合成业务场景。\n\n合成集成服务保留既有实施边界。'
   elif chapter['chapter']==6:
    body='合成案例甲展示已有实践。\n\n合成案例乙提供对应功能；实施范围保持原约定。'
   sent_bodies[str(chapter['chapter'])]=body
   sections.append({'chapter':chapter['chapter'],'body':body,'used_sources':[word['source']]})
  return json.dumps({'sections':sections},ensure_ascii=False)
 monkeypatch.setattr(sources,'resolve_model_record',lambda _: {'api_key':'synthetic-only','base_url':'http://127.0.0.1:1/v1'})
 monkeypatch.setattr(model,'completion',complete)
 response=client.post(f'/partners/{pid}/profile',headers=auth_headers(admin))
 assert response.status_code==200,response.text
 assert len(calls)==1
 inputs={str(c['chapter']):c['sources'] for c in calls[0]['input']['chapters']}
 for n,entries in snapshot['current_inputs'].items():
  assert [{k:v for k,v in row.items() if k!='source'} for row in inputs[n]]==[{k:v for k,v in row.items() if k in ['summary','body','prefix']} for row in entries]
 with get_db() as conn:
  saved=dict(conn.execute('SELECT ai_profile,profile_chapter_meta FROM partners WHERE id=?',(pid,)).fetchone())
  report=sources._saved_report(saved)
  assert report.chapters[4].split('\n\n',1)[1].strip()==sent_bodies['5']
  assert report.chapters[5].split('\n\n',1)[1].strip()==sent_bodies['6']
  assert sources.sources(conn,pid)==native_before
  assert [dict(r) for r in conn.execute('SELECT * FROM partner_profile_sources WHERE partner_id=? ORDER BY source_kind,source_id',(pid,))]==source_before
 repeated=client.post(f'/partners/{pid}/profile',headers=auth_headers(admin))
 assert repeated.status_code==200 and len(calls)==1
 with get_db() as conn:assert dict(conn.execute('SELECT ai_profile,profile_chapter_meta FROM partners WHERE id=?',(pid,)).fetchone())==saved
 (root/'OFFLINE-ONE-MERGE.json').write_text(json.dumps({'actual_prompt_and_inputs':calls,'saved':saved,'logical_mock_calls':1,'repeat_calls':0,'provider_calls':0,'sources_native_fingerprints_unchanged':True,'quality_limit':'Fixed offline output checks newline storage, not real model writing quality.'},ensure_ascii=False,indent=2))

def test_unchanged_original_snapshot_normal_api_is_zero_model(client,captured,monkeypatch):
 _,snapshot,helper=captured;admin=make_user('paragraph-unchanged-admin',role='admin')
 with get_db() as conn:pid=helper.seed(conn,snapshot,admin['id'],pending=False)
 def forbidden(*args,**kwargs):raise AssertionError('No changed inputs; must not call model')
 monkeypatch.setattr(model,'completion',forbidden)
 response=client.post(f'/partners/{pid}/profile',headers=auth_headers(admin))
 assert response.status_code==200,response.text
 with get_db() as conn:
  partner=conn.execute('SELECT ai_profile,profile_chapter_meta FROM partners WHERE id=?',(pid,)).fetchone()
  assert partner['ai_profile']==snapshot['partner']['ai_profile'] and partner['profile_chapter_meta']==snapshot['partner']['profile_chapter_meta']
