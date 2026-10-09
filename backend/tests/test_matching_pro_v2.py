"""Finite PRO v2 legal-boundary and actual-input regressions; no real model calls."""
import copy
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from backend.app import match_understanding, partner_match_context, profile_sources
from backend.app.database import get_db
from backend.app.routers import match
from backend.business import matching
from .conftest import make_partner, make_task, make_user, auth_headers, recommendation
from .test_profile_report import setup, upload


def legal_row(setup, body='具备NovelVision视觉检测能力。'):
    upload(setup,'synthetic-novel-vision.txt',body)
    with get_db() as conn:
        return partner_match_context.detailed_candidate(conn,setup[3],'短提示','需要NovelVision视觉检测')


def legal_item(row, *, kind='current_capability'):
    p = row[1]['profilePassages'][-1]
    return {**recommendation(),'partnerId':row[0]['id'],'partnerName':row[0]['name'],
            'recommendationReason':'泛 IT 能力不足：旧前缀也不能替代模型本次分类。',
            'evidenceType':kind,'profileEvidence':[{'source':p['source'],'quote':p['text']}],
            'evidenceCases':[],'evidenceDeliverables':[]}


def evaluate(row,item,supply='sufficient',*,rejected=False):
    reasons=[]
    recs=match._validated_recommendations([item],[row[0]],{row[0]['id']:row[2]},
                                        {row[0]['id']:row[3]},reasons)
    return match._validated_outcome(recs,{'recommendations':[item],'supplyStatus':supply,
                                         'gapAnalysis':'模型给出的覆盖和缺口说明。'},
                                    bool(reasons) or rejected,[row],requirement='必须有另一陌生专业的交付案例。')


@pytest.mark.parametrize('kind',['current_capability','delivered_project'])
@pytest.mark.parametrize('supply',['sufficient','partial','gap','unknown'])
def test_legal_model_category_and_supply_are_independent(setup,kind,supply):
    row=legal_row(setup,'NovelVision行业方向\n企业自述，处于规划阶段，尚未交付。\n具备视觉检测方案。')
    item=legal_item(row,kind=kind)
    result=evaluate(row,item,supply)
    assert len(result['recommendations'])==1
    assert result['recommendations'][0]['recommendationReason']==item['recommendationReason']
    assert result['supplyStatus']==supply and result['analysisComplete']
    # This tests the legal layer; contradictory model semantics are not called business-correct.


@pytest.mark.parametrize('kind',['planning_only','unrelated'])
def test_model_exclusion_does_not_mark_legal_analysis_incomplete(setup,kind):
    row=legal_row(setup);item=legal_item(row,kind=kind)
    result=evaluate(row,item)
    assert not result['recommendations'] and result['supplyStatus']=='unknown'
    assert result['analysisComplete']


@pytest.mark.parametrize('bad',['fake_partner','name_mismatch','foreign_source','fake_quote','stitched_quote','foreign_case','fake_file','foreign_map'])
def test_one_illegal_reference_rejects_whole_item(setup,bad):
    row=legal_row(setup,'具备NovelVision视觉检测能力。\n相关交付边界待核实。')
    item=legal_item(row)
    if bad=='fake_partner':item['partnerId']='unselected-id'
    elif bad=='name_mismatch':item['partnerName']='不同身份'
    elif bad=='foreign_source':item['profileEvidence'].append({'source':'partner:other:profile:0','quote':'真实但非本伙伴引用'})
    elif bad=='fake_quote':item['profileEvidence'].append({'source':item['profileEvidence'][0]['source'],'quote':'未实际发送的原文。'})
    elif bad=='stitched_quote':item['profileEvidence'][0]['quote']='具备NovelVision能力。相关交付边界。'
    elif bad=='foreign_case':item['evidenceCases']=['other-case']
    elif bad=='fake_file':item['evidenceDeliverables']=['fake-file']
    else:row[1]['_sourceMap'][item['profileEvidence'][0]['source']]['partnerId']='other'
    result=evaluate(row,item)
    assert not result['recommendations'] and not result['analysisComplete']


