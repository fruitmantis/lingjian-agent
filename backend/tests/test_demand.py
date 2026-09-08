import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from backend.app import ai_client
from backend.app.database import get_db
from backend.app.routers import match

from .conftest import auth_headers, make_partner, make_task, make_user, recommendation


COMPLETE_OPPORTUNITY = {
    "customerName": "合成客户", "projectName": "合成项目", "industry": "制造与工业",
    "region": "江苏", "projectStage": "需求调研", "businessNeeds": "合成业务需求",
}


def add_demand(owner, label, recs, *, industry="制造与工业", region="江苏", capability="数据库", old=False, archived=False):
    task_id = make_task(owner, label, recommendations=recs, archived=archived)
    created_at = (datetime.now(timezone.utc) - timedelta(days=60 if old else 0)).isoformat()
    with get_db() as conn:
        conn.execute("UPDATE match_records SET created_at = ? WHERE id = ?", (created_at, task_id))
        conn.execute(
            """INSERT INTO demand_profiles
               (id, match_record_id, requirement_text, industry_tags, region_tags,
                capability_tags, matched_partner_count, supply_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'sufficient', ?)""",
            (f"demand-{task_id}", task_id, label, industry, region, capability, len(recs), created_at),
        )
    return task_id


@pytest.mark.parametrize("enabled_count,expected_supply", [(0, "gap"), (1, "partial"), (3, "sufficient")])
def test_report_counts_distinct_enabled_supply(client, enabled_count, expected_supply):
    admin = make_user("supply_admin", role="admin")
    for i in range(4):
        partner = make_partner(f"supply-{i}", "同名伙伴")
        with get_db() as conn:
            conn.execute(
                "UPDATE partners SET capabilities = '数据库,数据库', status = ? WHERE id = ?",
                ("active" if i < enabled_count else "disabled", partner["id"]),
            )
    add_demand(admin, "supply demand", [])
    response = client.get("/admin/reports", headers=auth_headers(admin))
    assert response.status_code == 200
    report = response.json()
    assert report["overview"]["totalPartners"] == 4
    gap = report["supplyGaps"][0]
    assert gap["partnerCount"] == enabled_count
    assert gap["supplyStatus"] == expected_supply
    assert gap["demandCount"] == 1
    assert report["topFormalTags"] == [{"label": "数据库", "count": 4}]


@pytest.mark.parametrize("query", [
    "days=7", "industry=制造与工业", "region=江苏", "capability=数据库",
    "days=7&industry=制造与工业&region=江苏&capability=数据库",
])
def test_report_activity_uses_filtered_unarchived_demands(client, query):
    admin = make_user("report_admin", role="admin")
    included = make_partner("included", "已更名伙伴")
    excluded = make_partner("excluded", "筛选外伙伴")
    make_partner("unused", "未推荐伙伴")
    # Historical names may differ; a repeated partner in one task counts only once.
    rec = recommendation(included["id"], "历史名称")
    add_demand(admin, "included one", [rec, rec])
    add_demand(admin, "included two", [rec])
    add_demand(admin, "outside filter", [recommendation(excluded["id"], excluded["name"])],
               industry="金融", region="北京", capability="容器", old=True)
    add_demand(admin, "archived", [recommendation(excluded["id"], excluded["name"])], archived=True)
    response = client.get(f"/admin/reports?{query}", headers=auth_headers(admin))
    assert response.status_code == 200
    report = response.json()
    assert report["overview"]["totalDemands"] == 2
    assert report["overview"]["totalPartners"] == 3
    assert report["activePartnerCount"] == report["overview"]["activePartners"] == 1
    assert report["activePartnerRatio"] == 33.3
    assert len(report["topRecommendedPartners"]) == 1
    top = report["topRecommendedPartners"][0]
    assert (top["partnerName"], top["recommendCount"]) == (included["name"], 2)
    assert {item["partnerName"] for item in report["inactivePartners"]} == {excluded["name"], "未推荐伙伴"}


def test_report_handles_same_names_and_legacy_recommendations(client):
    admin = make_user("report_legacy_admin", role="admin")
    make_partner("same-one", "同名伙伴")
    make_partner("same-two", "同名伙伴")
    make_partner("legacy", "唯一历史伙伴")
    add_demand(admin, "mixed recommendations", [
        recommendation("same-one", "同名伙伴"), recommendation("same-two", "同名伙伴"),
        {"partnerName": "同名伙伴"}, {"partnerName": "唯一历史伙伴"},
        {"partnerName": "不存在的伙伴"}, {"partnerName": []}, "malformed entry",
    ])
    response = client.get("/admin/reports", headers=auth_headers(admin))
    assert response.status_code == 200
    report = response.json()
    assert report["activePartnerCount"] == 3
    assert report["activePartnerRatio"] == 100
    assert sorted(item["recommendCount"] for item in report["topRecommendedPartners"]) == [1, 1, 1]


