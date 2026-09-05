"""Recommendation identity, score and partner-owned evidence boundaries."""
import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from backend.app.database import get_db
from backend.app.routers import match
from .conftest import auth_headers, make_partner, make_task, make_user, recommendation


def fake_match(monkeypatch, items):
    observed = {}
    def complete(messages, **kwargs):
        observed["messages"] = messages
        return json.dumps(items, ensure_ascii=False)
    monkeypatch.setattr(match, "chat_completion", complete)
    return observed


def add_evidence(partner_id="partner-1", suffix="1", *, title="制造知识库案例", filename="方案文档.pdf"):
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("INSERT INTO cases (id, partner_id, title, description, created_at) VALUES (?, ?, ?, '合成案例', ?)", (f"case-{suffix}", partner_id, title, now))
        conn.execute("INSERT INTO deliverables (id, case_id, filename, file_path, created_at) VALUES (?, ?, ?, '/tmp/synthetic-only.pdf', ?)", (f"file-{suffix}", f"case-{suffix}", filename, now))


def test_scores_sorted_unique_limited_and_best_duplicate_kept(monkeypatch):
    items = []
    for index in range(8):
        pid, name = f"partner-{index}", f"候选{index}"
        make_partner(pid, name)
        items.append({**recommendation(pid, name), "matchScore": str(70 + index)})
    items.extend([{**items[0], "matchScore": "99"}, {**items[1], "matchScore": "NaN"}])
    fake_match(monkeypatch, items)
    recs = match._perform_partner_match("测试需求")
    assert len(recs) == 5
    assert len({rec.partnerId for rec in recs}) == 5
    assert [rec.matchScore for rec in recs] == ["99", "77", "76", "75", "74"]


@pytest.mark.parametrize("score", ["NaN", "Infinity", "-Infinity", "", "92分", -1, 101, True, None, {}, []])
def test_invalid_score_cannot_be_a_recommendation(monkeypatch, score):
    make_partner()
    fake_match(monkeypatch, [{**recommendation(), "matchScore": score}])
    with pytest.raises(HTTPException) as exc:
        match._perform_partner_match("测试需求")
    assert exc.value.status_code == 502
    assert "结果处理失败" in exc.value.detail


@pytest.mark.parametrize("score,expected", [(0, "0"), (100, "100"), (" 83.5 ", "83.5")])
def test_boundary_and_decimal_scores_remain_valid(monkeypatch, score, expected):
    make_partner()
    fake_match(monkeypatch, [{**recommendation(), "matchScore": score}])
    assert match._perform_partner_match("需求")[0].matchScore == expected


def test_active_identity_is_required_and_ambiguous_names_cannot_fallback(monkeypatch):
    make_partner("p-a", "重名伙伴")
    make_partner("p-b", "重名伙伴")
    make_partner("p-c", "唯一名称")
    make_partner("p-disabled", "停用伙伴")
    with get_db() as conn:
        conn.execute("UPDATE partners SET status = 'disabled' WHERE id = 'p-disabled'")
    items = [
        recommendation("missing", "唯一名称"),
        recommendation("p-disabled", "停用伙伴"),
        recommendation("p-a", "唯一名称"),
        recommendation("", "重名伙伴"),
        recommendation("", "唯一名称"),
    ]
    fake_match(monkeypatch, items)
    recs = match._perform_partner_match("需求")
    assert [rec.partnerId for rec in recs] == ["p-c"]


def test_only_owned_references_are_displayed_as_canonical_labels(monkeypatch):
    make_partner()
    make_partner("other", "其他伙伴")
    add_evidence()
    add_evidence("other", "other", title="其他伙伴机密案例", filename="其他交付物.pdf")
    observed = fake_match(monkeypatch, [{
        **recommendation(), "evidenceCases": ["case-1", "case-other", "fictional"],
        "evidenceDeliverables": ["file-1", "file-other", "fictional"],
    }])
    rec = match._perform_partner_match("需求")[0]
    assert rec.evidenceCases == "制造知识库案例"
    assert rec.evidenceDeliverables == "方案文档.pdf（案例：制造知识库案例）"
    assert "其他伙伴机密案例" not in rec.model_dump_json()
    assert "fictional" not in rec.model_dump_json()
    context = observed["messages"][1]["content"]
    assert "交付物ID: file-1" in context and "方案文档.pdf" in context
    assert "/tmp/synthetic-only.pdf" not in context


