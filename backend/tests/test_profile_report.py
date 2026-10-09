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
        if 'material' not in data:return json.dumps(merge_result(data),ensure_ascii=False)
        return json.dumps({'sections':[{'chapter':5,'summary':data['material'],'quotes':[data['material']]}]},ensure_ascii=False)
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

def merge_result(data):
    """Offline model stub; explicit source refs, no application processing side effects."""
    result=[]
    for chapter in data['chapters']:
        entries=chapter['sources']
        bodies=list(dict.fromkeys(row.get('summary',row.get('body','')) for row in entries))
        result.append({'chapter':chapter['chapter'],'body':'\n\n'.join(bodies) or profile_report.MISSING,
                       'used_sources':[{key:row[key] for key in ('kind','id','version')} for row in entries]})
    return {'sections':result}

def organize(setup):
    c,a,_,pid,_=setup
    response=c.post(f'/partners/{pid}/profile',headers=a)
    assert response.status_code==200,response.text
    return response.json()

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
    assert profile_report.parse(profile(setup)['ai_profile']).chapters==before
    assert profile(setup)['profile_needs_update']
    organize(setup)
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
    organize(setup)
    assert c.delete(f'/partners/{pid}/documents/{unique}',headers=a).status_code==204
    assert 'UniqueQuasar' not in profile(setup)['ai_profile']
    assert c.delete(f'/partners/{pid}/documents/{first}',headers=a).status_code==204
    assert sources.CHANGED in profile(setup)['ai_profile']
    organize(setup)
    assert 'DualSourceQuasar' in profile(setup)['ai_profile']
    assert c.delete(f'/partners/{pid}/documents/{second}',headers=a).status_code==204
    assert 'DualSourceQuasar' not in profile(setup)['ai_profile']
    assert c.post(f'/partners/{pid}/profile',headers=a).status_code==200
    assert 'Quasar' not in profile(setup)['ai_profile']

@pytest.mark.parametrize('action',['replace','delete'])
def test_late_old_contribution_cannot_overwrite_new_source(setup,monkeypatch,action):
    c,a,_,pid,_=setup
    fid=upload(setup,'late.txt','OriginalOldQuasar。')
    organize(setup)
    with get_db() as conn:
        source=next(s for s in sources.sources(conn,pid) if s['id']==fid)
        sources.put(conn,source,'failed',error='retry synthetic')
    def late(config,messages,schema):
        with get_db() as conn:
            if action=='delete':conn.execute('DELETE FROM partner_documents WHERE id=?',(fid,))
            else:conn.execute('UPDATE partner_documents SET extracted_text=?,file_path=? WHERE id=?',('NewReplacementQuasar。','synthetic-new-version',fid))
            material_files.changed(conn,pid)
        return json.dumps({'sections':[{'chapter':5,'summary':'OriginalOldQuasar。','quotes':['OriginalOldQuasar。']}]})
    monkeypatch.setattr(sources.development_model,'completion',late)
    sources.process_source(pid,'document',fid)
    assert 'OriginalOldQuasar' not in profile(setup)['ai_profile']
    with get_db() as conn:
        assert recall_candidates(conn,'OriginalOldQuasar',{})==[]

def test_replace_same_id_withdraws_previous_contribution(setup):
    c,a,_,pid,_=setup
    fid=upload(setup,'old.txt','OldOnlyQuasar。')
    organize(setup)
    response=c.put(f'/partners/{pid}/documents/{fid}',headers=a,files={'file':('new.txt','NewOnlyQuasar。'.encode())})
    assert response.status_code==200 and response.json()['id']==fid
    assert 'OldOnlyQuasar' not in profile(setup)['ai_profile']
    organize(setup)
    p=profile(setup)
    assert 'OldOnlyQuasar' not in p['ai_profile'] and 'NewOnlyQuasar' in p['ai_profile']

