"""Deterministic OpenAI-compatible fake used by process and browser tests."""

import asyncio
import json
import os

from fastapi import FastAPI


app = FastAPI()
_delayed_stages: set[str] = set()


def _stage(messages: list[dict]) -> str:
    system = "\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "system")
    if "交付伙伴匹配专家" in system:
        return "match"
    if "项目需求分析专家" in system:
        return "demand"
    if "从项目需求中抽取结构化项目信息" in system:
        return "opportunity"
    if "找出标准能力标签无法覆盖" in system:
        return "tags"
    return "default"


def _content(stage: str) -> str:
    if stage == "match":
        return json.dumps([{
            "partnerId": "partner-1", "partnerName": "验证伙伴", "matchScore": "92",
            "matchedCapabilities": "AI,数据治理", "matchedIndustries": "制造",
            "matchedRegions": "全国", "recommendationReason": "与验证需求匹配",
            "evidenceCases": "制造知识库案例", "evidenceDeliverables": "方案文档",
            "riskNotes": "需复核交付排期",
        }], ensure_ascii=False)
    if stage == "demand":
        return json.dumps({
            "industryTags": "制造", "capabilityTags": "数据治理", "deliveryTypeTags": "咨询",
            "regionTags": "全国", "complexityLevel": "中", "urgencyLevel": "中",
            "projectKeywords": "知识库,Agent", "supplyStatus": "sufficient", "gapAnalysis": "供给充足",
        }, ensure_ascii=False)
    if stage == "opportunity":
        return json.dumps({
            "customerName": "验证客户", "projectName": "制造知识库 Agent", "industry": "制造",
            "region": "全国", "projectStage": "需求调研", "businessNeeds": "建设知识库",
            "technicalNeeds": "Agent", "deliveryNeeds": "咨询实施", "qualificationRequirements": "未识别",
            "caseRequirements": "制造案例", "onsiteRequirement": "未识别", "timelineRequirement": "未识别",
            "cloudPlatformPreference": "华为云", "followUpQuestions": ["计划时间？"],
        }, ensure_ascii=False)
    if stage == "tags":
        return "[]"
    return "{}"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/chat/completions")
async def completions(payload: dict):
    messages=payload.get('messages') or []
    system=' '.join(m.get('content','') for m in messages if m.get('role')=='system')
    if 'partner_development:' in system:
        data=json.loads(messages[-1]['content'])
        request=data.get('request',data)
        if 'C_SLOW' in request.get('development_goal',''):await asyncio.sleep(3)
        if 'C_FAIL' in request.get('adjustment',''):content='{"invented_url":"https://example.com/invalid"}'
        elif 'diagnose' in system:
            content=json.dumps({'target_partner_id':request['target_partner_id'],'diagnoses':[{'capability_tag_id':t['capability_tag_id'],'target_requirement':t['requirement'],'target_satisfaction':'not_satisfied','evidence_status':'partial','judgment_source':'model_inference','evidence_refs':[],'pending_verifications':['请由发展经理核验人员基础'],'problem_type':'trainable_gap'} for t in request['targets']]},ensure_ascii=False)
        else:
            items=[]
            if 'C_GAP' not in request.get('development_goal',''):
                for candidate in data['candidates'][:6]:
                    tag=next((d['capability_tag_id'] for d in data['diagnoses'] if d['problem_type']=='trainable_gap' and d['capability_tag_id'] in candidate['capability_tag_ids']),None)
                    if tag:items.append({k:candidate[k] for k in ('source_type','source_id','source_version')}|{'capability_tag_id':tag,'reason':'基于目标能力与当前可用资源进行安排','estimated_hours':2,'note':''})
            content=json.dumps({'target_partner_id':request['target_partner_id'],'stages':[{'title':'基础准备与实践验证','items':items}],'limitations':['实施前需核实人员基础和访问条件'],'resource_gaps':[]},ensure_ascii=False)
        return {'choices':[{'message':{'content':content},'finish_reason':'stop'}],'usage':{'completion_tokens':20}}
    stage = _stage(messages)
    if "SIDEBAR_SLOW" in json.dumps(payload.get("messages"), ensure_ascii=False) and stage in {"match", "demand"}:
        await asyncio.sleep(5)
    delay_name = "FAKE_LLM_MATCH_DELAY_SECONDS" if stage == "match" else "FAKE_LLM_ENRICH_DELAY_SECONDS"
    delay = float(os.getenv(delay_name, "0"))
    if delay and stage not in _delayed_stages:
        _delayed_stages.add(stage)
        await asyncio.sleep(delay)
    return {
        "choices": [{"message": {"content": _content(stage)}, "finish_reason": "stop"}],
        "usage": {"completion_tokens": 20},
    }
