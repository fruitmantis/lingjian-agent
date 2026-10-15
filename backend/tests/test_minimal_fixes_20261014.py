"""10/14 bounded original business replays; no provider or runtime DB writes."""
import copy,hashlib,json,os
from pathlib import Path
import pytest
from backend.app import development_engine as engine, development_lifecycle as life
from backend.app import development_model as model, development_views as views, enablement
from backend.app import partner_match_context as context
from backend.app.database import get_db
from backend.app.development_types import Conversation
from backend.business import matching
from backend.business.matching_types import MatchAnswer
from backend.tests.conftest import auth_headers
from backend.tests.test_development_lifecycle import prepared
from backend.tests.test_bf_close import seed_plan,insert

@pytest.fixture
def original():
    location=os.environ.get('BANFEI_MINIMAL_EVIDENCE_DIR')
    if not location:pytest.skip('Original 10/14 archived replay requires BANFEI_MINIMAL_EVIDENCE_DIR.')
    root=Path(location)
    return root,json.loads((root/'MINIMAL-FIXTURES.json').read_text())

def resources(fixture,admin):
    for table,rows in fixture.get('bq22_catalog',{}).items():
        with get_db() as conn:
            for original in rows:
                row=copy.deepcopy(original)
                for field in ('created_by','updated_by','published_by'):
                    if row.get(field):row[field]=admin['id']
                insert(conn,table,row)
    for sid,kind,title,summary in fixture['bq22_resources']:
        metadata={'resource_type':kind,'title':title,'summary':summary,'level':'advanced' if sid.endswith('advanced') else 'basic','source_url':'https://example.invalid/'+sid}
        metadata['course_goals' if kind=='course' else 'lab_goals']=summary
        row=enablement.save('resource',sid,enablement.ResourceSave(base_revision=0,metadata=metadata),admin['id'])
        row=enablement.permissions('resource',sid,enablement.Permissions(base_revision=row['revision'],system_visible=True,model_allowed=True,partner_allowed=True,reason='Original isolated BQ22 replay'),admin['id'])
        enablement.publish('resource',sid,enablement.Revision(base_revision=row['revision']),admin['id'])

def test_original_bq22_new_version_omits_retired_field_and_preserves_unrelated_data(prepared,original,monkeypatch,client):
    root,fixture=original;user,_,admin,_=prepared;resources(fixture,admin)
    before=fixture['bq22_before'];version=fixture['bq22_versions'][0]
    with get_db() as conn:pid,base=seed_plan(conn,before,before['request'],[version],user)
    calls=[]
    def complete(config,messages,schema):
        calls.append(schema['title']);return json.dumps(fixture['bq22_responses'][len(calls)-1],ensure_ascii=False)
    monkeypatch.setattr(model,'completion',complete)
    run=views.converse(pid,Conversation(submission_id='minimal-bq22-correction',based_on_version_id=base,message=fixture['bq22_message']),user)
    engine.execute(run['run_id'])
    after=client.get('/development/plans/'+pid,headers=auth_headers(user)).json()
    assert after['runs'][0]['status']=='ready',after['runs']
    assert calls==['Understanding','AdvicePatch'] and 'limitations' not in after['payload']
    with get_db() as conn:
        assert conn.execute('SELECT payload_json FROM development_versions WHERE id=?',(base,)).fetchone()[0]==version['payload_json']
        saved=json.loads(conn.execute('SELECT payload_json FROM development_versions WHERE id=?',(after['plan']['current_version_id'],)).fetchone()[0])
        dependencies=json.loads(conn.execute('SELECT dependency_json FROM development_versions WHERE id=?',(after['plan']['current_version_id'],)).fetchone()[0])
    assert 'limitations' not in saved
    expected=json.loads(fixture['bq22_versions'][1]['payload_json'])
    for field in ['answer','next_steps','resource_gaps']:assert saved[field]==expected[field]
    old_items=[i for s in json.loads(version['payload_json'])['stages'] for i in s['items']]
    items=[i for s in saved['stages'] for i in s['items']]
    expected_items=[i for s in expected['stages'] for i in s['items']]
    assert [i['source_id'] for i in items]==[i['source_id'] for i in expected_items]
    for item,recorded in zip(items,expected_items):
        assert {k:v for k,v in item.items() if k!='item_id'}=={k:v for k,v in recorded.items() if k!='item_id'}
    assert items[0]['item_id']==old_items[1]['item_id'] and items[-1]==old_items[-1]
    assert all(ref in dependencies for ref in json.loads(version['dependency_json']) if ref['source_id']=='bq22-migration-lab')
    copied=views.transferable(pid,user,after['plan']['current_version_id'])
    assert '尚不会Python' not in copied['text']
    (root/'BQ22-ORIGINAL-REPLAY.json').write_text(json.dumps({'calls':calls,'provider_calls':0,'saved':saved,'dependencies':dependencies,'api':after,'copy':copied,'original_v1_unchanged':True},ensure_ascii=False,indent=2))