def test_failure_withdraws_old_fact_and_retry_preserves_valid_sources(setup,monkeypatch):
    c,a,_,pid,_=setup
    upload(setup,'initial.docx',document(),True)
    fid=upload(setup,'valid.txt','OldFailedQuasar。')
    organize(setup)
    def fail(*args):raise TimeoutError('synthetic contribution timeout')
    monkeypatch.setattr(sources.development_model,'completion',fail)
    assert c.put(f'/partners/{pid}/documents/{fid}',headers=a,files={'file':('new.txt','UnprocessedQuasar。'.encode())}).status_code==200
    p=profile(setup)
    assert p['profile_status']=='failed'
    assert 'OldFailedQuasar' not in p['ai_profile'] and 'UnprocessedQuasar' not in p['ai_profile']
    assert '第1章原有完整说明' in p['ai_profile']
    assert c.post(f'/partners/{pid}/profile',headers=a).status_code==502
    assert c.post(f'/partners/{pid}/documents/{fid}/retry',headers=a).status_code==200
    assert any(r['state']=='failed' for r in profile(setup,True)['profile_sources'])

def test_hidden_identity_inside_baseline_and_matching_output_is_redacted(setup):
    c,a,_,pid,_=setup
    upload(setup,'initial.docx',document(extra='秘密资料卡 https://hidden.invalid/inside'),True)
    response=c.post('/cases',headers=a,json={'partner_id':pid,'title':'秘密资料卡','description':'具有隐藏案例的ColdRareQuasar业务能力。','category_id':'technical-1'})
    assert response.status_code==201
    organize(setup)
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
    organize(setup)
    assert '具备稀有冷链回退能力' in profile(setup)['ai_profile']
    assert '案例：稀有冷链回退' not in sources.redact_sources('案例：稀有冷链回退',['稀有冷链回退'])
    assert sources.redact_sources('依据稀有冷链回退能力进行判断',['稀有冷链回退'])=='依据稀有冷链回退能力进行判断'

def test_chapter_ten_has_only_sources_and_factual_dates_stay_in_body(setup):
    c,a,_,pid,_=setup
    upload(setup,'baseline.docx',document(),True)
    text=profile(setup)['ai_profile']
    chapter=profile_report.parse(text).chapters[9]
    assert '## 10. 数据来源' in chapter and '免责声明' not in text
    assert '第10章原有完整说明' not in chapter
    assert '来源日期2026-09-24，集团口径，企业自述' in text
    assert '原件和未展示资料' not in text
    assert 'baseline.docx' not in chapter

@pytest.mark.parametrize('invalid_quote',[
    '具备SyntheticQuasar能力。\n预测模型',
    '已为药物研发客户交付SyntheticQuasar项目。',
])
def test_nonliteral_model_quotes_fail_without_changing_original_or_valid_word(setup,monkeypatch,invalid_quote):
    c,a,_,pid,_=setup
    upload(setup,'original.docx',document(),True)
    original='企业自述，尚未交付。\n具备SyntheticQuasar能力。\n研发设计\n制造生产\n预测模型'
    monkeypatch.setattr(sources.development_model,'completion',
        lambda *_args:json.dumps({'sections':[{'chapter':5,'summary':'SyntheticQuasar，企业自述尚未交付。','quotes':[invalid_quote]}]},ensure_ascii=False))
    fid=upload(setup,'strict.txt',original)
    with get_db() as conn:
        row=conn.execute('SELECT file_path,extracted_text,processing_status FROM partner_documents WHERE id=?',(fid,)).fetchone()
        assert row['extracted_text']==original and row['processing_status']=='ready'
        assert Path(row['file_path']).read_text()==original
        contribution=conn.execute("SELECT state,error FROM partner_profile_sources WHERE source_kind='document' AND source_id=?",(fid,)).fetchone()
        assert contribution['state']=='failed' and contribution['error']=='贡献缺少原文依据'
    current=profile(setup)
    assert current['profile_status']=='failed'
    assert 'SyntheticQuasar' not in current['ai_profile']
    assert '第1章原有完整说明' in current['ai_profile']


