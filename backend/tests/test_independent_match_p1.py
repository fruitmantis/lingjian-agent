"""Independent QA probes: synthetic sources, dedicated PG, no external model."""
import json
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path
from backend.app import development_model, match_understanding, profile_sources
from backend.app.database import get_db
from backend.app.routers import match
from backend.tests.conftest import make_user, recommendation
from backend.tests.test_profile_report import setup, upload

def run_actual_task(setup, monkeypatch, requirement, raw_builder):
    owner=make_user('independent-owner-'+uuid4().hex[:8])
    payloads=[]
    def completion(config, messages, schema):
        if schema['title']=='MatchUnderstanding':
            return json.dumps({'in_scope':True,'facts':{'technicalNeeds':'药物研发'},'tag_suggestions':[]})
        assert schema['title']=='MatchAnswer'
        from backend.app.ai_client import completion_payload
        from backend.app.model_resolver import model_config_from_record
        payload=completion_payload(model_config_from_record(config),messages,schema)
        data=json.loads(next(m['content'] for m in payload['messages'] if m['role']=='user'))
        assert data['requirement']==requirement
        payloads.append(data)
        candidate=next(c for c in data['candidates'] if c['partnerId']==setup[3])
        item=raw_builder(candidate)
        return json.dumps({'recommendations':[item],
                           'supplyStatus':'sufficient','gapAnalysis':'raw supplier coverage'},ensure_ascii=False)
    monkeypatch.setattr(development_model,'completion',completion)
    accepted=match.create_task(match.TaskCreateRequest(requestId=uuid4(),requirement=requirement),owner)
    match.executor.shutdown(wait=True)
    with get_db() as conn:
        snapshot=match_understanding.load(conn,accepted.recordId)
        record=dict(conn.execute('SELECT task_status,recommendations_json FROM match_records WHERE id=?',(accepted.recordId,)).fetchone())
    assert len(payloads)==1 and record['task_status']=='ready'
    assert json.loads(record['recommendations_json'])==snapshot['outcome']['recommendations']
    return snapshot['outcome'],payloads[0]

def literal_item(candidate, kind, reason, quote):
    passage=next(p for p in candidate['profilePassages'] if quote in p['text'])
    return {**recommendation(),'partnerId':candidate['partnerId'],'partnerName':candidate['name'],
            'evidenceType':kind,'recommendationReason':reason,
            'profileEvidence':[{'source':passage['source'],'quote':quote}],
            'evidenceCases':[],'evidenceDeliverables':[]}

def test_independent_unrelated_future_plan_does_not_erase_delivered_drug_project(setup,monkeypatch):
    body='已交付药物研发数据平台，完成项目验收；另一业务计划开发通用办公系统。'
    upload(setup,'synthetic-mixed-current-plan.txt',body)
    result,payload=run_actual_task(setup,monkeypatch,'需要药物研发服务伙伴',
        lambda c:literal_item(c,'delivered_project','直接项目证据：已交付药物研发数据平台。','已交付药物研发数据平台，完成项目验收'))
    assert any(body in p['text'] for c in payload['candidates'] if c['partnerId']==setup[3] for p in c['profilePassages'])
    assert len(result['recommendations'])==1, 'An unrelated future plan must not negate the explicitly delivered drug project'
    assert result['recommendations'][0]['recommendationReason'].startswith('直接项目证据：')