def test_existing_bq22_v2_read_copy_and_next_save_do_not_use_retired_field(prepared,original,client):
    root,fixture=original;user,_,admin,_=prepared;resources(fixture,admin)
    versions=copy.deepcopy(fixture['bq22_versions']);versions[1]['based_on_version_id']=versions[0]['id']
    with get_db() as conn:pid,base=seed_plan(conn,fixture['bq22_before'],fixture['bq22_before']['request'],versions,user)
    assert json.loads(versions[1]['payload_json'])['limitations']
    current=client.get('/development/plans/'+pid,headers=auth_headers(user)).json()
    historical=client.get('/development/plans/'+pid+'?version_id='+versions[0]['id'],headers=auth_headers(user)).json()
    assert current['plan']['current_version_id']==base and 'limitations' not in current['payload'] and 'limitations' not in historical['payload']
    copied=views.transferable(pid,user,base)
    assert '尚不会Python' not in copied['text'] and '没有API集成经验' not in copied['text']
    with get_db() as conn:
        for row in versions:assert conn.execute('SELECT payload_json FROM development_versions WHERE id=?',(row['id'],)).fetchone()[0]==row['payload_json']
        plan=life.authorize(conn,pid,user)
        new=life.save_version(conn,plan,base,json.loads(versions[1]['payload_json']),json.loads(versions[1]['dependency_json']),user['id'])
        payload=conn.execute('SELECT payload_json FROM development_versions WHERE id=?',(new,)).fetchone()[0]
        expected=json.loads(versions[1]['payload_json']);expected.pop('limitations')
        assert json.loads(payload)==expected
        assert conn.execute('SELECT dependency_json FROM development_versions WHERE id=?',(new,)).fetchone()[0]==life.dump(json.loads(versions[1]['dependency_json']))
        for row in versions:assert conn.execute('SELECT payload_json FROM development_versions WHERE id=?',(row['id'],)).fetchone()[0]==row['payload_json']
    (root/'BQ22-EXISTING-V2-PROJECTION.json').write_text(json.dumps({'current_api':current,'historical_api':historical,'copy':copied,'next_payload':expected,'old_v1_v2_unchanged':True,'provider_calls':0},ensure_ascii=False,indent=2))

def test_original_bq03_same_source_title_reaches_actual_bounded_request(prepared,original,monkeypatch):
    from backend.app.routers import match
    from backend.tests.test_model_simplification import CONFIG
    root,fixture=original;native=fixture['bq03_native']
    assert hashlib.sha256(native.encode()).hexdigest()==fixture['bq03_native_sha256']
    values=[{**row,'original':native} for row in fixture['bq03_values']]
    monkeypatch.setattr(context,'_candidate_values',lambda conn,partner:copy.deepcopy(values))
    requirement=fixture['bq03_before_input']['requirement']
    with get_db() as conn:
        row=context.detailed_candidate(conn,'partner-1','软件漏洞修复和应急响应',requirement,recall_terms=['漏洞','安全'])
    rows=[row];snapshot={'understanding':{'facts':fixture['bq03_before_input']['facts']}}
    context.assemble_details(rows,CONFIG,lambda current:match._detail_content(requirement,snapshot,current),MatchAnswer.model_json_schema())
    messages=matching.detail_messages(match._detail_content(requirement,snapshot,rows));frame=json.loads(messages[-1]['content'])
    passages=frame['candidates'][0]['profilePassages'];source_map=row[1]['_sourceMap']
    title='三次蝉联！华为云CodeArts位居DevOps平台领导者类别'
    assert passages and any('7000+代码检查' in p['text'] for p in passages)
    for group in row[1]['_groups']:
        if any('7000+代码检查' in source_map[s]['text'] for s in group['sources']):
            assert any(title in source_map[s]['text'] for s in group['sources'])
    assert any(title in p['text'] for p in passages)
    assert all(p['text']==native[source_map[p['source']]['start']:source_map[p['source']]['end']] for p in passages)
    assert all('证据边界：' not in p['text'] for p in passages)
    assert context.input_metrics(CONFIG,messages,MatchAnswer.model_json_schema())[0]<=context.DETAIL_CHAR_LIMIT
    parsed,rejected=matching.parse_answer(json.dumps(fixture['bq03_response'],ensure_ascii=False))
    assert not rejected and len(parsed['recommendations'])==len(fixture['bq03_response']['recommendations'])
    assert [r['evidenceType'] for r in parsed['recommendations']]==[r['evidenceType'] for r in fixture['bq03_response']['recommendations']]
    assert [r['recommendationReason'] for r in parsed['recommendations']]==[r['recommendationReason'] for r in fixture['bq03_response']['recommendations']]
    (root/'BQ03-TITLE-ACTUAL-INPUT.json').write_text(json.dumps({'input':frame,'source_map':source_map,'native_sha256':fixture['bq03_native_sha256'],'original_business_contract_preserved':True,'provider_calls':0},ensure_ascii=False,indent=2))

def test_original_bq24_replaces_condition_clause_and_keeps_explicit_requirement(original):
    root,fixture=original;frame=fixture['bq24_before_input'];messages=matching.detail_messages(json.dumps(frame,ensure_ascii=False));prompt=messages[0]['content']
    assert '用户要求相关服务经历时，结合每家拟承担的服务判断' in prompt
    assert '只有用户明确要求单家包办，才按单家覆盖全部工作理解' in prompt
    assert '用户其他明确必备条件、资格和排除条件' in prompt
    assert prompt.count('允许伙伴按各自能力分工')==1
    assert '项目工作允许分工；用户明确限定合作方本身的经验' not in prompt
    assert json.loads(messages[-1]['content'])==frame
    (root/'BQ24-CONDITION-REQUEST.json').write_text(json.dumps({'messages':messages,'requirement_unchanged':True,'provider_calls':0},ensure_ascii=False,indent=2))