def test_failed_source_retries_cached_text_once_without_resending_successful_source(setup,monkeypatch):
    c,a,_,pid,_=setup
    upload(setup,'original.docx',document(),True)
    upload(setup,'ready.txt','AlreadyReadySyntheticQuasar。')
    original='企业自述，尚未交付。\nOriginalFailedSyntheticQuasar。'
    calls=[]
    def failed(_config,messages,_schema):
        calls.append(json.loads(messages[-1]['content'])['material'])
        return json.dumps({'sections':[{'chapter':5,'summary':'InventedSyntheticQuasar。','quotes':['InventedSyntheticQuasar。']}]})
    monkeypatch.setattr(sources.development_model,'completion',failed)
    fid=upload(setup,'retry.txt',original)
    with get_db() as conn:
        before=dict(conn.execute('SELECT * FROM partner_documents WHERE id=?',(fid,)).fetchone())
    def ready(_config,messages,_schema):
        data=json.loads(messages[-1]['content'])
        if 'material' not in data:return json.dumps(merge_result(data))
        material=data['material'];calls.append(material)
        return json.dumps({'sections':[{'chapter':5,'summary':material,'quotes':[material]}]})
    monkeypatch.setattr(sources.development_model,'completion',ready)
    response=c.post(f'/partners/{pid}/profile',headers=a)
    assert response.status_code==200 and response.json()['profile_status']=='failed'
    assert calls==[original]
    assert c.post(f'/partners/{pid}/documents/{fid}/retry',headers=a).status_code==200
    assert profile(setup)['profile_status']=='ready'
    assert calls==[original,original]
    assert c.post(f'/partners/{pid}/profile',headers=a).status_code==200
    assert calls==[original,original]
    with get_db() as conn:
        after=dict(conn.execute('SELECT * FROM partner_documents WHERE id=?',(fid,)).fetchone())
        for key in ('file_path','extracted_text','processed_at','created_at'):
            assert before[key]==after[key]
    assert Path(after['file_path']).read_text()==original
    assert 'AlreadyReadySyntheticQuasar' in profile(setup)['ai_profile']
    assert '尚未交付' in profile(setup)['ai_profile']
    assert 'InventedSyntheticQuasar' not in profile(setup)['ai_profile']


@pytest.mark.parametrize('quote',[
    '集团口径，企业自述，尚未交付。\n\n具备SyntheticQuasar能力。',
    '集团口径，企业自述，尚未交付。具备SyntheticQuasar能力。',
])
def test_linebreak_quotes_save_native_complete_context(setup,monkeypatch,quote):
    original='### 当前能力\n集团口径，企业自述，尚未交付。\n具备SyntheticQuasar能力。\n\n仅限当前版本，不支持境外交付。'
    monkeypatch.setattr(sources.development_model,'completion',
        lambda *_args:json.dumps({'sections':[{'chapter':5,'summary':'SyntheticQuasar内部能力，尚未交付，仅限当前版本。','quotes':[quote]}]},ensure_ascii=False))
    fid=upload(setup,'linebreak.txt',original)
    with get_db() as conn:
        row=conn.execute("SELECT state,sections_json FROM partner_profile_sources WHERE source_id=?",(fid,)).fetchone()
        assert row['state']=='ready'
        quotes=json.loads(row['sections_json'])[0]['quotes']
        assert all(q in original for q in quotes)
        assert '### 当前能力' in quotes[0] and '尚未交付' in quotes[0] and '不支持境外交付' in quotes[0]
        assert conn.execute('SELECT extracted_text FROM partner_documents WHERE id=?',(fid,)).fetchone()[0]==original


@pytest.mark.parametrize('quote',['CodeArts产品，仅限试验。','CodeArts 产品，仅限实验。','CodeArts\t产品，仅限试验。'])
def test_non_linebreak_character_changes_are_not_repaired(quote):
    text='CodeArts 产品，仅限试验。'
    valid,rejected=sources.validated_sections(text,[{'chapter':5,'quotes':[quote]}])
    assert not valid and rejected[0]['reason']=='nonliteral_quote'


