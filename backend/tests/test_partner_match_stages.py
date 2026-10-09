"""PG recall and a single validated public matching result."""
from backend.app.routers import match
from backend.app.database import get_db
from .conftest import make_partner
from .test_profile_report import setup,upload
from .conftest import recommendation
from backend.business import matching
import json


def answer(partner_id=None, name='后段能力伙伴', case_ids=None):
    recs = [] if not partner_id else [{
        'partnerId': partner_id, 'partnerName': name, 'matchScore': '86',
        'matchedCapabilities': '', 'matchedIndustries': '', 'matchedRegions': '',
        'recommendationReason': '后段画像提供了待核实的能力线索',
        'evidenceCases': case_ids or [], 'evidenceDeliverables': [],
        'riskNotes': '不支持跨境，交付边界需核实',
    }]
    return json.dumps({ 'recommendations': recs,
                       'supplyStatus': 'partial', 'gapAnalysis': '仍需核实实际交付边界'}, ensure_ascii=False)

def test_invalid_partner_raw_answer_and_supply_are_not_published(setup):
    pid=setup[3];row=None
    with get_db() as conn:row=dict(conn.execute('SELECT * FROM partners WHERE id=?',(pid,)).fetchone())
    context={'profilePassages':[{'source':f'partner:{pid}:profile:1','text':'具备Quasar能力。'}]}
    raw={**recommendation(),'partnerId':pid,'partnerName':row['name'],'evidenceCases':[],'evidenceDeliverables':[], 'profileEvidence':[{'source':f'partner:{pid}:profile:1','quote':'具备Quasar能力。'}]}
    invalid={**raw,'partnerId':'invented-id','partnerName':'InventedPartner'}
    rejections=[]
    recs=match._validated_recommendations([raw,invalid],[row],{pid:[]},{pid:[]},rejections)
    output={'answer':'推荐InventedPartner，供给完全充分。','gapAnalysis':'InventedPartner足够。','supplyStatus':'sufficient','recommendations':[raw,invalid]}
    result=match._validated_outcome(recs,output,bool(rejections),[(row,context,[],[])],requirement='需要Quasar能力')
    assert len(recs)==1 and result['recommendations']==[r.model_dump() for r in recs]
    assert result['recommendations'][0]['partnerName']==row['name'] and 'InventedPartner' not in str(result)
    assert result['answer']=='' and not result['analysisComplete']
    assert result['supplyStatus']=='sufficient'

def test_hidden_sources_are_removed_from_accepted_card_and_answer(setup):
    upload(setup,'PrivateSourceLabel.txt','具备测试能力。')
    pid=setup[3]
    with get_db() as conn:row=dict(conn.execute('SELECT * FROM partners WHERE id=?',(pid,)).fetchone())
    raw={**recommendation(),'partnerId':pid,'partnerName':row['name'],'recommendationReason':'依据PrivateSourceLabel.txt https://private.invalid/file 具备能力','riskNotes':'PrivateSourceLabel.txt待核实'}
    recs=match._validated_recommendations([raw],[row],{pid:[]},{pid:[]})
    result=match._validated_outcome(recs,{'supplyStatus':'partial'},False,[(row,{},[],[])])
    assert 'PrivateSourceLabel.txt' not in str(result) and 'https://private.invalid' not in str(result)
    assert result['recommendations']==[r.model_dump() for r in recs]

def test_detail_prompt_preserves_explicit_hard_requirements():
    prompt=matching.detail_messages('{"facts":{"qualificationRequirements":"必须持证","onsiteRequirement":"必须驻场"}}')
    assert '用户明确提出的必备和排除条件应按原意执行' in prompt[0]['content'] and '必须持证' in prompt[1]['content']

