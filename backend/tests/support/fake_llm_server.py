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
    stage = _stage(payload.get("messages") or [])
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
