"""Source-driven profile contracts on random PostgreSQL schemas and synthetic documents."""
import json
from pathlib import Path
import pytest
from backend.app import profile_sources as sources, profile_report, material_files
from backend.app.database import get_db
from backend.app.partner_match_context import recall_candidates,detailed_candidate
from .conftest import make_partner,make_user,auth_headers
from .support.profile_report_fixture import document

@pytest.fixture
def setup(client,monkeypatch,tmp_path):
    pid=make_partner()['id']
    admin=auth_headers(make_user('source-admin',role='admin'))
    user=auth_headers(make_user('source-reader'))
    calls=[]
    monkeypatch.setattr(sources,'resolve_model_record',lambda _: {})
    def complete(config,messages,schema):
        data=json.loads(messages[-1]['content']);calls.append(data)
        assert 'current_report' not in data and 'intro' not in data
        return json.dumps({'sections':[{'chapter':5,'quotes':[data['material']]}]},ensure_ascii=False)
    monkeypatch.setattr(sources.development_model,'completion',complete)
    def preview(path):
        target=tmp_path/(path.stem+'.pdf');target.write_bytes(b'%PDF-synthetic');return str(target)
    monkeypatch.setattr(material_files,'office_preview',preview)
    return client,admin,user,pid,calls

def upload(setup,name,text,initialize=False):
    c,a,_,pid,_=setup
    data=text if isinstance(text,bytes) else text.encode()
    response=c.post(f'/partners/{pid}/documents',headers=a,files={'file':(name,data)},
                    data={'initialize_profile':str(initialize).lower()})
    assert response.status_code==201,response.text
    return response.json()['id']

def profile(setup,admin=False):
    c,a,u,pid,_=setup
    return c.get(f'/partners/{pid}',headers=a if admin else u).json()

def test_word_initialization_tables_qualifiers_and_user_ten_chapters(setup):
    upload(setup,'initial.docx',document(toc=True),True)
    p=profile(setup)
    assert len(profile_report.parse(p['ai_profile']).chapters)==10
    assert '目录' not in p['ai_profile'] and p['ai_profile'].count('| 字段 | 事实 |')==3
    assert '集团口径，企业自述' in p['ai_profile']
    assert p['profile_status']=='ready' and setup[4]==[]
    assert 'initial.docx' not in json.dumps(p,ensure_ascii=False)
    assert 'initial.docx' in profile(setup,True)['ai_profile']

def test_no_word_never_uses_old_ai_intro_or_summary_and_keeps_tags(setup):
    _,_,_,pid,calls=setup
    with get_db() as conn:
        conn.execute('UPDATE partners SET ai_profile=?,intro=? WHERE id=?',('OBSOLETE_PROFILE_CAPABILITY','OBSOLETE_INTRO_CAPABILITY',pid))
        conn.execute('INSERT INTO app_metadata(key,value) VALUES (?,?)',('partner_match_summary:'+pid,'{"text":"OBSOLETE_SUMMARY_CAPABILITY"}'))
        before=dict(conn.execute('SELECT * FROM partners WHERE id=?',(pid,)).fetchone())
        sources.initialize_cached(conn,pid)
        after=dict(conn.execute('SELECT * FROM partners WHERE id=?',(pid,)).fetchone())
        for field in ('intro','capabilities','industries','service_areas'):assert before[field]==after[field]
        assert recall_candidates(conn,'OBSOLETE_PROFILE_CAPABILITY',{})==[]
        assert recall_candidates(conn,'OBSOLETE_INTRO_CAPABILITY',{})==[]
        assert recall_candidates(conn,'OBSOLETE_SUMMARY_CAPABILITY',{})==[]
    assert 'OBSOLETE_' not in json.dumps(profile(setup),ensure_ascii=False)
    assert profile(setup)['profile_status']=='missing' and calls==[]

def test_material_updates_only_related_chapter_and_hidden_still_recalls(setup):
    upload(setup,'initial.docx',document(),True)
    before=profile_report.parse(profile(setup)['ai_profile']).chapters
    upload(setup,'HIDDEN_SOURCE_NAME.txt','具备QuasarFalcon冷链回退能力；但不支持跨境交付。')
    after=profile_report.parse(profile(setup)['ai_profile']).chapters
    assert all(before[i]==after[i] for i in range(10) if i!=4)
    assert 'QuasarFalcon' in after[4] and '不支持跨境' in after[4]
    assert 'HIDDEN_SOURCE_NAME' not in json.dumps(profile(setup),ensure_ascii=False)
    with get_db() as conn:
        assert recall_candidates(conn,'QuasarFalcon冷链回退',{})[0]['partnerId']==setup[3]
        context=detailed_candidate(conn,setup[3],'QuasarFalcon','QuasarFalcon')[1]
        assert 'QuasarFalcon' in json.dumps(context,ensure_ascii=False)
        assert 'HIDDEN_SOURCE_NAME' not in json.dumps(context,ensure_ascii=False)