def test_task_persisted_before_understanding_and_no_all_partner_model_call(setup,monkeypatch):
    import json
    from uuid import uuid4
    from backend.app import development_model,match_understanding,agent_settings
    from .conftest import make_user
    upload(setup,'recall.txt','具备TaskFlowQuasar能力。')
    for i in range(15): make_partner('flow-distractor-'+str(i),'无关伙伴'+str(i))
    calls=[];owner=make_user('source-match-owner')
    def complete(config,messages,schema):
        calls.append(schema['title'])
        with get_db() as conn:
            task=dict(conn.execute('SELECT * FROM match_records WHERE owner_user_id=?',(owner['id'],)).fetchone())
            assert task['requirement']=='需要TaskFlowQuasar能力，必须本地交付'
        if schema['title']=='MatchUnderstanding':
            return json.dumps({'in_scope':True,'facts':{'technicalNeeds':'TaskFlowQuasar','onsiteRequirement':'必须本地交付'},'tag_suggestions':[]})
        assert schema['title']=='MatchAnswer'
        data=json.loads(messages[-1]['content'])
        assert len(data['candidates'])<16 and data['facts']['onsiteRequirement']=='必须本地交付'
        candidate=data['candidates'][0]
        assert candidate['partnerId']==setup[3]
        good={**recommendation(),'partnerId':setup[3],'partnerName':'验证伙伴','evidenceCases':[],'evidenceDeliverables':[],
              'recommendationReason':'TaskFlowQuasar能力有资料支持，本地交付仍待核实。',
              'profileEvidence':[{'source':candidate['profilePassages'][0]['source'],'quote':candidate['profilePassages'][0]['text']}]}
        bad={**good,'partnerId':'invalid-id','partnerName':'InvalidOutsidePartner'}
        return json.dumps({'gapAnalysis':'InvalidOutsidePartner覆盖','supplyStatus':'sufficient','recommendations':[good,bad]})
    monkeypatch.setenv('LLM_API_KEY','synthetic-key')
    monkeypatch.setattr(development_model,'completion',complete)
    accepted=match.create_task(match.TaskCreateRequest(requestId=uuid4(),requirement='需要TaskFlowQuasar能力，必须本地交付'),owner)
    match.executor.shutdown(wait=True)
    with get_db() as conn:
        task=dict(conn.execute('SELECT * FROM match_records WHERE id=?',(accepted.recordId,)).fetchone())
        saved=match_understanding.load(conn,accepted.recordId)
    assert calls==['MatchUnderstanding','MatchAnswer']
    assert task['task_status'] in ('ready','partial')
    assert saved['initial_selection']['method']=='postgres_keywords'
    assert 'InvalidOutsidePartner' not in str(saved['outcome'])
    assert json.loads(task['recommendations_json'])==saved['outcome']['recommendations']
    assert saved['outcome']['supplyStatus']=='sufficient'
    assert not saved['outcome']['analysisComplete']


def test_ordinary_history_masks_current_hidden_source_identity_without_rewriting_history(setup):
    from .conftest import make_user,make_task,auth_headers
    from backend.app import match_understanding
    c,admin,_,pid,_=setup
    upload(setup,'HiddenLegacySource.txt','具有测试业务事实。')
    owner=make_user('legacy-hidden-owner')
    rec={**recommendation(),'partnerId':pid,'partnerName':'验证伙伴','recommendationReason':'HiddenLegacySource.txt显示测试业务事实',
         'evidenceCases':'HiddenLegacySource.txt','evidenceDeliverables':'https://hidden.invalid/item'}
    task=make_task(owner,'原始需求应保留',recommendations=[rec])
    with get_db() as conn:
        match_understanding.save(conn,task,{'visible_answer':'依据HiddenLegacySource.txt https://hidden.invalid/item支持测试业务事实'})
    public=c.get('/agent/tasks/'+task,headers=auth_headers(owner))
    assert public.status_code==200
    assert 'HiddenLegacySource.txt' not in public.text and 'https://hidden.invalid' not in public.text
    assert '测试业务事实' in public.text and public.json()['requirement']=='原始需求应保留'
    private=c.get('/agent/tasks/'+task,headers=admin)
    assert 'HiddenLegacySource.txt' in private.text
    with get_db() as conn:
        assert 'HiddenLegacySource.txt' in conn.execute('SELECT recommendations_json FROM match_records WHERE id=?',(task,)).fetchone()[0]