def test_sent_case_and_file_ownership_is_required_even_with_a_good_quote(setup):
    row=legal_row(setup);item=legal_item(row)
    case={'id':'sent-case','partner_id':row[0]['id'],'title':'案例','description':'原文'}
    file={'id':'sent-file','case_id':case['id'],'filename':'交付.txt','case_title':case['title']}
    item.update(evidenceCases=[case['id']],evidenceDeliverables=[file['id']])
    row=(row[0],row[1],[case],[file])
    assert len(evaluate(row,item)['recommendations'])==1
    other={**case,'partner_id':'foreign-owner'}
    assert not evaluate((row[0],row[1],[other],[file]),item)['recommendations']
    # A visible case omitted from the actual payload cannot be cited by ID.
    assert not evaluate((row[0],row[1],[],[]),item)['recommendations']


@pytest.mark.parametrize('mutation',['withdrawn','changed','deleted','older_word'])
def test_recall_and_detail_never_restore_invalid_source_versions(setup,mutation):
    if mutation=='older_word':
        from .support.profile_report_fixture import document
        old=upload(setup,'old.docx',document(extra='NovelVision专有技术。'),True)
        upload(setup,'new.docx',document(extra='另一项新事实。'),True)
    else:old=upload(setup,'old.txt','NovelVision专有技术。')
    with get_db() as conn:
        first=partner_match_context.recall_candidates(conn,'需要NovelVision伙伴',{})
        if mutation=='older_word':
            assert not first
            return
        assert first and first[0]['hits']
        if mutation=='withdrawn':conn.execute("UPDATE partner_profile_sources SET state='failed' WHERE source_id=?",(old,))
        elif mutation=='changed':conn.execute("UPDATE partner_documents SET extracted_text=? WHERE id=?",('改变后的事实。',old))
        else:conn.execute("DELETE FROM partner_documents WHERE id=?",(old,))
        assert partner_match_context.recall_candidates(conn,'需要NovelVision伙伴',{})==[]
        context=partner_match_context.detailed_candidate(conn,setup[3],'短提示','需要NovelVision伙伴',hits=first[0]['hits'])[1]
    assert not context['profilePassages'] and not context['inputCoverage']['complete']
    assert all(x['reason']=='source_position_unavailable' for x in context['inputCoverage']['omissions'])


def test_hit_offsets_survive_normalization_and_exact_duplicate_contributions(setup):
    fid=upload(setup,'aliases.txt','原始技术方向\n具备Research and Development及AI视觉分析能力。')
    with get_db() as conn:
        value=profile_sources.matching_values(conn,setup[3])[0]
        # Exact duplicate positions alone are deduplicated; another source stays distinct.
        conn.execute('UPDATE partner_profile_sources SET sections_json=? WHERE source_id=?',
                     (json.dumps([{'chapter':5,'quotes':[value['text'],value['text']]}],ensure_ascii=False),fid))
        selected=partner_match_context.recall_candidates(conn,'需要人工智能研发伙伴',{})[0]
        values={ (v['sourceRef'],v['source_version'],v['path']):v for v in profile_sources.matching_values(conn,setup[3])}
        hit_texts=[values[(h['sourceRef'],h['source_version'],h['path'])]['text'][h['start']:h['end']] for h in selected['hits'] if h['sourceRef']!='partner:'+setup[3]]
        assert any(x.lower()=='research and development' for x in hit_texts)
        assert 'AI' in hit_texts
        context=partner_match_context.detailed_candidate(conn,setup[3],'短提示','需要人工智能研发伙伴',hits=selected['hits'])[1]
    assert context['inputCoverage']['complete']
    doc_groups=[g for g in context['_groups'] if any(context['_sourceMap'][key]['sourceRef'].startswith('document:') for key in g['sources'])]
    assert len(doc_groups)==1
    assert all(set(h)=={'sourceRef','source_version','path','start','end'} for h in selected['hits'])
    assert not any(k.startswith('_') for k in partner_match_context.provider_context(context))


