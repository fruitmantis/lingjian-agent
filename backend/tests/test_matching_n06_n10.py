"""N10 retrieval and N06 presentation regressions; isolated PG and synthetic models only."""
import json
from uuid import uuid4

import pytest

from backend.app import development_model, match_understanding, partner_match_context
from backend.app.database import get_db
from backend.app.routers import match
from backend.business import matching
from .conftest import make_partner, make_task, make_user, auth_headers, recommendation
from .test_profile_report import setup, upload


@pytest.mark.parametrize("requirement", [
    "找能协作做软件漏洞修复和应急响应的伙伴。",
    "需要软件漏洞修复和应急响应服务伙伴。",
    "找能协作做软件漏洞修复和应急响应的伙伴，必须驻场。",
])
def test_distributed_n10_terms_reach_same_detail_with_original_and_conditions(setup, monkeypatch, requirement):
    body = "协作环节覆盖：漏洞发现 / 报告 / 修复 / 应急响应\n软件安全服务范围以实际约定为准。"
    upload(setup, "synthetic-security.txt", body)
    for i in range(15):
        make_partner("unmatched-security-" + str(i), "合成无命中" + str(i))
    if requirement.startswith("找能") and "驻场" not in requirement:
        terms, anchors = matching.recall_query(requirement, {})
        parts = next(a["parts"] for a in anchors if len(a["parts"]) > 10)
        # This distributed source failed the former conjunctive ratio before ranking.
        assert sum(t in body for t in parts) < max(2, (len(parts) + 1) // 2)
    calls = []
    owner = make_user("synthetic-security-owner")
    def complete(config, messages, schema):
        calls.append(schema["title"])
        with get_db() as conn:
            assert conn.execute("SELECT requirement FROM match_records WHERE owner_user_id=?",
                                (owner["id"],)).fetchone()[0] == requirement
        if schema["title"] == "MatchUnderstanding":
            return json.dumps({"in_scope": True, "facts": {"technicalNeeds": "软件漏洞修复与应急响应",
                              "onsiteRequirement": "必须驻场" if "驻场" in requirement else "未知"},
                               "tag_suggestions": []}, ensure_ascii=False)
        data = json.loads(messages[-1]["content"])
        assert data["requirement"] == requirement
        assert len(data["candidates"]) == 1
        assert data["candidates"][0]["partnerId"] == setup[3]
        assert "应急响应" in str(data["candidates"][0]["profilePassages"])
        assert "sourceRef" not in str(data["candidates"][0])  # Private range maps stay private.
        if "驻场" in requirement:
            assert data["facts"]["onsiteRequirement"] == "必须驻场"
        # A recall hit never forces a formal recommendation.
        return json.dumps({
                           "recommendations": [], "supplyStatus": "unknown",
                           "gapAnalysis": "本测试不判定实际交付能力。"}, ensure_ascii=False)
    monkeypatch.setattr(development_model, "completion", complete)
    accepted = match.create_task(match.TaskCreateRequest(requestId=uuid4(), requirement=requirement), owner)
    match.executor.shutdown(wait=True)
    with get_db() as conn:
        saved = match_understanding.load(conn, accepted.recordId)
    assert calls == ["MatchUnderstanding", "MatchAnswer"]
    assert saved["outcome"]["recommendations"] == []


def test_n10_retains_original_hit_requirement_stable_rank_and_twelve_candidate_cap(setup):
    for i in range(16):
        pid = "bounded-security-" + str(i).zfill(2)
        make_partner(pid, "合成有限召回" + str(i))
        with get_db() as conn:
            conn.execute("UPDATE partners SET capabilities=? WHERE id=?", ("漏洞修复与应急响应", pid))
    make_partner("unmatched-security", "合成无关伙伴")
    make_partner("disabled-security", "合成停用伙伴")
    with get_db() as conn:
        conn.execute("UPDATE partners SET capabilities=?,status='inactive' WHERE id=?",
                     ("漏洞修复与应急响应", "disabled-security"))
        selected = partner_match_context.recall_candidates(conn, "找能协作做软件漏洞修复和应急响应的伙伴。", {}, limit=99)
        repeated = partner_match_context.recall_candidates(conn, "找能协作做软件漏洞修复和应急响应的伙伴。", {}, limit=99)
        smaller = partner_match_context.recall_candidates(conn, "找能协作做软件漏洞修复和应急响应的伙伴。", {}, limit=3)
    assert selected == repeated and len(selected) == 12 and smaller == selected[:3]
    assert [x["partnerId"] for x in selected] == ["bounded-security-" + str(i).zfill(2) for i in range(12)]
    assert all(x["hits"] and x["recallTerms"] for x in selected)
    assert "unmatched-security" not in str(selected) and "disabled-security" not in str(selected)


def test_n06_natural_gap_retains_actual_omission_legal_card_and_saved_public_output(setup, client):
    upload(setup, "synthetic-visible.txt", "具备NovelVision视觉分析方案。")
    unavailable = upload(setup, "synthetic-omitted.txt", "NovelVision相关实施边界需补充核实。")
    with get_db() as conn:
        selected = partner_match_context.recall_candidates(conn, "需要NovelVision视觉分析伙伴。", {})[0]
        conn.execute("UPDATE partner_profile_sources SET state='failed' WHERE source_id=?", (unavailable,))
        row = partner_match_context.detailed_candidate(conn, setup[3], "短提示",
                "需要NovelVision视觉分析伙伴。", hits=selected["hits"], recall_terms=selected["recallTerms"])
    passage = row[1]["profilePassages"][0]
    coverage = row[1]["inputCoverage"]
    assert coverage["complete"] is False
    assert coverage["omissions"] and all(e["reason"] == "source_position_unavailable" for e in coverage["omissions"])
    sent = json.loads(match._detail_content("需要NovelVision视觉分析伙伴。",
                                           {"understanding": {"facts": {}}}, [row]))
    candidate = sent["candidates"][0]
    assert "inputCoverage" not in candidate and "omissions" not in str(candidate)
    assert "evidenceState" not in candidate
    assert row[1]["evidenceState"] == "部分召回命中的来源位置无法确认，相关片段未能送达。"
    item = {**recommendation(), "partnerId": row[0]["id"], "partnerName": row[0]["name"],
            "matchScore": "67", "recommendationReason": "所见资料自述视觉分析方案，可进一步接洽。",
            "riskNotes": "部分已命中资料未完整展示，方案范围仍需补充核实。",
            "evidenceType": "current_capability",
            "profileEvidence": [{"source": passage["source"], "quote": passage["text"]}],
            "evidenceCases": [], "evidenceDeliverables": []}
    recs = match._validated_recommendations([item], [row[0]], {row[0]["id"]: []}, {row[0]["id"]: []})
    result = match._validated_outcome(recs, {"recommendations": [item], "supplyStatus": "sufficient",
        "gapAnalysis": "部分已命中资料未完整展示，不能确认全部需求已覆盖。"}, False, [row])
    assert len(result["recommendations"]) == 1
    assert result["recommendations"][0]["matchScore"] == "67"
    assert result["recommendations"][0]["riskNotes"].startswith(item["riskNotes"])
    assert not result["analysisComplete"] and result["supplyStatus"] == "sufficient"
    assert "未完整展示" in result["answer"]
    for field in ("answer", "gapAnalysis"):
        assert not any(x in result[field] for x in ("complete=false", "inputCoverage", "global_budget"))
    owner = make_user("synthetic-natural-gap-owner")
    task = make_task(owner, "需要NovelVision视觉分析伙伴。")
    match._set_task_state(task, "ready", recommendations=recs,
                         snapshot={"candidate_stamp": match._candidate_stamp(), "outcome": result,
                                   "detail_input_coverage": {row[0]["id"]: coverage}})
    public = client.get("/agent/tasks/" + task, headers=auth_headers(owner))
    with get_db() as conn:
        stored = match_understanding.load(conn, task)
    assert stored["outcome"]["analysisComplete"] is False
    assert stored["detail_input_coverage"][row[0]["id"]] == coverage
    assert public.status_code == 200
    assert "profileEvidence" not in public.json()["recommendations"][0]
    assert public.json()["recommendations"] == result["recommendations"]
    assert "未完整展示" in public.json()["answer"]


def test_n06_prompt_uses_real_omissions_and_keeps_structured_evidence():
    prompt = matching.detail_messages("{}")[0]["content"]
    assert "只写影响本次判断的缺口，不罗列通用风险，不凑推荐数量" in prompt
    assert "未知保持未知" in prompt and "直接陈述真实项目或主体" in prompt
    assert "删除全部免责声明" not in prompt and "资料未说明不等于不具备" not in prompt
    assert "不添加推责、过度保守或否定式兜底套话" in prompt
    assert "用户明确提出的必备和排除条件应按原意执行" in prompt
    assert "不把规划、协作、奖项或群体介绍说成该伙伴已经完成的具体项目" in prompt
    assert "逐字连续子串" in prompt and "profileEvidence.source" in prompt
    assert prompt.count("根据完整需求和伙伴资料，推荐有具体接洽价值的伙伴") == 1
    assert "inputCoverage" not in prompt and "omissions" not in prompt