def add_opportunity(owner):
    task_id = make_task(owner, "editable opportunity")
    opp_id = f"opportunity-{task_id}"
    old = "2020-01-01T00:00:00+00:00"
    with get_db() as conn:
        conn.execute(
            """INSERT INTO project_opportunities
               (id, match_record_id, requirement_text, completeness_score, missing_fields,
                technical_needs, follow_up_questions, created_at, updated_at)
               VALUES (?, ?, '合成需求', 0, ?, '保留的技术需求', '["原始补充建议"]', ?, ?)""",
            (opp_id, task_id, ",".join(COMPLETE_OPPORTUNITY), old, old),
        )
    return task_id, opp_id


@pytest.mark.parametrize("editor", ["owner", "admin"])
def test_opportunity_edits_recalculate_completeness_and_missing_fields(client, editor):
    owner = make_user("opportunity_owner")
    admin = make_user("opportunity_admin", role="admin")
    task_id, opp_id = add_opportunity(owner)
    url = f"/agent/tasks/{task_id}/opportunity" if editor == "owner" else f"/admin/opportunities/{opp_id}"
    headers = auth_headers(owner if editor == "owner" else admin)
    method = "PATCH" if editor == "owner" else "PUT"
    response = client.request(method, url, headers=headers, json=COMPLETE_OPPORTUNITY)
    assert response.status_code == 200
    full = response.json()
    assert full["completenessScore"] == 100
    assert full["missingFields"] == ""
    assert full["technicalNeeds"] == "保留的技术需求"
    assert full["followUpQuestions"] == '["原始补充建议"]'
    assert full["updatedAt"] != full["createdAt"]

    response = client.request(method, url, headers=headers, json={"customerName": "", "region": "  ", "industry": ""})
    assert response.status_code == 200
    partial = response.json()
    assert partial["completenessScore"] == 50
    assert set(partial["missingFields"].split(",")) == {"customerName", "region", "industry"}
    assert partial["projectName"] == COMPLETE_OPPORTUNITY["projectName"]
    # Null keeps the existing partial-update semantics; empty strings clear fields.
    unchanged = client.request(method, url, headers=headers, json={"projectName": None}).json()
    assert unchanged["projectName"] == partial["projectName"]
    assert unchanged["completenessScore"] == partial["completenessScore"]
    assert unchanged["updatedAt"] == partial["updatedAt"]


def test_new_opportunity_extraction_uses_same_completeness_rules(client, monkeypatch):
    owner = make_user("extracted_opportunity_owner")
    task_id = make_task(owner, "extracted opportunity")
    data = {**COMPLETE_OPPORTUNITY, "region": "  ", "industry": " 未识别 "}
    monkeypatch.setattr(ai_client, "chat_completion", lambda *_args, **_kwargs: json.dumps(data))
    assert match._extract_project_opportunity("合成需求", task_id, []) is True
    detail = client.get(f"/agent/tasks/{task_id}", headers=auth_headers(owner)).json()
    assert detail["opportunity"]["completenessScore"] == 67
    assert set(detail["opportunity"]["missingFields"].split(",")) == {"region", "industry"}


def test_concurrent_opportunity_edits_keep_metrics_consistent(client):
    owner = make_user("concurrent_opportunity_owner")
    task_id, _ = add_opportunity(owner)
    fields = list(COMPLETE_OPPORTUNITY)
    payloads = [
        {field: COMPLETE_OPPORTUNITY[field] for field in fields[:3]},
        {field: COMPLETE_OPPORTUNITY[field] for field in fields[3:]},
    ]
    headers = auth_headers(owner)

    def update(payload):
        return client.patch(f"/agent/tasks/{task_id}/opportunity", headers=headers, json=payload).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(update, payloads)) == [200, 200]
    result = client.get(f"/agent/tasks/{task_id}", headers=headers).json()["opportunity"]
    assert result["completenessScore"] == 100
    assert result["missingFields"] == ""
    assert all(result[field] == value for field, value in COMPLETE_OPPORTUNITY.items())