def test_rejected_restriction_quarantines_same_source_group_across_chapters(setup,monkeypatch):
    text=('### 事实甲\n企业自述，具备SyntheticQuasar能力。\n'
          '仅限集团内部验证，不提供对外已交付证明。\n\n'
          '### 独立事实乙\n企业自述，具备IndependentFalcon能力。\n仅限当前版本。')
    raw={'sections':[
        {'chapter':5,'summary':'IndependentFalcon，仅限当前版本。','quotes':['企业自述，具备SyntheticQuasar能力。','企业自述，具备IndependentFalcon能力。']},
        {'chapter':8,'summary':'SyntheticQuasar，内部实践。','quotes':['企业自述，具备SyntheticQuasar能力。']},
        {'chapter':9,'summary':'仅限内部。','quotes':['仅限集团外部验证，不提供对外已交付证明。']} ]}
    default_completion=sources.development_model.completion
    monkeypatch.setattr(sources.development_model,'completion',lambda *_args:json.dumps(raw,ensure_ascii=False))
    fid=upload(setup,'mixed.txt',text)
    with get_db() as conn:
        row=conn.execute('SELECT state,error,sections_json FROM partner_profile_sources WHERE source_id=?',(fid,)).fetchone()
        assert row['state']=='ready' and '已舍弃' in row['error']
        quotes=[q for sec in json.loads(row['sections_json']) for q in sec['quotes']]
        assert quotes and all(q in text for q in quotes)
        assert not any('SyntheticQuasar' in q for q in quotes)
        assert any('IndependentFalcon' in q and '仅限当前版本' in q for q in quotes)
    monkeypatch.setattr(sources.development_model,'completion',default_completion)
    organize(setup)
    assert 'SyntheticQuasar' not in profile(setup)['ai_profile']
    assert 'IndependentFalcon' in profile(setup)['ai_profile']


def test_repeated_quote_keeps_all_literal_contexts_without_choosing_position():
    text='### 规划范围\n具备RepeatedQuasar能力。\n仅限规划，尚未交付。\n\n### 当前范围\n具备RepeatedQuasar能力。\n仅限内部验证。'
    valid,rejected=sources.validated_sections(text,[{'chapter':5,'quotes':['具备RepeatedQuasar能力。']}])
    quotes=valid[0]['quotes']
    assert not rejected and len(quotes)==2 and all(q in text for q in quotes)
    assert any('尚未交付' in q for q in quotes)
    assert any('仅限内部验证' in q for q in quotes)


def test_empty_rejected_quote_does_not_discard_independent_native_fact():
    text='企业自述，具备IndependentFalcon能力。仅限当前版本。'
    valid,rejected=sources.validated_sections(text,[{'chapter':5,'quotes':['',text]}])
    assert valid[0]['quotes']==[text] and len(rejected)==1


def test_short_rejected_restriction_drops_its_fact_in_other_chapter_only():
    text='### 事实甲\n具备ShortQuasar能力。\n仅限内部。\n\n### 独立事实乙\n具备IndependentFalcon能力。'
    valid,rejected=sources.validated_sections(text,[
        {'chapter':5,'quotes':['具备ShortQuasar能力。','具备IndependentFalcon能力。']},
        {'chapter':9,'quotes':['仅限外部。']}])
    quotes=[q for sec in valid for q in sec['quotes']]
    assert quotes and all(q in text for q in quotes)
    assert not any('ShortQuasar' in q for q in quotes)
    assert any('IndependentFalcon' in q for q in quotes)
    assert any(r['reason']=='rejected_fact_group' and r['chapter']==5 for r in rejected)


def test_native_heading_does_not_become_previous_fact_restriction():
    text='已交付Falcon系统。\n\n规划能力（尚未交付）：\n具备Quasar能力。'
    valid,rejected=sources.validated_sections(text,[{'chapter':5,'quotes':['已交付Falcon系统。']}])
    quotes=valid[0]['quotes']
    assert not rejected and quotes and all(q in text for q in quotes)
    assert all('规划' not in q and 'Quasar' not in q for q in quotes)


