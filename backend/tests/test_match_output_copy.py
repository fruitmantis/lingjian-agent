"""Output-copy checks with fixed results and the actual provider prompt, no model calls."""
import json
import os
from pathlib import Path
import pytest
from backend.app.routers import match
from backend.business import matching
from backend.business.matching_types import MatchAnswer
from backend.app.ai_client import completion_payload
from backend.app.model_resolver import model_config_from_record
from .test_profile_report import setup
from .conftest import recommendation
from .test_matching_v3 import raw_row, CONFIG



def canonical_row(partner,fact):
    with match.get_db() as conn:conn.execute('UPDATE partners SET capabilities=? WHERE id=?',(fact,partner['id']))
    partner={**partner,'capabilities':fact}
    row=raw_row(partner,[fact]);source=row[1]['profilePassages'][0]['source']
    row[1]['_sourceMap'][source].update(sourceRef='partner:'+partner['id'],path='/capabilities')
    return row


def fixture_result(ctx,complete=True,risk=''):
    with match.get_db() as conn:
        partner=dict(conn.execute('SELECT * FROM partners WHERE id=?',(ctx[3],)).fetchone())
    fact='某项目仅限平面图像，不能判断立体尺寸。'
    row=canonical_row(partner,fact);row[1]['inputCoverage']['complete']=complete
    item={**recommendation(),'partnerId':partner['id'],'partnerName':partner['name'],
        'recommendationReason':'建议联系该伙伴承担平面视觉检测环节。'+fact,
        'matchedCapabilities':'不存在的正式标签','matchedIndustries':'','matchedRegions':'',
        'riskNotes':risk,'evidenceCases':[],'evidenceDeliverables':[],
        'evidenceType':'current_capability',
        'profileEvidence':[row[1]['profilePassages'][0]['source']]}
    return partner,row,item