def _synthetic_source(setup, pid, name, body):
    make_partner(pid, name)
    upload((setup[0], setup[1], setup[2], pid, setup[4]), pid + '.txt', body)
    return pid


def test_recall_is_stable_and_questions_cannot_change_it(setup):
    from backend.app.partner_match_context import recall_candidates
    a = _synthetic_source(setup, 'intent-a', '合成甲', '药物研发能力，仅为合成验证资料。')
    b = _synthetic_source(setup, 'intent-b', '合成乙', '药物研发能力，仅为合成验证资料。')
    _synthetic_source(setup, 'generic-it', '合成无关', '软件研发、云平台、交付、现场、认证、预算、资质和教育医疗服务。')
    requirement = '有一个制药项目，需要懂药物研发的服务伙伴'
    pollution = {
        'industry': '教育医疗',
        'followUpQuestions': ['是否有预算、时间、资质、交付、案例、云平台、现场或海外市场要求？'],
        'projectKeywords': '云平台,交付,预算',
        'technicalNeeds': '数据治理',
        'capabilityTags': ['人工智能'],
        'suggestions': ['优先找通用 IT 服务伙伴'],
    }
    with get_db() as conn:
        baseline = recall_candidates(conn, requirement, {})
        info = {}
        polluted = recall_candidates(conn, requirement, pollution, diagnostics=info)
        repeated = recall_candidates(conn, requirement, pollution)
    assert baseline == polluted == repeated
    assert [x['partnerId'] for x in baseline[:2]] == sorted([a, b])
    assert [x['partnerId'] for x in baseline[2:]] == ['generic-it']
    assert info['candidate_order'] == [x['partnerId'] for x in baseline]
    # Partial original-term overlap is retrieval only, not a professional recommendation.
    assert baseline[2]['recallTerms'] == ['研发']
    query_terms, _ = matching.recall_query(requirement, pollution)
    assert not {'预算', '资质', '教育医疗', '人工智能', '数据治理'} & set(query_terms)
    assert 'keywords' not in info and len(info['keyword_fingerprint']) == 64


def test_recall_requires_original_term_hits_without_filling_unmatched_partners(setup):
    from backend.app.partner_match_context import recall_candidates
    upload(setup, 'generic-only.txt', '具备软件研发、交付、服务、认证、平台、资质及案例。')
    for i in range(14):
        make_partner('no-topic-' + str(i), '合成通用伙伴' + str(i))
    with get_db() as conn:
        partial = recall_candidates(conn, '需要懂药物研发的服务伙伴', {})
        assert [x['partnerId'] for x in partial] == [setup[3]]
        assert partial[0]['recallTerms'] == ['研发']
        assert recall_candidates(conn, '需要服务伙伴，提供交付服务', {}) == []


def test_controlled_synonyms_recall_across_domains_without_literal_phrase(setup):
    from backend.app.partner_match_context import recall_candidates
    examples = [
        ('synonym-rd', '药物研发', '药物研究与开发'),
        ('synonym-finance', '银行风险控制', '银行风控'),
        ('synonym-ai', '人工智能客户分析', 'AI客户分析'),
    ]
    for pid, original, source in examples:
        _synthetic_source(setup, pid, '合成同义伙伴' + pid, source + '；资料自述，尚未核实交付。')
        assert original not in source
    with get_db() as conn:
        for pid, original, _ in examples:
            selected = recall_candidates(conn, '需要' + original + '服务伙伴', {})
            assert selected and selected[0]['partnerId'] == pid