def test_shared_restriction_does_not_link_independent_fact_to_rejected_quote(setup,monkeypatch):
    text=('### 事实甲\n具备Quasar能力。\n仅限内部验证，不提供外部已交付证明。\n\n'
          '### 独立事实乙\n具备Falcon能力。\n仅限内部验证，不提供外部已交付证明。')
    raw={'sections':[{'chapter':5,'summary':'Falcon，仅限内部验证。','quotes':['具备Quasar能力。','具备Falcon能力。']},
        {'chapter':9,'summary':'仅限内部验证。','quotes':['具备Quasar能力。\n仅限外部验证，不提供外部已交付证明。']}]}
    monkeypatch.setattr(sources.development_model,'completion',lambda *_args:json.dumps(raw,ensure_ascii=False))
    fid=upload(setup,'shared-restriction.txt',text)
    with get_db() as conn:
        row=conn.execute('SELECT state,sections_json FROM partner_profile_sources WHERE source_id=?',(fid,)).fetchone()
        assert row['state']=='ready'
        quotes=[q for sec in json.loads(row['sections_json']) for q in sec['quotes']]
        assert quotes and all(q in text for q in quotes)
        assert not any('Quasar' in q for q in quotes)
        assert any('Falcon' in q and '仅限内部验证' in q for q in quotes)

def test_one_new_upload_never_retries_thousand_historical_failures(setup,tmp_path,monkeypatch):
    c,a,_,pid,calls=setup
    upload(setup,'retained.txt','ExistingValidQuasar。')
    calls.clear()
    created=material_files.now()
    documents=[];contributions=[]
    for index in range(1000):
        fid=f'historical-failure-{index}'
        text=f'HistoricalFailureQuasar{index}。'
        path=str(tmp_path/(fid+'.txt'))
        documents.extend((fid,pid,fid+'.txt',path,'txt',created,text,'ready'))
        original={'id':fid,'partner_id':pid,'kind':'document','file_path':path,
                  'created_at':created,'text':text,'processing_status':'ready'}
        contributions.extend((pid,'document',fid,sources.stamp(original),'failed','[]',
                              'synthetic historical failure',created))
    with get_db() as conn:
        conn.execute('INSERT INTO partner_documents (id,partner_id,filename,file_path,file_type,created_at,extracted_text,processing_status) VALUES '+
                     ','.join(['(?,?,?,?,?,?,?,?)']*1000),documents)
        conn.execute('INSERT INTO partner_profile_sources (partner_id,source_kind,source_id,source_fingerprint,state,sections_json,error,updated_at) VALUES '+
                     ','.join(['(?,?,?,?,?,?,?,?)']*1000),contributions)
        material_files.changed(conn,pid)
        before=[dict(r) for r in conn.execute("SELECT * FROM partner_profile_sources WHERE state='failed' ORDER BY source_id")]
    parsed=[]
    original_extract=material_files.extract_text
    def extract(path,kind):
        parsed.append(path)
        return original_extract(path,kind)
    monkeypatch.setattr(material_files,'extract_text',extract)
    fresh=upload(setup,'new-only.txt','NewIndependentQuasar。')
    assert [r['material'] for r in calls if 'material' in r]==['NewIndependentQuasar。'] and len(parsed)==1
    assert c.post(f'/partners/{pid}/profile',headers=a).status_code==200
    assert c.post('/partners/batch-profile',headers=a).status_code==200
    case_payload={'partner_id':pid,'title':'MetadataOnly','category_id':'technical-1'}
    response=c.post('/cases',headers=a,json=case_payload)
    assert response.status_code==201
    cid=response.json()['id']
    assert c.put(f'/cases/{cid}',headers=a,json={**case_payload,'title':'MetadataEdited'}).status_code==200
    with get_db() as conn:
        after=[dict(r) for r in conn.execute("SELECT * FROM partner_profile_sources WHERE state='failed' ORDER BY source_id")]
    assert before==after and [r['material'] for r in calls if 'material' in r]==['NewIndependentQuasar。']
    assert 'ExistingValidQuasar' in profile(setup)['ai_profile']
    # A new attachment and explicit classification each dispatch only their own file.
    response=c.post(f'/cases/{cid}/deliverables',headers=a,
                    files={'file':('new-attachment.txt','NewAttachmentQuasar。'.encode())})
    assert response.status_code==201
    response=c.put('/admin/partner-materials/documents/historical-failure-0/classify',
                   headers=a,json={**case_payload,'title':'ExplicitHistoricalFile'})
    assert response.status_code==200
    assert [r['material'] for r in calls if 'material' in r]==[
        'NewIndependentQuasar。','NewAttachmentQuasar。','HistoricalFailureQuasar0。']
    assert len(parsed)==2  # Classification reads the selected committed cache.
    with get_db() as conn:
        assert conn.execute("SELECT count(*) FROM partner_profile_sources WHERE state='failed'").fetchone()[0]==999
        assert conn.execute("SELECT state FROM partner_profile_sources WHERE source_id=?",(fresh,)).fetchone()[0]=='ready'