@pytest.mark.parametrize('complete',[True,False])
@pytest.mark.parametrize('risk',['','确认部署环境和接口版本。'])
def test_fixed_output_preserves_roles_facts_and_diagnostics_without_automatic_copy(setup,complete,risk):
    partner,row,item=fixture_result(setup,complete,risk)
    recs=match._validated_recommendations([item],[partner],{partner['id']:[]},{partner['id']:[]})
    result=match._validated_outcome(recs,{'recommendations':[item],'supplyStatus':'sufficient','gapAnalysis':'','analysisRefs':[],'_analysis_shape_valid':True},False,[row])
    assert len(result['recommendations'])==1 and result['recommendations'][0]['recommendationReason']==item['recommendationReason']
    assert result['recommendations'][0]['riskNotes']==risk
    assert all(result['recommendations'][0][field]=='' for field in
               ('matchedCapabilities','matchedIndustries','matchedRegions','evidenceCases','evidenceDeliverables'))
    assert result['gapAnalysis']=='' and result['analysisComplete'] is complete
    assert result['supplyStatus']=='sufficient'  # Local diagnostics do not override the model's supply judgment.
    assert '不能判断立体尺寸' in result['recommendations'][0]['recommendationReason']
    assert result['answer']==''  # The reason appears once in its card.
    assert not any(word in result['answer'] for word in ('不能据此','仅供参考','不构成','本次分析不完整','标签未能'))
    if risk:assert risk in result['recommendations'][0]['riskNotes']
    evidence=os.getenv('BANFEI_MATCH_OUTPUT_EVIDENCE_DIR')
    if evidence and complete:
        Path(evidence,'fixed-output-'+('communication' if risk else 'empty')+'.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))


@pytest.mark.parametrize('mode',['empty','invalid_quote'])
def test_missing_or_invalid_results_have_no_default_disclaimer_or_unvalidated_summary(setup,mode):
    rows=[];items=[];recs=[]
    if mode=='invalid_quote':
        partner,row,item=fixture_result(setup)
        item['profileEvidence'][0]='unsent-source'
        rows=[row];items=[item]
        recs=match._validated_recommendations(items,[partner],{partner['id']:[]},{partner['id']:[]})
    result=match._validated_outcome(recs,{'answer':'未校验的模型答复。','recommendations':items,
        'supplyStatus':'sufficient','gapAnalysis':'未校验的引用结论。' if items else '', 'analysisRefs':[],'_analysis_shape_valid':mode=='empty'},False,rows)
    assert result['recommendations']==[] and result['answer']=='本次暂无推荐伙伴。'
    assert result['gapAnalysis']=='' and result['supplyStatus']==('sufficient' if mode=='empty' else 'unknown')
    assert result['analysisComplete'] is (mode=='empty')


def test_actual_prompt_and_gap_contract_use_direct_facts_and_keep_explicit_conditions(setup):
    partner,row,_=fixture_result(setup)
    requirement='必须本地部署，排除公有云；预算未知。'
    content=match._detail_content(requirement,{'understanding':{'facts':{'onsiteRequirement':'必须本地部署','cloudPlatformPreference':'排除公有云'}}},[row])
    messages=matching.detail_messages(content)
    payload=completion_payload(model_config_from_record(CONFIG),messages,MatchAnswer.model_json_schema())
    prompt=payload['messages'][0]['content'];data=json.loads(payload['messages'][1]['content'])
    assert data['requirement']==requirement and data['facts']['onsiteRequirement']=='必须本地部署'
    assert '明确必备条件、资格和排除条件' in prompt and '实际主体' in prompt
    assert '实际主体、集团关系、日期与业务性质' in prompt and '保留真实否定、规划及范围' in prompt
    assert '直接陈述事实与建议' in prompt and '不补通用免责段' in prompt
    assert 'riskNotes只写与该对象相关的必要事项' in prompt and 'gapAnalysis说明整体分工' in prompt
    assert 'analysisRefs列这段分析实际使用的伙伴及引用' in prompt
    parsed=MatchAnswer.model_validate({'recommendations':[],'supplyStatus':'unknown','analysisRefs':[]})
    assert 'answer' not in MatchAnswer.model_json_schema()['properties']
    assert parsed.gapAnalysis==''
    evidence=os.getenv('BANFEI_MATCH_OUTPUT_EVIDENCE_DIR')
    if evidence:Path(evidence,'ACTUAL_OFFLINE_PROVIDER_PAYLOAD.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))



def test_source_ids_keep_native_layout_cards_and_overall_division(setup):
    partner,_,item=fixture_result(setup)
    fact='该项目以小程序为入口，接入会员系统。\n指标包括活动报\n名数；效果未独立验证。'
    row=canonical_row(partner,fact)
    key=row[1]['profilePassages'][0]['source']
    item['profileEvidence']=[key]
    output={'recommendations':[item],'supplyStatus':'partial',
            'gapAnalysis':'建议由验证伙伴负责会员场景，仍需寻找数据治理协作方。','analysisRefs':[],'_analysis_shape_valid':True}
    rejected=[]
    assert match._source_assessment(item,row)=='current_capability'
    recs=match._validated_recommendations([item],[partner],{partner['id']:[]},{partner['id']:[]},rejected)
    final=match._validated_outcome(recs,output,bool(rejected),[row])
    assert not rejected and len(final['recommendations'])==1
    assert final['answer']==final['gapAnalysis']==output['gapAnalysis']
    assert item['_resolvedProfileEvidence']==[{'source':key,'quote':fact}]


def test_detail_prompt_keeps_group_subject_and_card_field_responsibilities():
    prompt=matching.detail_messages('')[0]['content']
    assert '主体、集团关系' in prompt and '实际主体' in prompt
    assert 'recommendationReason说明伙伴事实和建议角色' in prompt
    assert 'riskNotes只写与该对象相关的必要事项' in prompt and 'gapAnalysis说明整体分工' in prompt
    assert 'profileEvidence只选该伙伴已发送的短source编号数组' in prompt
    assert '程序还原原文' in prompt