def test_topic_combination_can_recall_without_an_exact_compound(setup):
    from backend.app.partner_match_context import recall_candidates
    pid = _synthetic_source(setup, 'separate-topic', '合成主题伙伴', '具备药物数据处理能力；支持研发阶段，实际交付需核实。')
    with get_db() as conn:
        selected = recall_candidates(conn, '需要药物研发服务伙伴', {})
    assert [x['partnerId'] for x in selected] == [pid]


def test_model_supply_is_not_mechanically_capped_by_current_capability(setup):
    from backend.app.partner_match_context import detailed_candidate
    upload(setup,'current-self-claim.txt','具备药物研发能力，项目经验尚未确认。')
    with get_db() as conn:
        row,context,cases,files=detailed_candidate(conn,setup[3],'药物研发','需要药物研发伙伴')
    passage=context['profilePassages'][0]
    raw={**recommendation(),'partnerId':row['id'],'partnerName':row['name'],
         'recommendationReason':'仅有相关能力自述，项目经验尚未确认。',
         'evidenceType':'current_capability','evidenceCases':[],'evidenceDeliverables':[],'profileEvidence':[{'source':passage['source'],'quote':passage['text']}]}
    recs=match._validated_recommendations([raw],[row],{row['id']:[]},{row['id']:[]})
    result=match._validated_outcome(recs,{'supplyStatus':'sufficient','recommendations':[raw]},False,
                                    [(row,context,cases,files)],requirement='需要药物研发伙伴')
    assert result['supplyStatus']=='sufficient'
    assert result['recommendations'][0]['recommendationReason']==raw['recommendationReason']


def test_reason_prefix_is_not_a_programmatic_veto(setup):
    with get_db() as conn:
        row = dict(conn.execute('SELECT * FROM partners WHERE id=?', (setup[3],)).fetchone())
    raw = {**recommendation(), 'partnerId': row['id'], 'partnerName': row['name'],
           'recommendationReason': '泛 IT 能力不足：无法建立与本次核心需求的联系。','evidenceCases':[],'evidenceDeliverables':[]}
    rejected = []
    recs = match._validated_recommendations([raw], [row], {row['id']: []}, {row['id']: []}, rejected)
    assert len(recs)==1 and not rejected
    assert recs[0].recommendationReason==raw['recommendationReason']


def test_review_prompt_distinguishes_completed_project_claims_and_generic_it():
    prompt = matching.detail_messages('{}')[0]['content']
    assert all(word in prompt for word in ['current_capability', 'delivered_project', '不把规划、协作、奖项或群体介绍说成该伙伴已经完成的具体项目'])



def test_original_word_project_fact_supports_direct_evidence_without_attachments(setup):
    from backend.tests.support.profile_report_fixture import document
    from backend.app.partner_match_context import detailed_candidate
    requirement = '需要药物研发服务伙伴'
    upload(setup, 'completed-project.docx', document(extra='已交付药物研发数据平台，完成项目验收。'), True)
    with get_db() as conn:
        row, context, cases, files = detailed_candidate(conn, setup[3], requirement, requirement)
    raw = {**recommendation(), 'partnerId': row['id'], 'partnerName': row['name'],
           'recommendationReason': '直接项目证据：画像原文有药物研发平台交付记录。',
           'evidenceCases': [], 'evidenceDeliverables': [], 'evidenceType':'delivered_project',
           'profileEvidence':[{'source':p['source'],'quote':p['text']} for p in context['profilePassages']]}
    recs = match._validated_recommendations([raw], [row], {row['id']: cases}, {row['id']: files})
    result = match._validated_outcome(recs, {'supplyStatus': 'sufficient','recommendations':[raw]}, False,
                                     [(row, context, cases, files)], requirement=requirement)
    assert recs and result['supplyStatus'] == 'sufficient'
    assert result['recommendations'][0]['recommendationReason'].startswith(matching.DIRECT_EVIDENCE)
    assert setup[4] == []  # Original Word adoption remains entirely local.