@pytest.mark.parametrize('scope',['document','attachment'])
def test_independent_upload_b_finishes_while_a_model_is_waiting_and_fails(setup,monkeypatch,scope):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    c,a,_,pid,_=setup
    endpoint=f'/partners/{pid}/documents'
    if scope=='attachment':
        case=c.post('/cases',headers=a,json={'partner_id':pid,'title':'ConcurrentCase',
                                             'category_id':'technical-1'})
        assert case.status_code==201
        endpoint=f"/cases/{case.json()['id']}/deliverables"
    entered=threading.Event();release=threading.Event();seen=[]
    def completion(_config,messages,_schema):
        data=json.loads(messages[-1]['content'])
        if 'material' not in data:return json.dumps(merge_result(data))
        material=data['material'];seen.append(material)
        if material=='BlockedFailureQuasar。':
            entered.set()
            assert release.wait(20),'test did not release synthetic model A'
            raise TimeoutError('synthetic independent A failure')
        return json.dumps({'sections':[{'chapter':5,'summary':material,'quotes':[material]}]})
    monkeypatch.setattr(sources.development_model,'completion',completion)
    def submit(name,text):
        return c.post(endpoint,headers=a,files={'file':(name,text.encode())})
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(submit,'a.txt','BlockedFailureQuasar。')
        try:
            assert entered.wait(10),'A did not reach model'
            with get_db() as conn:
                table='partner_documents' if scope=='document' else 'deliverables'
                fid=conn.execute(f"SELECT id FROM {table} WHERE filename='a.txt'").fetchone()[0]
            assert c.post(endpoint+f'/{fid}/retry',headers=a).status_code==409
            second=pool.submit(submit,'b.txt','IndependentSuccessQuasar。')
            response=second.result(timeout=10)
            assert response.status_code==201,response.text
            assert not first.done() and not release.is_set()
            organize(setup)
            assert 'IndependentSuccessQuasar' in profile(setup)['ai_profile']
        finally:
            release.set()
        assert first.result(timeout=10).status_code==201
    assert seen==['BlockedFailureQuasar。','IndependentSuccessQuasar。']
    with get_db() as conn:
        states={r['source_id']:r['state'] for r in conn.execute(
            "SELECT source_id,state FROM partner_profile_sources WHERE source_kind=?",(scope,))}
        assert states[fid]=='failed' and states[response.json()['id']]=='ready'
    assert 'IndependentSuccessQuasar' in profile(setup)['ai_profile']
    assert 'BlockedFailureQuasar' not in profile(setup)['ai_profile']


