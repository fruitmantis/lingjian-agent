"""Deterministic OpenAI-compatible fake used by process and browser tests."""

import asyncio
import json
import os

from fastapi import FastAPI


# This is an isolated regression/fault fixture, never a selectable development model.
# A runtime DATABASE_URL or runtime data directory must fail before a server opens.
from backend.tests.support.model_test_boundary import require_test_database
require_test_database()
app = FastAPI()
_delayed_stages: set[str] = set()


def _stage(messages: list[dict]) -> str:
    system = "\n".join(str(item.get("content", "")) for item in messages if item.get("role") == "system")
    if "一次理解项目找伙伴" in system:
        return "understanding"
    if "项目伙伴 AI 初选" in system:
        return "initial_selection"
    if "交付伙伴匹配顾问" in system:
        return "detailed_review"
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
            "matchedCapabilities": "AI,数据治理", "matchedIndustries": "制造与工业",
            "matchedRegions": "广东", "recommendationReason": "与验证需求匹配",
            "evidenceCases": "制造知识库案例", "evidenceDeliverables": "方案文档",
            "riskNotes": "需复核交付排期",
        }], ensure_ascii=False)
    if stage == "demand":
        return json.dumps({
            "industryTags": "制造与工业", "capabilityTags": "数据治理", "deliveryTypeTags": "咨询",
            "regionTags": "广东", "complexityLevel": "中", "urgencyLevel": "中",
            "projectKeywords": "知识库,Agent", "supplyStatus": "sufficient", "gapAnalysis": "供给充足",
        }, ensure_ascii=False)
    if stage == "opportunity":
        return json.dumps({
            "customerName": "验证客户", "projectName": "制造知识库 Agent", "industry": "制造与工业",
            "region": "广东", "projectStage": "需求调研", "businessNeeds": "建设知识库",
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
    if 'Scope Gate' in system:
        # Explicit replay fixture only; this is NOT production classification or
        # evidence of real-model stability. Unknown synthetic business text passes.
        text=json.loads(next(m['content'] for m in messages if m['role']=='user'))['message']
        off_topic={'明天天气怎么样？','帮我安排三天旅游行程','写一个 Python 快速排序函数','写一首关于月亮的诗'}
        content=json.dumps({'in_scope':text not in off_topic})
        return {'choices':[{'message':{'content':content},'finish_reason':'stop'}]}
    if 'partner_development:' in system:
        from backend.tests.support.development_mock import response
        if 'C_SLOW' in json.dumps(messages,ensure_ascii=False):await asyncio.sleep(3)
        content=json.dumps(response(messages),ensure_ascii=False)
        return {'choices':[{'message':{'content':content},'finish_reason':'stop'}],'usage':{'completion_tokens':20}}
    stage = _stage(messages)
    if stage in {'understanding','initial_selection','detailed_review'}:
        data=json.loads(messages[-1]['content'])
        if stage=='understanding':
            content=json.dumps({'in_scope':True,'facts':json.loads(_content('opportunity')),'tag_suggestions':[]},ensure_ascii=False)
        elif stage=='initial_selection':
            content=json.dumps({'candidates':[{'partnerId':p['partnerId'],'verificationFocus':'核实数据库及知识库交付经验'} for p in data['partners'][:2]]},ensure_ascii=False)
        else:
            items=[]
            for p in data['candidates'][:1]:
                items.append({**json.loads(_content('match'))[0],'partnerId':p['partnerId'],'partnerName':p['name'],'evidenceCases':[],'evidenceDeliverables':[]})
            content=json.dumps({'answer':'根据现有合成资料，建议优先核实以下伙伴。','recommendations':items,'supplyStatus':'partial' if items else 'unknown','gapAnalysis':'交付排期与承接边界待核实'},ensure_ascii=False)
        if 'SIDEBAR_SLOW' in json.dumps(messages,ensure_ascii=False) and stage=='understanding':await asyncio.sleep(5)
        return {'choices':[{'message':{'content':content},'finish_reason':'stop'}],'usage':{'completion_tokens':20}}
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
