"""Finite v3 request budgeting and subtraction checks; isolated PG, no models."""
import copy
import json
import pytest
from backend.app import match_understanding, partner_match_context
from backend.app.routers import match
from backend.app.task_failures import MatchInputBudgetError
from .conftest import make_partner, recommendation

CONFIG = {'base_url':'https://api.deepseek.com','model_name':'deepseek-v4-flash',
          'api_key':'offline-only','max_tokens':4096,'temperature':0.3,'top_p':1}

def raw_row(partner, texts):
    pid = partner['id']
    passages, groups, mapping = [], [], {}
    for i, text in enumerate(texts):
        key = f'partner:{pid}:profile:{i}'
        passages.append({'source':key,'text':text})
        mapping[key] = {'partnerId':pid,'sourceRef':f'document:{pid}:{i}',
            'source_version':'synthetic-original','path':'/text','start':0,'end':len(text),'text':text}
        groups.append({'sources':[key],'hitIndexes':[i],'size':len(text),'priority':i})
    return (partner, {'partnerId':pid,'name':partner['name'],'capabilities':'','industries':'','regions':'',
        'profilePassages':passages,'visibleCases':[],'deliverables':[],
        'inputCoverage':{'complete':True,'hitCount':len(texts),'hitGroupCount':len(texts),
            'selectedGroupCount':len(texts),'omittedHitGroups':0,'omissions':[]},
        '_groups':groups,'_sourceMap':mapping}, [], [])

def assemble(rows, facts=None):
    return partner_match_context.assemble_details(rows, CONFIG,
        lambda selected:match._detail_content('完整需求，必须保留最后条件。',
            {'understanding':{'facts':facts or {}}}, selected),
        match_understanding.MatchAnswer.model_json_schema())

def test_v3_fixed_request_counts_system_schema_and_fields_before_selection(monkeypatch):
    row = raw_row({'id':'fixed-only','name':'固定内容伙伴'}, ['真实主要依据，企业自述，仅限规划。'])
    row[1]['capabilities'] = 'X' * (partner_match_context.DETAIL_CHAR_LIMIT - 1000)
    measures = []
    original = partner_match_context.input_metrics
    def observe(config, messages, schema):
        value = original(config, messages, schema)
        measures.append((value, json.loads(messages[1]['content']), schema['title']))
        return value
    monkeypatch.setattr(partner_match_context,'input_metrics',observe)
    with pytest.raises(MatchInputBudgetError):
        assemble([row], {'onsiteRequirement':'必须驻场','followUpQuestions':['不能入模'],
                         'futureDiagnostics':'不能入模'})
    assert measures[0][0][0] > partner_match_context.DETAIL_CHAR_LIMIT
    assert all(not m[1]['candidates'][0]['profilePassages'] for m in measures)
    assert measures[0][1]['requirement'] == '完整需求，必须保留最后条件。'
    assert measures[0][1]['facts'] == {'onsiteRequirement':'必须驻场'}
    assert measures[0][2] == 'MatchAnswer'
    assert not row[1]['_sourceMap']

def test_v3_primary_groups_survive_private_diagnostics_and_routine_budget_selection():
    first = raw_row({'id':'first','name':'候选甲'},
                    ['甲的主要依据\n企业自述，仅限规划，尚未交付。',
                     '甲的补充背景\n' + '背景' * 14000 + '\n仅限内部验证。'])
    second = raw_row({'id':'second','name':'候选乙'},
                     ['乙的主要依据\n适用于当前版本，参与方式仍需确认。'])
    first[1]['futureDiagnostics'] = 'private-' * 10000
    first[1]['inputCoverage']['omissions'] = [
        {'reason':'selection_budget','hitIndexes':[100+i],'internalPosition':'private-' * 80}
        for i in range(1000)]
    rows = [first,second]
    config, chars, tokens = assemble(rows)
    payload = json.loads(match._detail_content('完整需求，必须保留最后条件。',
                       {'understanding':{'facts':{}}}, rows))
    assert 0 < chars <= partner_match_context.DETAIL_CHAR_LIMIT and tokens > 0
    assert first[1]['inputCoverage']['complete'] and second[1]['inputCoverage']['complete']
    assert first[1]['inputCoverage']['budgetSkippedGroups'] == 1
    assert len(first[1]['inputCoverage']['omissions']) == 1001
    assert '尚未交付' in first[1]['profilePassages'][0]['text']
    assert '参与方式仍需确认' in second[1]['profilePassages'][0]['text']
    assert not any('inputCoverage' in c or 'futureDiagnostics' in c for c in payload['candidates'])
    assert 'internalPosition' not in json.dumps(payload) and 'hitIndexes' not in json.dumps(payload)
    for row in rows:
        assert set(row[1]['_sourceMap']) == {p['source'] for p in row[1]['profilePassages']}
    assert len(first[1]['_sourceMap']) == 1