def test_whole_group_budget_loss_retains_other_candidate_and_model_gap(setup):
    row=legal_row(setup,'NovelVision方向\n\n企业自述，待核实。\n具备视觉检测能力。')
    item=legal_item(row)
    other=make_partner('oversized-other','超长合成伙伴')
    source = 'partner:oversized-other:profile:0'
    body = 'NovelVision方向\\n' + '企业自述。' * 6000 + '\\n仅限规划，尚未交付。'
    bad_context = {'partnerId':other['id'],'name':other['name'],
        'capabilities':'','industries':'','regions':'','profilePassages':[{'source':source,'text':body}],
        'visibleCases':[],'deliverables':[],'inputCoverage':{'complete':True,'omissions':[],
            'hitCount':1,'hitGroupCount':1,'selectedGroupCount':1,'omittedHitGroups':0},
        '_groups':[{'sources':[source],'hitIndexes':[0],'size':len(body),'priority':0}],
        '_sourceMap':{source:{'partnerId':other['id'],'sourceRef':'document:synthetic-oversized',
            'source_version':'synthetic','path':'/text','start':0,'end':len(body),'text':body}}}
    bad=(other,bad_context,[],[])
    config={'base_url':'https://api.deepseek.com','model_name':'deepseek-v4-flash',
            'api_key':'offline-only','max_tokens':4096,'temperature':0.3,'top_p':1}
    partner_match_context.assemble_details([row,bad],config,
        lambda rows:match._detail_content('需要NovelVision视觉检测',{'understanding':{'facts':{}}},rows),
        match_understanding.MatchAnswer.model_json_schema())
    assert row[1]['profilePassages'] and row[1]['inputCoverage']['complete']
    assert not bad_context['profilePassages'] and not bad_context['_sourceMap']
    assert not bad_context['inputCoverage']['complete']
    assert any(e['reason']=='primary_evidence_budget' and e['hitIndexes']==[0]
               for e in bad_context['inputCoverage']['omissions'])
    item=legal_item(row)  # Use actual sent short IDs.
    recs=match._validated_recommendations([item],[row[0]],{row[0]['id']:[]},{row[0]['id']:[]})
    result=match._validated_outcome(recs,{'recommendations':[item],'supplyStatus':'sufficient',
                                         'gapAnalysis':'模型具体指出条件缺口。'},False,[row,bad])
    assert len(result['recommendations'])==1 and result['supplyStatus']=='sufficient'
    assert not result['analysisComplete'] and '模型具体指出条件缺口。' in result['gapAnalysis']


def test_novel_machine_vision_title_body_and_table_header_are_adjacent(setup):
    body='NovelVision机器视觉检测\n\n| 原始字段 | 原始限制 |\n| --- | --- |\n| 检测方案 | 企业自述，暂无交付 |\n仅限平面图像，不能判断立体尺寸。'
    row=legal_row(setup,body)
    passages=row[1]['profilePassages']
    assert len(passages)==1 and passages[0]['text']==body
    assert '原始字段' in passages[0]['text']
    assert '原始限制' in passages[0]['text']
    assert '企业自述' in passages[0]['text']
    assert '不能判断立体尺寸' in ''.join(p['text'] for p in passages)
    assert row[1]['inputCoverage']['complete']


def test_original_paraphrase_and_added_condition_preserve_evidence_positions(setup):
    upload(setup,'synonym.txt','现有AI客户分析方案，支持人工智能业务咨询。')
    requests=['需要人工智能客户分析服务伙伴。','寻找AI客户分析合作伙伴。',
              '寻找AI客户分析合作伙伴，必须现场交付。']
    with get_db() as conn:
        choices=[partner_match_context.recall_candidates(conn,r,{}) for r in requests]
    assert all(c and c[0]['partnerId']==setup[3] for c in choices)
    # Equivalent wording preserves the actual evidence range, without score/order rules.
    assert set(tuple(h.values()) for h in choices[0][0]['hits']) == set(tuple(h.values()) for h in choices[1][0]['hits'])
    assert set(tuple(h.values()) for h in choices[1][0]['hits']) <= set(tuple(h.values()) for h in choices[2][0]['hits'])


def test_heating_zero_recall_is_unknown_without_detailed_model(setup,monkeypatch):
    from backend.app import development_model
    upload(setup,'ordinary-office.txt','普通软件服务与办公系统维护。')
    snapshot={'_task_id':'synthetic-no-progress','understanding':{'facts':{}},'model':{}}
    def forbidden(*args,**kwargs):raise AssertionError('zero recall must not invoke detailed model')
    monkeypatch.setattr(development_model,'completion',forbidden)
    recs=match._perform_partner_match('区域供热管网水力平衡与换热站调试服务。',snapshot)
    assert recs==[] and snapshot['outcome']['supplyStatus']=='unknown'
    assert snapshot['outcome']['analysisComplete']