def test_independent_same_title_ids_keep_binding_without_semantic_reclassification(setup,monkeypatch,tmp_path):
    # The deliberately wrong model reason is not a business-effect test.
    # Check exact stored/sent IDs and reject ambiguous labels, not narrative meaning.
    pid=setup[3];stamp=datetime.now(timezone.utc).isoformat()
    office_id='office-'+uuid4().hex;drug_id='drug-'+uuid4().hex;fid='file-'+uuid4().hex
    title='同名交付项目';office='已为制药企业完成机房部署。';drug='已交付药物研发数据平台，完成项目验收。'
    path=tmp_path/'synthetic-office.txt';path.write_text(office)
    with get_db() as conn:
        for cid,body in [(office_id,office),(drug_id,drug)]:
            conn.execute('INSERT INTO cases(id,partner_id,title,description,category_id,visible,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                         (cid,pid,title,body,'delivery-1',1,stamp,stamp))
        conn.execute('INSERT INTO deliverables(id,case_id,filename,file_path,file_type,created_at,extracted_text,processing_status,processed_at) VALUES (?,?,?,?,?,?,?,?,?)',
                     (fid,office_id,'机房交付.txt',str(path),'txt',stamp,office,'ready',stamp))
        profile_sources.sync(conn,pid)
        source=next(s for s in profile_sources.sources(conn,pid) if s['kind']=='attachment' and s['id']==fid)
        profile_sources.put(conn,source,'ready',[{'chapter':6,'quotes':[office]}])
        profile_sources.rebuild(conn,pid)
    def raw(c):
        assert {office_id,drug_id}.issubset({x['id'] for x in c['visibleCases']})
        assert any(f['id']==fid for f in c['deliverables'])
        return {**recommendation(),'partnerId':pid,'partnerName':c['name'],'evidenceType':'delivered_project',
                'recommendationReason':'直接项目证据：已交付药物研发数据平台。',
                'profileEvidence':[],'evidenceCases':[],'evidenceDeliverables':[fid]}
    result,payload=run_actual_task(setup,monkeypatch,'有一个制药项目，需要懂药物研发的服务伙伴',raw)
    sent_file=next(f for c in payload['candidates'] if c['partnerId']==pid for f in c['deliverables'] if f['id']==fid)
    assert sent_file['caseId']==office_id and sent_file['caseId']!=drug_id
    with get_db() as conn:
        bound_file=dict(conn.execute('SELECT * FROM deliverables WHERE id=?',(fid,)).fetchone())
        case_rows=[dict(conn.execute('SELECT * FROM cases WHERE id=?',(cid,)).fetchone()) for cid in (office_id,drug_id)]
    assert bound_file['case_id']==office_id
    assert match._references_valid([fid],[bound_file],'filename',pid,owned_cases=case_rows)
    assert not match._references_valid([title],case_rows,'title',pid)
    assert not match._references_valid([drug_id],[bound_file],'filename',pid,owned_cases=case_rows)
    assert len(result['recommendations'])==1 and result['supplyStatus']=='sufficient'
    assert result['recommendations'][0]['recommendationReason']=='直接项目证据：已交付药物研发数据平台。'
    assert result['recommendations'][0]['evidenceDeliverables']==f'机房交付.txt（案例：{title}）'

def test_independent_hidden_source_is_redacted_in_a_retained_public_card(setup,monkeypatch):
    body='企业自述，现有能力介绍，交付经历待核实。\n具备药物研发能力，提供研发数据分析方案。'
    filename='IndependentHiddenSource.txt'
    upload(setup,filename,body)
    def raw(c):
        item=literal_item(c,'current_capability','相关能力自述（待核实）：依据IndependentHiddenSource.txt https://private.invalid/source 具备药物研发能力。','具备药物研发能力，提供研发数据分析方案。')
        item['riskNotes']='IndependentHiddenSource.txt为内部来源，经历待核实'
        return item
    result,payload=run_actual_task(setup,monkeypatch,'需要药物研发服务伙伴',raw)
    assert len(result['recommendations'])==1, 'Privacy check must retain a valid card instead of passing by rejecting it'
    assert result['supplyStatus']=='sufficient'  # Hiding source names is not a supply judgment.
    assert filename not in json.dumps(result,ensure_ascii=False)
    assert 'https://private.invalid' not in json.dumps(result,ensure_ascii=False)
    # The supplied gap is the current overall-summary field, not an unused raw answer.
    assert result['answer']==result['gapAnalysis']=='raw supplier coverage'

def test_independent_complete_original_requirement_after_first_150_chars_reaches_provider_payload(setup,monkeypatch):
    upload(setup,'synthetic-long-requirement.txt','具备药物研发能力，提供研发数据分析方案。')
    requirement='需要药物研发服务伙伴。'+('这是用户补充的原始项目背景，完整保留。'*20)+'最终硬条件：必须北京驻场且交付时限为九十天。'
    assert len(requirement)>150
    result,payload=run_actual_task(setup,monkeypatch,requirement,
        lambda c:literal_item(c,'unrelated','相关能力自述（待核实）：仅供检查完整原文传递。','具备药物研发能力，提供研发数据分析方案。'))
    assert payload['requirement']==requirement
    assert '最终硬条件：必须北京驻场且交付时限为九十天。' in payload['requirement'][150:]
    assert payload['facts']['technicalNeeds']=='药物研发'
    assert 'understanding' not in payload  # Only extracted demand facts, no duplicate wrapper.
    assert not {'inputCoverage','evidenceState','_sourceMap'} & set(payload)