def test_v3_empty_model_risk_stays_empty_without_generic_case_or_schedule_risks():
    partner = make_partner('v3-open-advice','合成协作伙伴')
    row = (partner,{'inputCoverage':{'complete':True},'_sourceMap':{},'profilePassages':[]},[],[])
    item = {**recommendation(),'partnerId':partner['id'],'partnerName':partner['name'],
        'matchedCapabilities':'','matchedIndustries':'','matchedRegions':'',
        'recommendationReason':'合成离线顾问建议，仅验证合法层与展示。',
        'riskNotes':'','evidenceType':'current_capability','profileEvidence':[],
        'evidenceCases':[],'evidenceDeliverables':[]}
    recs = match._validated_recommendations([item],[partner],{partner['id']:[]},{partner['id']:[]})
    result = match._validated_outcome(recs,{'recommendations':[item],'supplyStatus':'sufficient',
        'gapAnalysis':'合成离线结果不代表业务判断已通过。'},False,[row])
    assert len(recs)==1 and recs[0].riskNotes==''
    assert '需核实：' not in result['answer'] and result['analysisComplete']
    bad = {**item,'matchedCapabilities':'不存在的标签'}
    bad_recs = match._validated_recommendations([bad],[partner],{partner['id']:[]},{partner['id']:[]})
    assert bad_recs[0].matchedCapabilities=='' and bad_recs[0].riskNotes==''  # Unavailable formal labels stay excluded without filler copy.



def test_native_wrapped_fact_and_table_are_continuous_with_original_headings():
    original = '# 项目介绍\n\n01\n检测范围\n采用多角度设备进行\n连续检测。\n\n数据表\n名称\t范围\n设备甲\t仅限表面\n设备乙\t保留日期\n'
    start = original.index('多角度')
    ranges = partner_match_context._group_ranges(original,start,start+3)
    assert len(ranges)==1
    assert '采用多角度设备进行\n连续检测。' in original[ranges[0][0]:ranges[0][1]]
    assert '01\n检测范围' in original[ranges[0][0]:ranges[0][1]]
    start=original.index('设备乙')
    ranges=partner_match_context._group_ranges(original,start,start+3)
    assert len(ranges)==1
    assert '名称\t范围\n设备甲\t仅限表面\n设备乙\t保留日期' in original[ranges[0][0]:ranges[0][1]]


def test_additional_evidence_rotates_before_first_candidate_exhausts_budget():
    rows=[raw_row({'id':key,'name':name},[name+'的主要依据。','补充事实。'+char*8000]+
                  (['另一事实。'+char*8000] if key=='a' else []))
          for key,name,char in [('a','甲','A'),('b','乙','B'),('c','丙','C')]]
    _,chars,_=assemble(rows)
    assert chars<=25000
    assert len(rows[0][1]['profilePassages'])==2
    assert len(rows[1][1]['profilePassages'])==2  # Greedy per-partner fill would starve this turn.
    assert all(row[1]['profilePassages'] for row in rows)
    for index,row in enumerate(rows,1):
        assert all(p['source'].startswith(f'P{index}-S') for p in row[1]['profilePassages'])


def test_short_wire_sources_require_sent_set_and_mapping_owner():
    row=raw_row({'id':'owned','name':'合成主体'},['项目事实，仅限指定区域。'])
    assemble([row])
    key=row[1]['profilePassages'][0]['source']
    item={'evidenceType':'delivered_project','profileEvidence':[{'source':key,'quote':'仅限指定区域'}]}
    assert match._source_assessment(item,row)=='delivered_project'
    foreign=copy.deepcopy(row);foreign[1]['_sourceMap'][key]['partnerId']='other'
    assert match._source_assessment(item,foreign) is None
    altered=copy.deepcopy(row);altered[1]['_sourceMap'][key]['text']='不同原文。'
    assert match._source_assessment(item,altered) is None
    assert match._source_assessment({**item,'profileEvidence':[{'source':'P2-S1','quote':'仅限指定区域'}]},row) is None
    assert match._source_assessment({**item,'profileEvidence':[{'source':key,'quote':'项目事实指定区域'}]},row) is None
    legacy=raw_row({'id':'legacy','name':'历史主体'},['原有连续事实。'])
    legacy[1].pop('_sourceMap')
    assert match._source_assessment({'profileEvidence':[{'source':'partner:legacy:profile:0','quote':'连续事实'}]},legacy)=='current_capability'
    legacy[1]['profilePassages'][0]['source']='P1-S1'
    assert match._source_assessment({'profileEvidence':[{'source':'P1-S1','quote':'连续事实'}]},legacy) is None