def test_delete_unique_and_shared_fact_no_resurrection(setup):
    c,a,_,pid,_=setup
    first=upload(setup,'first.txt','具备DualSourceQuasar能力。')
    second=upload(setup,'second.txt','具备DualSourceQuasar能力。')
    unique=upload(setup,'unique.txt','具备UniqueQuasar能力。')
    assert c.delete(f'/partners/{pid}/documents/{unique}',headers=a).status_code==204
    assert 'UniqueQuasar' not in profile(setup)['ai_profile']
    assert c.delete(f'/partners/{pid}/documents/{first}',headers=a).status_code==204
    assert 'DualSourceQuasar' in profile(setup)['ai_profile']
    assert c.delete(f'/partners/{pid}/documents/{second}',headers=a).status_code==204
    assert 'DualSourceQuasar' not in profile(setup)['ai_profile']
    assert c.post(f'/partners/{pid}/profile',headers=a).status_code==200
    assert 'Quasar' not in profile(setup)['ai_profile']

@pytest.mark.parametrize('action',['replace','delete'])
def test_late_old_contribution_cannot_overwrite_new_source(setup,monkeypatch,action):
    c,a,_,pid,_=setup
    fid=upload(setup,'late.txt','OriginalOldQuasar。')
    with get_db() as conn:
        source=next(s for s in sources.sources(conn,pid) if s['id']==fid)
        sources.put(conn,source,'failed',error='retry synthetic')
    def late(config,messages,schema):
        with get_db() as conn:
            if action=='delete':conn.execute('DELETE FROM partner_documents WHERE id=?',(fid,))
            else:conn.execute('UPDATE partner_documents SET extracted_text=?,file_path=? WHERE id=?',('NewReplacementQuasar。','synthetic-new-version',fid))
            material_files.changed(conn,pid)
        return json.dumps({'sections':[{'chapter':5,'quotes':['OriginalOldQuasar。']}]})
    monkeypatch.setattr(sources.development_model,'completion',late)
    sources.process_partner(pid)
    assert 'OriginalOldQuasar' not in profile(setup)['ai_profile']
    with get_db() as conn:
        assert recall_candidates(conn,'OriginalOldQuasar',{})==[]

def test_replace_same_id_withdraws_previous_contribution(setup):
    c,a,_,pid,_=setup
    fid=upload(setup,'old.txt','OldOnlyQuasar。')
    response=c.put(f'/partners/{pid}/documents/{fid}',headers=a,files={'file':('new.txt','NewOnlyQuasar。'.encode())})
    assert response.status_code==200 and response.json()['id']==fid
    p=profile(setup)
    assert 'OldOnlyQuasar' not in p['ai_profile'] and 'NewOnlyQuasar' in p['ai_profile']

def test_failure_withdraws_old_fact_and_retry_preserves_valid_sources(setup,monkeypatch):
    c,a,_,pid,_=setup
    upload(setup,'initial.docx',document(),True)
    fid=upload(setup,'valid.txt','OldFailedQuasar。')
    def fail(*args):raise TimeoutError('synthetic contribution timeout')
    monkeypatch.setattr(sources.development_model,'completion',fail)
    assert c.put(f'/partners/{pid}/documents/{fid}',headers=a,files={'file':('new.txt','UnprocessedQuasar。'.encode())}).status_code==200
    p=profile(setup)
    assert p['profile_status']=='failed'
    assert 'OldFailedQuasar' not in p['ai_profile'] and 'UnprocessedQuasar' not in p['ai_profile']
    assert '第1章原有完整说明' in p['ai_profile']
    assert c.post(f'/partners/{pid}/profile',headers=a).status_code==502
    assert any(r['state']=='failed' for r in profile(setup,True)['profile_sources'])

