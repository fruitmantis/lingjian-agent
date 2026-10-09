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


def fixture_result(ctx,complete=True,risk=''):
    with match.get_db() as conn:
        partner=dict(conn.execute('SELECT * FROM partners WHERE id=?',(ctx[3],)).fetchone())
    fact='某项目仅限平面图像，不能判断立体尺寸。'
    row=raw_row(partner,[fact]);row[1]['inputCoverage']['complete']=complete
    item={**recommendation(),'partnerId':partner['id'],'partnerName':partner['name'],
        'recommendationReason':'建议联系该伙伴承担平面视觉检测环节。'+fact,
        'matchedCapabilities':'不存在的正式标签','matchedIndustries':'','matchedRegions':'',
        'riskNotes':risk,'evidenceCases':[],'evidenceDeliverables':[],
        'evidenceType':'current_capability',
        'profileEvidence':[{'source':row[1]['profilePassages'][0]['source'],'quote':fact}]}
    return partner,row,item


@pytest.mark.parametrize('complete',[True,False])
@pytest.mark.parametrize('risk',['','确认部署环境和接口版本。'])
def test_fixed_output_preserves_roles_facts_and_diagnostics_without_automatic_copy(setup,complete,risk):
    partner,row,item=fixture_result(setup,complete,risk)
    recs=match._validated_recommendations([item],[partner],{partner['id']:[]},{partner['id']:[]})
    result=match._validated_outcome(recs,{'recommendations':[item],'supplyStatus':'sufficient','gapAnalysis':''},False,[row])
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
        item['profileEvidence'][0]['quote']='从未发送的事实。'
        rows=[row];items=[item]
        recs=match._validated_recommendations(items,[partner],{partner['id']:[]},{partner['id']:[]})
    result=match._validated_outcome(recs,{'answer':'未校验的模型答复。','recommendations':items,
        'supplyStatus':'sufficient','gapAnalysis':'未校验的引用结论。' if items else ''},False,rows)
    assert result['recommendations']==[] and result['answer']=='本次暂无正式推荐。'
    assert result['gapAnalysis']=='' and result['supplyStatus']=='unknown'
    assert result['analysisComplete'] is (mode=='empty')


def test_actual_prompt_and_gap_contract_use_direct_facts_and_keep_explicit_conditions(setup):
    partner,row,_=fixture_result(setup)
    requirement='必须本地部署，排除公有云；预算未知。'
    content=match._detail_content(requirement,{'understanding':{'facts':{'onsiteRequirement':'必须本地部署','cloudPlatformPreference':'排除公有云'}}},[row])
    messages=matching.detail_messages(content)
    payload=completion_payload(model_config_from_record(CONFIG),messages,MatchAnswer.model_json_schema())
    prompt=payload['messages'][0]['content'];data=json.loads(payload['messages'][1]['content'])
    assert data['requirement']==requirement and data['facts']['onsiteRequirement']=='必须本地部署'
    assert '用户明确提出的必备和排除条件应按原意执行' in prompt
    assert '真实项目或主体' in prompt and '直接陈述有依据的事实' in prompt
    assert '不添加推责、过度保守或否定式兜底套话' in prompt and '保留完整业务名称与实际限定' in prompt
    assert '删除全部免责声明' not in prompt
    assert 'riskNotes 只确认为该伙伴建议的角色的交付范围、业务场景适配及协作接口' in prompt
    assert 'gapAnalysis 只写组合分工和跨伙伴缺项' in prompt and '两项无内容则空字符串' in prompt
    assert '资料未说明不等于不具备' not in prompt
    parsed=MatchAnswer.model_validate({'recommendations':[],'supplyStatus':'unknown'})
    assert 'answer' not in MatchAnswer.model_json_schema()['properties']
    assert parsed.gapAnalysis==''
    evidence=os.getenv('BANFEI_MATCH_OUTPUT_EVIDENCE_DIR')
    if evidence:Path(evidence,'ACTUAL_OFFLINE_PROVIDER_PAYLOAD.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2))



def test_layout_only_model_quotes_keep_cards_and_overall_division(setup):
    partner,_,item=fixture_result(setup)
    fact='该项目以小程序为入口，接入会员系统。\n指标包括活动报\n名数；效果未独立验证。'
    row=raw_row(partner,[fact])
    key=row[1]['profilePassages'][0]['source']
    item['profileEvidence']=[{'source':key,'quote':'指标包括活动报名数；效果未独立验证。'}]
    output={'recommendations':[item],'supplyStatus':'partial',
            'gapAnalysis':'建议由验证伙伴负责会员场景，仍需寻找数据治理协作方。'}
    rejected=[]
    assert match._source_assessment(item,row)=='current_capability'
    recs=match._validated_recommendations([item],[partner],{partner['id']:[]},{partner['id']:[]},rejected)
    final=match._validated_outcome(recs,output,bool(rejected),[row])
    assert not rejected and len(final['recommendations'])==1
    assert final['answer']==final['gapAnalysis']==output['gapAnalysis']
    assert item['profileEvidence'][0]['quote']=='指标包括活动报\n名数；效果未独立验证。'


def test_detail_prompt_keeps_group_subject_and_card_field_responsibilities():
    prompt=matching.detail_messages('')[0]['content']
    assert '候选伙伴名称不等于资料每项事实的主体' in prompt
    assert '按资料明确写出实际主体' in prompt and '集团背景仍可说明合作价值' in prompt
    assert '卡片和整体分工均保留这一主体关系' in prompt
    assert '末尾再核实签约主体不能修正前面错误的事实归属' in prompt
    assert '保留原生换行、空格和制表符' in prompt
    assert 'recommendationReason 只写有据事实、建议角色和联系角色' in prompt
    assert '同一沟通事项只在 riskNotes 呈现一次' in prompt
    assert '其他角色能力由对应伙伴沟通' in prompt