def test_source_intro_and_fact_stay_distinct_without_selecting_navigation():
    text=('文章标题\n存档形式：网页缓存\n原始URL：https://example.invalid/article\n'
          '证据边界：集团介绍，匿名项目。\n图文限制：保留原件。\n'
          '导航甲\n>导航乙\n>导航丙\n文章标题\n2026 / 01 / 01\n'
          '集团成员在某项目中提供服务。\n项目以移动端作为入口。\n01\n交付细节\n'
          '后续事实，保留原始限定。\n推荐阅读\n2026 / 01 / 02\n其它文章\n')
    start=text.index('后续事实')
    ranges=partner_match_context._merge_ranges(
        partner_match_context._intro_ranges(text)+partner_match_context._group_ranges(text,start,start+4))
    fragments=[text[a:b] for a,b in ranges]
    assert any('集团成员' in p and '移动端' in p for p in fragments)
    assert any('后续事实' in p for p in fragments)
    assert not any('导航甲' in p or '>导航乙' in p or '其它文章' in p for p in fragments)
    assert any('匿名项目' in p for p in fragments)
    assert all(text[a:b] for a,b in ranges)


def test_understanding_asks_only_direction_changing_questions_and_keeps_unknown_names():
    prompt=partner_match_context.matching.understanding_messages('预算和接口未知，希望统一身份。',[], '')[0]['content']
    assert '能给出建议就不补问' in prompt and '会改变当前推荐方向' in prompt
    assert '已经表达的目标不重复索要' in prompt and '客户名、项目名未提供就保持未知' in prompt
    assert '不满足必备条件的接洽线索不能放回正式推荐卡片' in partner_match_context.matching.detail_messages('')[0]['content']


def test_selected_same_source_overlap_merges_exactly_without_losing_group_links():
    row=raw_row({'id':'overlap','name':'同来源验证'},['连续原文。','原文。后续事实。','下一来源保留。'])
    keys=[p['source'] for p in row[1]['profilePassages']]
    first=row[1]['_sourceMap'][keys[0]]
    second=row[1]['_sourceMap'][keys[1]]
    second.update(sourceRef=first['sourceRef'],start=2,end=10)
    # Both ranges come from one literal original: overlap is "原文。".
    original='连续原文。后续事实。'
    first.update(start=0,end=5,text=original[:5])
    second.update(start=2,end=len(original),text=original[2:])
    row[1]['profilePassages'][0]['text']=first['text']
    row[1]['profilePassages'][1]['text']=second['text']
    assemble([row])
    mapping=row[1]['_sourceMap']
    one=[entry for entry in mapping.values() if entry['sourceRef']==first['sourceRef']]
    assert len(one)==1 and one[0]['text']==original
    assert (one[0]['start'],one[0]['end'])==(0,len(original))
    assert len(mapping)==2  # Different source identity is not semantically deduplicated.
    assert all(set(g['sources'])<=set(mapping) for g in row[1]['_groups'])


def test_article_dates_are_not_footer_or_operation_filters():
    text=('标题\n存档形式：网页缓存\n原始URL：https://example.invalid/archive\n'
          '导航\n标题\n2026 / 01 / 01\n项目介绍。\n01\n阶段记录\n'
          '2026 / 01 / 02\n阶段事实保留。\n推荐阅读\n2026 / 01 / 03\n其它文章\n')
    a,b,_=partner_match_context._source_layout(text)
    assert '2026 / 01 / 02\n阶段事实保留。' in text[a:b]
    assert '其它文章' not in text[a:b]


def test_heading_hit_keeps_following_native_paragraph_in_one_range():
    text='# 主题\n\n1\n\n保留完整事实和日期。\n\n# 下一主题\n另一事实。\n'
    a=text.index('1')
    ranges=partner_match_context._group_ranges(text,a,a+1)
    assert len(ranges)==1 and '1\n\n保留完整事实和日期。' in text[ranges[0][0]:ranges[0][1]]
    assert '另一事实' not in text[ranges[0][0]:ranges[0][1]]