def test_hidden_identity_inside_baseline_and_matching_output_is_redacted(setup):
    c,a,_,pid,_=setup
    upload(setup,'initial.docx',document(extra='秘密资料卡 https://hidden.invalid/inside'),True)
    response=c.post('/cases',headers=a,json={'partner_id':pid,'title':'秘密资料卡','description':'具有隐藏案例的ColdRareQuasar业务能力。','category_id':'technical-1'})
    assert response.status_code==201
    text=json.dumps(profile(setup),ensure_ascii=False)
    assert '秘密资料卡' not in text and 'https://hidden.invalid' not in text
    assert 'ColdRareQuasar' in text
    cid=response.json()['id']
    assert c.get(f'/cases/{cid}',headers=setup[2]).status_code==404
    assert c.patch(f'/cases/{cid}/visibility',headers=a,json={'visible':True}).status_code==200
    assert 'ColdRareQuasar' in profile(setup)['ai_profile']

def test_rare_tail_capability_beats_more_than_twelve_distractors(setup):
    c,a,_,pid,_=setup
    upload(setup,'rare.txt','普通业务。'*1400+'\n具备RareTailQuasar能力；但不支持境外交付。')
    for i in range(18):
        other=make_partner('distractor-'+str(i),'常规干扰伙伴'+str(i))
        with get_db() as conn:
            conn.execute('UPDATE partners SET capabilities=? WHERE id=?',('AI,数据治理,普通业务',other['id']))
    with get_db() as conn:
        hits=recall_candidates(conn,'需要RareTailQuasar能力，普通AI业务',{'technicalNeeds':'RareTailQuasar'})
        assert hits[0]['partnerId']==pid and len(hits)<=12
        detail=detailed_candidate(conn,pid,'RareTailQuasar','RareTailQuasar')[1]
        packed=json.dumps(detail,ensure_ascii=False)
        assert 'RareTailQuasar' in packed and '不支持境外交付' in packed


def test_quote_retains_adjacent_negative_and_subject_qualifier():
    text='集团口径，企业自述。\n具备Quasar能力。\n但不支持跨境交付。'
    value=sources.complete_quote(text,'具备Quasar能力。')
    assert '集团口径' in value and '不支持跨境' in value

def test_additive_migration_and_rollback_preserve_legacy_and_sources(setup):
    from backend.app.profile_source_schema import migrate,rollback
    pid=setup[3]
    with get_db() as conn:
        # This table/schema belongs to this test invocation only.
        conn.execute('DROP TABLE partner_profile_sources')
        conn.execute("UPDATE app_metadata SET value='19' WHERE key='schema_version'")
        conn.execute('UPDATE partners SET ai_profile=?,intro=? WHERE id=?',('legacy-output','legacy-intro',pid))
        before=dict(conn.execute('SELECT * FROM partners WHERE id=?',(pid,)).fetchone())
        assert migrate(conn)['schema_version']==20
        sources.initialize_cached(conn,pid)
        assert conn.execute('SELECT intro FROM partners WHERE id=?',(pid,)).fetchone()[0]=='legacy-intro'
        assert rollback(conn)['schema_version']==19
        after=dict(conn.execute('SELECT * FROM partners WHERE id=?',(pid,)).fetchone())
        for field in ('ai_profile','intro','capabilities','industries','service_areas'):assert before[field]==after[field]
        assert migrate(conn)['schema_version']==20
        assert conn.execute("SELECT count(*) FROM app_metadata WHERE key=? ",('profile_source_legacy:'+pid,)).fetchone()[0]==1


def test_hidden_case_title_equal_to_capability_does_not_erase_business_fact(setup):
    c,a,_,pid,_=setup
    response=c.post('/cases',headers=a,json={'partner_id':pid,'title':'稀有冷链回退',
        'description':'具备稀有冷链回退能力；但不支持境外交付。','category_id':'technical-1'})
    assert response.status_code==201
    with get_db() as conn:
        context=detailed_candidate(conn,pid,'稀有冷链回退','稀有冷链回退')[1]
        assert '具备稀有冷链回退能力' in json.dumps(context,ensure_ascii=False)
    assert '具备稀有冷链回退能力' in profile(setup)['ai_profile']
    assert '案例：稀有冷链回退' not in sources.redact_sources('案例：稀有冷链回退',['稀有冷链回退'])
    assert sources.redact_sources('依据稀有冷链回退能力进行判断',['稀有冷链回退'])=='依据稀有冷链回退能力进行判断'

def test_original_chapter_ten_disclaimer_dates_survive_public_projection(setup):
    c,a,_,pid,_=setup
    upload(setup,'baseline.docx',document(),True)
    text=profile(setup)['ai_profile']
    chapter=profile_report.parse(text).chapters[9]
    assert '第10章原有完整说明' in chapter
    assert '来源日期2026-09-24，集团口径，企业自述' in chapter
    assert 'baseline.docx' not in chapter