@pytest.mark.parametrize('case_index',[0,1,2])
def test_fixed_historic_specialist_projection_passes_persists_and_displays(client,case_index):
    path=Path(os.environ['BANFEI_MATCH_REPLAY_INPUT'])
    replay=json.loads(path.read_text())
    case=replay['cases'][case_index]
    rows,items=[],[]
    for entry in case['inputs']:
        p=entry['partner']
        make_partner(p['id'],p['name'])
        with get_db() as conn:
            conn.execute('UPDATE partners SET capabilities=?,industries=?,service_areas=? WHERE id=?',
                         (p.get('capabilities',''),p.get('industries',''),p.get('service_areas',''),p['id']))
        # These are the saved actual-sent projections, not current DB source fill-in.
        rows.append((p,entry['context'],entry['cases'],entry['deliverables']))
        items.append(entry['item'])
    reasons=[]
    recs=match._validated_recommendations(items,[r[0] for r in rows],
        {r[0]['id']:r[2] for r in rows},{r[0]['id']:r[3] for r in rows},reasons)
    result=match._validated_outcome(recs,{'recommendations':items,'supplyStatus':'partial',
                                        'gapAnalysis':'固定旧输出的合法层回放，不能作为新模型业务正确性证明。'},
                                   bool(reasons),rows,requirement=case['requirement'],facts=case['facts'])
    assert not reasons and len(recs)==len(items) and result['analysisComplete']
    owner=make_user('historic-replay-owner')
    task=make_task(owner,case['requirement'])
    snapshot={'candidate_stamp':match._candidate_stamp(),'outcome':result}
    match._set_task_state(task,'ready',recommendations=recs,snapshot=snapshot)
    with get_db() as conn:
        stored=conn.execute('SELECT recommendations_json FROM match_records WHERE id=?',(task,)).fetchone()[0]
        assert json.loads(stored)==result['recommendations']
    public=client.get('/agent/tasks/'+task,headers=auth_headers(owner))
    assert public.status_code==200
    assert public.json()['recommendations']==result['recommendations']
    assert all(i['recommendationReason'] in public.json()['answer'] for i in items)


def test_prompt_delegates_semantics_without_specialist_whitelist():
    prompt=matching.detail_messages('{}')[0]['content']
    assert all(x in prompt for x in ['末尾条件','必备和排除条件应按原意执行','逐字连续','不与 evidenceType 机械对应'])
    assert not any(x in prompt for x in ['Oracle','GaussDB','EDA','PCB','DDoS','药物研发'])
    assert not any(hasattr(matching,name) for name in
                   ['core_anchors','related_to_core','planning_context','project_wording','requires_case_history','evidence_reason'])


def test_duplicate_id_cannot_reuse_another_item_classification_or_bad_sources(setup,monkeypatch):
    from backend.app import development_model
    upload(setup,'duplicate-card.txt','具备NovelVision视觉检测能力。')
    owner=make_user('duplicate-card-owner')
    def complete(config,messages,schema):
        if schema['title']=='MatchUnderstanding':
            return json.dumps({'in_scope':True,'facts':{'technicalNeeds':'NovelVision','businessNeeds':'需要NovelVision视觉检测伙伴。'}})
        data=json.loads(messages[-1]['content'])
        assert messages[-1]['content'].count('需要NovelVision视觉检测伙伴。')==1
        c=data['candidates'][0];p=c['profilePassages'][-1]
        good={**recommendation(),'partnerId':c['partnerId'],'partnerName':c['name'],
              'matchScore':'70','recommendationReason':'合法原文支持的条目。',
              'evidenceType':'current_capability','profileEvidence':[{'source':p['source'],'quote':p['text']}],
              'evidenceCases':[],'evidenceDeliverables':[]}
        bad={**good,'matchScore':'99','recommendationReason':'非法引用的高分条目。',
             'profileEvidence':[{'source':p['source'],'quote':'虚构资料引用。'}]}
        return json.dumps({'recommendations':[bad,good],
                           'supplyStatus':'sufficient','gapAnalysis':'虚构资料引用。'})
    monkeypatch.setattr(development_model,'completion',complete)
    task=match.create_task(match.TaskCreateRequest(requestId=uuid4(),requirement='需要NovelVision视觉检测伙伴。'),owner)
    match.executor.shutdown(wait=True)
    with get_db() as conn: saved=match_understanding.load(conn,task.recordId)
    result=saved['outcome']
    assert len(result['recommendations'])==1 and result['recommendations'][0]['matchScore']=='70'
    assert '非法引用' not in result['answer'] and '虚构资料引用' not in result['gapAnalysis']
    assert result['supplyStatus']=='sufficient' and not result['analysisComplete']