def test_valid_case_reference_to_a_plan_is_not_a_formal_recommendation(setup):
    with get_db() as conn:
        row = dict(conn.execute('SELECT * FROM partners WHERE id=?', (setup[3],)).fetchone())
    case = {'id': 'synthetic-plan-case', 'partner_id':row['id'], 'title': '药物研发项目规划',
            'description': '仅规划药物研究开发功能，尚未实施或交付。'}
    raw = {**recommendation(), 'partnerId': row['id'], 'partnerName': row['name'],
           'recommendationReason': '直接项目证据：具备药物研发项目能力。',
           'evidenceCases': [case['id']], 'evidenceDeliverables': [], 'evidenceType':'planning_only'}
    recs = match._validated_recommendations([raw], [row], {row['id']: [case]}, {row['id']: []})
    result = match._validated_outcome(recs, {'supplyStatus': 'sufficient','recommendations':[raw]}, False,
                                     [(row, {}, [case], [])], requirement='需要药物研发服务伙伴')
    assert recs == [] and result['supplyStatus'] == 'unknown'
    assert '未来规划线索' in result['answer']


def test_unrelated_completed_project_does_not_prove_current_requirement(setup):
    upload(setup, 'completed-unrelated.txt', '已交付云运维管理平台并通过验收。')
    from backend.app.partner_match_context import detailed_candidate
    requirement = '需要药物研发服务伙伴'
    with get_db() as conn:
        row, context, cases, files = detailed_candidate(conn, setup[3], requirement, requirement)
    raw = {**recommendation(), 'partnerId': row['id'], 'partnerName': row['name'],
           'recommendationReason': '直接项目证据：模型声称具备药物研发经验。',
           'evidenceCases': [], 'evidenceDeliverables': [], 'evidenceType':'unrelated',
           'profileEvidence':[{'source':p['source'],'quote':p['text']} for p in context['profilePassages']]}
    recs = match._validated_recommendations([raw], [row], {row['id']: cases}, {row['id']: files})
    result = match._validated_outcome(recs, {'supplyStatus': 'sufficient','recommendations':[raw]}, False,
                                     [(row, context, cases, files)], requirement=requirement)
    assert recs == [] and result['supplyStatus'] == 'unknown'
    assert result['analysisComplete']


def test_recall_metadata_never_logs_original_words_or_synthetic_credentials(setup, caplog):
    import logging
    from backend.app.partner_match_context import recall_candidates, log_match_metadata
    fake = 'SYNTHETIC_SECRET_123456'
    requirement = '需要药物研发；API_KEY=' + fake
    with get_db() as conn:
        info = {}
        recall_candidates(conn, requirement, {}, diagnostics=info)
    with caplog.at_level(logging.INFO, logger='uvicorn.error'):
        log_match_metadata('RECALL', task_id='synthetic-id', input_version='synthetic-version',
                           keywords=[fake], requirement=requirement, **info)
    assert fake.lower() not in caplog.text.lower()
    assert '药物研发' not in caplog.text and 'api_key' not in caplog.text.lower()
    assert 'keyword_fingerprint' in caplog.text and 'candidate_order' in caplog.text