@pytest.mark.parametrize('action',['replace','delete'])
def test_normal_api_update_or_delete_while_old_model_waits_keeps_other_facts(setup,monkeypatch,action):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    c,a,_,pid,_=setup
    upload(setup,'retained.txt','UnrelatedRetainedQuasar。')
    organize(setup)
    fid=upload(setup,'version.txt','LateOldVersionQuasar。')
    with get_db() as conn:
        current=sources.source(conn,pid,'document',fid)
        old_fingerprint=sources.stamp(current)
        sources.put(conn,current,'failed',error='synthetic explicit retry')
    entered=threading.Event();release=threading.Event();seen=[]
    def completion(_config,messages,_schema):
        data=json.loads(messages[-1]['content'])
        if 'material' not in data:return json.dumps(merge_result(data))
        material=data['material'];seen.append(material)
        if material=='LateOldVersionQuasar。':
            entered.set()
            assert release.wait(20)
        return json.dumps({'sections':[{'chapter':5,'summary':material,'quotes':[material]}]})
    monkeypatch.setattr(sources.development_model,'completion',completion)
    with ThreadPoolExecutor(max_workers=1) as pool:
        old=pool.submit(c.post,f'/partners/{pid}/documents/{fid}/retry',headers=a)
        try:
            assert entered.wait(10)
            if action=='replace':
                response=c.put(f'/partners/{pid}/documents/{fid}',headers=a,
                               files={'file':('replacement.txt','CurrentReplacementQuasar。'.encode())})
                assert response.status_code==200,response.text
                organize(setup)
                assert 'CurrentReplacementQuasar' in profile(setup)['ai_profile']
            else:
                assert c.delete(f'/partners/{pid}/documents/{fid}',headers=a).status_code==204
            assert 'UnrelatedRetainedQuasar' in profile(setup)['ai_profile']
            assert 'LateOldVersionQuasar' not in profile(setup)['ai_profile']
        finally:
            release.set()
        assert old.result(timeout=10).status_code==200
    # Even a queued old-version callback cannot process the replacement.
    sources.process_source(pid,'document',fid,old_fingerprint)
    assert seen==(['LateOldVersionQuasar。','CurrentReplacementQuasar。'] if action=='replace' else ['LateOldVersionQuasar。'])
    current=profile(setup)['ai_profile']
    assert 'UnrelatedRetainedQuasar' in current and 'LateOldVersionQuasar' not in current
    assert ('CurrentReplacementQuasar' in current)==(action=='replace')


def test_case_move_preserves_ready_attachment_without_models_and_rejects_old_owner(setup,monkeypatch):
    c,a,_,pid,calls=setup
    target=make_partner('move-target','SyntheticTarget')['id']
    payload={'partner_id':pid,'title':'MoveCase','description':'CurrentCaseQuasar。',
             'category_id':'technical-1'}
    response=c.post('/cases',headers=a,json=payload);assert response.status_code==201
    cid=response.json()['id']
    attachment=c.post(f'/cases/{cid}/deliverables',headers=a,
                      files={'file':('move.txt','MoveReadyQuasar。'.encode())})
    assert attachment.status_code==201
    fid=attachment.json()['id']
    with get_db() as conn:
        old_stamp=sources.stamp(sources.source(conn,pid,'attachment',fid))
    calls.clear()
    monkeypatch.setattr(sources.development_model,'completion',lambda *_:pytest.fail('Metadata move must not call a model'))
    assert c.put(f'/cases/{cid}',headers=a,json={**payload,'partner_id':target}).status_code==200
    sources.process_source(pid,'attachment',fid,old_stamp)
    assert calls==[] and 'MoveReadyQuasar' not in profile(setup)['ai_profile']
    moved=c.get(f'/partners/{target}',headers=a).json()
    assert 'MoveReadyQuasar' not in moved['ai_profile'] and moved['profile_needs_update']
    with get_db() as conn:
        raw=' '.join(value['text'] for value in sources.matching_values(conn,target))
        assert 'MoveReadyQuasar' in raw and 'CurrentCaseQuasar' in raw
    with get_db() as conn:
        assert sources.source(conn,pid,'attachment',fid) is None
        row=conn.execute("SELECT state,source_fingerprint FROM partner_profile_sources WHERE partner_id=? AND source_id=?",(target,fid)).fetchone()
        assert row['state']=='ready'
        assert row['source_fingerprint']==sources.stamp(sources.source(conn,target,'attachment',fid))