def test_title_only_recall_keeps_qualification_and_actual_body():
    text='RareTitle专业服务\n\n企业自述，相关交付经历待核实。\n具备数据分析方案能力。'
    ranges=partner_match_context._group_ranges(text,0,len('RareTitle'))
    assert ranges==[(0,len(text))]
    assert text[ranges[0][0]:ranges[0][1]]==text


@pytest.mark.parametrize(('original','proposed'),[
    ('指标包括活动报\n名数；效果未独立验证。','指标包括活动报名数；效果未独立验证。'),
    ('互动问答、消\r\n费引导、智能查询。','互动问答、消费引导、智能查询。'),
    ('减少查阅\n文档次数。','减少查阅文档次数。'),
    ('原生第一行\r\n第二行事实。','原生第一行\n第二行事实。'),
    ('该能力处于规划阶段，尚未交付。','该能力处于规\n划阶段，尚未交付。'),
])
def test_profile_quote_linebreak_difference_recovers_untouched_continuous_range(original,proposed):
    row=raw_row({'id':'owned','name':'合成主体'},['前言。\n'+original+'\n结尾。'])
    assemble([row])
    key=row[1]['profilePassages'][0]['source']
    item={'evidenceType':'planning_only','profileEvidence':[{'source':key,'quote':proposed}]}
    source_before=copy.deepcopy(row[1])
    assert match._source_assessment(item,row)=='planning_only'
    assert item['profileEvidence'][0]['quote']==original
    assert item['profileEvidence'][0]['quote'] in source_before['profilePassages'][0]['text']
    assert row[1]==source_before  # Source cache/map/versions are not normalized.


@pytest.mark.parametrize(('original','proposed'),[
    ('活动报\n名数尚未独立验证。','活动报名数已独立验证。'),
    ('已形成方案。\n仅为规划，未交付。\n拟用于教学。','已形成方案。拟用于教学。'),
    ('事实甲。\n\n中间限制。\n\n事实乙。','事实甲。事实乙。'),
    ('AI service 支持。','AIservice 支持。'),
    ('阶段\t未来规划','阶段未来规划'),
    ('消⽂档。','消文档。'),
    ('活动报\n名数。','活动报名数！'),
])
def test_profile_quote_keeps_all_non_linebreak_characters_literal(original,proposed):
    row=raw_row({'id':'owned','name':'合成主体'},[original])
    assemble([row])
    key=row[1]['profilePassages'][0]['source']
    item={'profileEvidence':[{'source':key,'quote':proposed}]}
    before=copy.deepcopy(item)
    assert match._source_assessment(item,row) is None
    assert item==before


def test_profile_quote_normalization_does_not_choose_distinct_native_ranges():
    original='活动报\n名数。\n另一个位置：活动报\r\n名数。'
    row=raw_row({'id':'owned','name':'合成主体'},[original])
    assemble([row])
    key=row[1]['profilePassages'][0]['source']
    item={'profileEvidence':[{'source':key,'quote':'活动报名数。'}]}
    assert match._source_assessment(item,row) is None


@pytest.mark.parametrize('invalid',['owner','map_text','case','later_quote'])
def test_profile_quote_recovery_does_not_bypass_identity_or_partially_rewrite_rejected_items(invalid):
    row=raw_row({'id':'owned','name':'合成主体'},['活动报\n名数；效果未独立验证。'])
    assemble([row])
    key=row[1]['profilePassages'][0]['source']
    item={'profileEvidence':[{'source':key,'quote':'活动报名数；效果未独立验证。'}]}
    if invalid=='owner':row[1]['_sourceMap'][key]['partnerId']='other'
    elif invalid=='map_text':row[1]['_sourceMap'][key]['text']='另一份原文。'
    elif invalid=='case':item['evidenceCases']=['not-owned']
    else:item['profileEvidence'].append({'source':key,'quote':'效果已经验证。'})
    before=copy.deepcopy(item)
    assert match._source_assessment(item,row) is None
    assert item==before


def test_profile_quote_recovery_preserves_legacy_source_identity():
    row=raw_row({'id':'legacy','name':'历史主体'},['活动报\n名数；效果未独立验证。'])
    row[1].pop('_sourceMap')
    key=row[1]['profilePassages'][0]['source']
    item={'profileEvidence':[{'source':key,'quote':'活动报名数；效果未独立验证。'}]}
    assert match._source_assessment(item,row)=='current_capability'
    assert item['profileEvidence'][0]['quote']=='活动报\n名数；效果未独立验证。'
    row[1]['profilePassages'][0]['source']='P1-S1'
    assert match._source_assessment({'profileEvidence':[{'source':'P1-S1','quote':item['profileEvidence'][0]['quote']}]},row) is None