def test_actual_detail_payload_prioritizes_rare_tail_source_and_keeps_qualifier(setup,monkeypatch):
    from uuid import uuid4
    from backend.app import development_model,match_understanding,partner_match_context
    from backend.app.ai_client import completion_payload
    from backend.app.model_resolver import model_config_from_record
    from .conftest import make_user
    requirement='需要RareTailQuasar专业服务。'+'补充背景。'*35+'必须本地交付，排除仅提供资源开通的伙伴。'
    tail='RareTailQuasar专业服务\n\n企业自述，相关交付经历待核实。\n具备数据分析方案能力。'
    prefix='\n'.join(f'第{i}项服务伙伴项目需求风险说明：服务伙伴项目都需核实，伙伴服务项目暂无直接关联。' for i in range(200))
    upload(setup,'synthetic-long-tail.txt',prefix+'\n'+tail)
    owner=make_user('rare-tail-payload-owner')
    calls=[];payloads=[]
    def complete(config,messages,schema):
        calls.append(schema['title'])
        if schema['title']=='MatchUnderstanding':
            return json.dumps({'in_scope':True,'facts':{'technicalNeeds':'RareTailQuasar药物研发'},'tag_suggestions':[]})
        assert schema['title']=='MatchAnswer'
        # Inspect the entire provider-shaped payload at the actual detail call.
        payload=completion_payload(model_config_from_record(config),messages,schema)
        payloads.append(payload)
        data=json.loads(next(m['content'] for m in payload['messages'] if m['role']=='user'))
        candidate=next(x for x in data['candidates'] if x['partnerId']==setup[3])
        passages=candidate['profilePassages']
        assert any('RareTailQuasar' in p['text'] for p in passages)
        assert any('企业自述' in p['text'] and '待核实' in p['text'] for p in passages)
        assert data['requirement']==requirement and len(requirement)>150
        assert json.dumps(data,ensure_ascii=False).count(requirement)==1
        assert '必须本地交付，排除仅提供资源开通的伙伴。' in data['requirement']
        assert any(p['text'].startswith('RareTailQuasar专业服务') and
                   '企业自述' in p['text'] and '数据分析方案' in p['text'] for p in passages)
        assert not any(k.startswith('_') for k in candidate)
        assert all(p['source'].startswith('P1-S') for p in passages)
        measured = partner_match_context.input_metrics(config,messages,schema)
        packed = json.dumps(payload['messages'],ensure_ascii=False,separators=(',',':'))
        assert measured[0] == len(packed) <= partner_match_context.DETAIL_CHAR_LIMIT
        assert payload['messages'][0]['content'].count('Return only a JSON object matching this JSON schema.') == 1
        assert 'inputCoverage' not in candidate and 'omissions' not in str(candidate)
        assert prefix not in json.dumps(payload,ensure_ascii=False)
        return json.dumps({'recommendations':[
            {**recommendation(),'partnerId':candidate['partnerId'],'partnerName':candidate['name'],
             'recommendationReason':'模型判断存在相关现有方案，交付边界待核实。',
             'evidenceType':'current_capability','profileEvidence':[{'source':p['source'],'quote':p['text']} for p in passages],
             'evidenceCases':[],'evidenceDeliverables':[]}],
            'supplyStatus':'partial','gapAnalysis':'本地交付和资源开通排除条件由同次模型判断。'},ensure_ascii=False)
    monkeypatch.setattr(development_model,'completion',complete)
    accepted=match.create_task(match.TaskCreateRequest(requestId=uuid4(),requirement=requirement),owner)
    match.executor.shutdown(wait=True)
    with get_db() as conn:
        record=conn.execute('SELECT task_status FROM match_records WHERE id=?',(accepted.recordId,)).fetchone()
        saved=match_understanding.load(conn,accepted.recordId)
    assert calls==['MatchUnderstanding','MatchAnswer'] and len(payloads)==1
    assert record['task_status']=='ready'
    assert len(saved['outcome']['recommendations'])==1
    candidate=saved['initial_selection']['candidates'][0]
    assert candidate['hits'] and all(set(h)=={'sourceRef','source_version','path','start','end'} for h in candidate['hits'])
    assert saved['detail_source_map'][setup[3]]
    detail=setup[0].get('/agent/tasks/'+accepted.recordId,headers=__import__('backend.tests.conftest',fromlist=['auth_headers']).auth_headers(owner))
    assert detail.status_code==200 and len(detail.json()['recommendations'])==1
    assert detail.json()['requirement']==requirement
    assert detail.json()['recommendations']==saved['outcome']['recommendations']