def test_exact_legacy_names_work_but_fabricated_narratives_do_not(monkeypatch):
    make_partner()
    add_evidence()
    fake_match(monkeypatch, [{**recommendation(), "evidenceCases": "制造知识库案例", "evidenceDeliverables": "方案文档.pdf"}])
    rec = match._perform_partner_match("需求")[0]
    assert rec.evidenceCases == "制造知识库案例" and rec.evidenceDeliverables.startswith("方案文档.pdf")
    fake_match(monkeypatch, [{**recommendation(), "evidenceCases": "制造知识库案例已实现全球领先成果", "evidenceDeliverables": "凭空编造的成果"}])
    rec = match._perform_partner_match("需求")[0]
    assert rec.evidenceCases == "未提供可核实的支撑案例"
    assert rec.evidenceDeliverables == "未提供可核实的支撑交付物"
    assert "全球领先" not in rec.model_dump_json()
    assert "初步匹配" in rec.recommendationReason
    assert "缺少可核实的支撑案例" in rec.riskNotes


def test_ambiguous_evidence_names_need_ids(monkeypatch):
    make_partner()
    add_evidence(suffix="1")
    add_evidence(suffix="2")
    fake_match(monkeypatch, [{**recommendation(), "evidenceDeliverables": "方案文档.pdf"}])
    rec = match._perform_partner_match("需求")[0]
    assert rec.evidenceCases == "未提供可核实的支撑案例"
    assert rec.evidenceDeliverables == "未提供可核实的支撑交付物"


def test_unsupported_match_attributes_and_empty_risks_are_replaced(monkeypatch):
    make_partner()
    fake_match(monkeypatch, [{**recommendation(), "matchedCapabilities": ["AI", "虚构认证"],
                             "matchedIndustries": {"raw": "internal"}, "riskNotes": "无风险"}])
    rec = match._perform_partner_match("需求")[0]
    assert rec.matchedCapabilities == "AI"
    assert rec.matchedIndustries == "未核实"
    assert "虚构认证" not in rec.model_dump_json() and "internal" not in rec.model_dump_json()
    assert "缺少可核实的支撑交付物" in rec.riskNotes


@pytest.mark.parametrize("reason", [None, " ", {}, ["raw JSON"]])
def test_missing_or_nontext_reasons_are_rejected(monkeypatch, reason):
    make_partner()
    fake_match(monkeypatch, [{**recommendation(), "recommendationReason": reason}])
    with pytest.raises(HTTPException):
        match._perform_partner_match("需求")


def test_snake_case_and_wrapped_legacy_results_still_work(monkeypatch):
    make_partner()
    import re
    legacy = {re.sub(r"(?<!^)(?=[A-Z])", "_", k).lower(): v for k, v in recommendation().items()}
    fake_match(monkeypatch, {"recommendations": [None, legacy]})
    assert match._perform_partner_match("需求")[0].partnerId == "partner-1"


def test_new_task_persists_only_validated_results_without_rewriting_history(client, monkeypatch):
    user = make_user("recommendation_owner")
    make_partner()
    old_id = make_task(user, "historical evidence unchanged")
    with get_db() as conn:
        old = dict(conn.execute("SELECT * FROM match_records WHERE id = ?", (old_id,)).fetchone())
    fake_match(monkeypatch, [recommendation(), recommendation(), {**recommendation(), "matchScore": "secret-raw-invalid"}])
    def finish(record_id, *_args, **_kwargs):
        match._set_task_state(record_id, "ready")
        return "ready"
    monkeypatch.setattr(match, "_run_task_enrichment", finish)
    response = client.post("/agent/match", headers=auth_headers(user), json={"requirement": "NEW-VALIDATED"})
    assert response.status_code == 200
    assert len(response.json()["recommendations"]) == 1
    assert "secret-raw-invalid" not in response.text
    with get_db() as conn:
        new = conn.execute("SELECT recommendations_json FROM match_records WHERE id = ?", (response.json()["recordId"],)).fetchone()
        assert json.loads(new[0]) == response.json()["recommendations"]
        assert dict(conn.execute("SELECT * FROM match_records WHERE id = ?", (old_id,)).fetchone()) == old
