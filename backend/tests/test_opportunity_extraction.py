import json
import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError
from backend.app import ai_client
from backend.app.database import get_db
from backend.app.opportunity_extraction import normalize_opportunity, UNKNOWN, TEXT_FIELDS
from backend.app.routers import match
from backend.app.routers.demand import calculate_opportunity_completeness
from .conftest import make_user, make_partner, make_task, auth_headers, recommendation

BASE = {"customerName": "合成客户", "projectName": "合成医疗项目", "industry": ["教育医疗"],
        "region": {"domestic": ["上海"], "overseas": []}, "projectStage": "方案设计", "businessNeeds": "容灾"}

@pytest.mark.parametrize("region,expected", [
    ({"domestic": ["上海"], "overseas": []}, "上海"),
    ({"domestic": ["深圳"], "overseas": ["亚太"]}, "广东,亚太"),
    ({"region_type": "domestic", "regions": ["上海"]}, "上海"),
    ([{"region_type": "domestic", "regions": ["广东"]}, {"region_type": "overseas", "regions": ["欧洲"]}], "广东,欧洲"),
    (["上海", None, 5, "待确认地区"], "上海"),
    ({"unrecognized": "上海"}, UNKNOWN),
    (None, UNKNOWN),
])
def test_region_forms_and_unknown(region, expected):
    result = normalize_opportunity(json.dumps({**BASE, "region": region}))
    assert result["region"] == expected
    assert result["projectName"] == BASE["projectName"]

@pytest.mark.parametrize("wrap", [
    lambda value: json.dumps(value),
    lambda value: "```JSON\n" + json.dumps(value) + "\n```",
    lambda value: "以下是提取结果：\n" + json.dumps(value) + "\n以上仅为项目摘要。",
    lambda value: json.dumps([value]),
    lambda value: json.dumps({"data": value}),
    lambda value: json.dumps(value)[:-1] + ",}",
    lambda value: "```json\n" + json.dumps(value)[:-1] + ",}\n```",
])
def test_compatible_wrappers_keep_real_failure_shape(wrap):
    result = normalize_opportunity(wrap(BASE))
    assert result["industry"] == "教育医疗" and result["region"] == "上海"
    assert result["customerName"] == BASE["customerName"]


def test_local_bad_fields_do_not_discard_good_fields():
    result = normalize_opportunity(json.dumps({**BASE, "region": 12, "qualificationRequirements": {"unexpected": "secret"},
        "deliveryNeeds": ["容灾", "迁移", None], "onsiteRequirement": False, "followUpQuestions": "是否要求驻场？"}))
    assert result["region"] == result["qualificationRequirements"] == result["onsiteRequirement"] == UNKNOWN
    assert result["projectName"] == BASE["projectName"] and result["deliveryNeeds"] == "容灾；迁移"
    assert result["followUpQuestions"] == ["是否要求驻场？"]
    assert "secret" not in json.dumps(result)

@pytest.mark.parametrize("raw", ["完全没有结构化字段", "{}", "null", '[{"projectName":"甲"},{"projectName":"乙"}]'])
def test_unavailable_fields_become_unknown_not_invented(raw):
    result = normalize_opportunity(raw)
    assert all(result[field] == UNKNOWN for field in TEXT_FIELDS)
    assert result["followUpQuestions"] == []
    assert calculate_opportunity_completeness(result)[0] == 0


def test_separator_repair_does_not_rewrite_business_text():
    text = '保留字面量 ,} 和 \"quoted\"'
    result = normalize_opportunity(json.dumps({**BASE, "businessNeeds": text})[:-1] + ',}')
    assert result["businessNeeds"] == text


def test_retry_saves_grouped_regions_and_preserves_existing_results(client, monkeypatch):
    user = make_user("tolerant-retry"); make_partner(); task = make_task(user, "合成医疗项目", task_status="partial")
    with get_db() as conn:
        conn.execute("INSERT INTO demand_profiles(id,match_record_id,requirement_text,created_at) VALUES ('kept-demand',?,'合成医疗项目','2026')", (task,))
    calls = []
    def completion(*args, **kwargs):
        calls.append(kwargs["scene"])
        return json.dumps(BASE)
    monkeypatch.setattr(ai_client, "chat_completion", completion)
    monkeypatch.setattr(match, "_perform_partner_match", lambda *_: (_ for _ in ()).throw(AssertionError("No rematch")))
    response = client.post(f"/agent/tasks/{task}/retry", headers=auth_headers(user))
    assert response.status_code == 200 and response.json()["taskStatus"] == "ready"
    assert calls == ["demand_profile"]
    with get_db() as conn:
        row = conn.execute("SELECT region,industry,project_name FROM project_opportunities WHERE match_record_id=?", (task,)).fetchone()
        assert tuple(row) == ("上海", "教育医疗", BASE["projectName"])
        assert conn.execute("SELECT count(*) FROM demand_profiles WHERE match_record_id=?", (task,)).fetchone()[0] == 1
    detail = client.get(f"/agent/tasks/{task}", headers=auth_headers(user)).json()
    assert len(detail["recommendations"]) == 1 and detail["failureDetails"] == []


def test_unknowns_are_saved_without_false_completeness(client, monkeypatch):
    user = make_user("unknown-opportunity"); make_partner(); task = make_task(user, "合成缺失数据")
    monkeypatch.setattr(ai_client, "chat_completion", lambda *a, **k: '{"customerName":"合成客户","region":false}')
    failures = []
    assert match._extract_project_opportunity("合成缺失数据", task, [], failures=failures)
    assert failures == []
    with get_db() as conn:
        row = conn.execute("SELECT project_name,region,completeness_score,missing_fields FROM project_opportunities WHERE match_record_id=?", (task,)).fetchone()
    assert row["project_name"] == row["region"] == UNKNOWN
    assert row["completeness_score"] == 17 and "region" in row["missing_fields"]

@pytest.mark.parametrize("error,code", [(httpx.ReadTimeout("synthetic"), "timeout")])
def test_technical_failures_are_not_masked_as_unknown(client, monkeypatch, error, code):
    user = make_user("technical-failure"); make_partner(); task = make_task(user, "合成技术失败")
    monkeypatch.setattr(ai_client, "chat_completion", lambda *a, **k: (_ for _ in ()).throw(error))
    failures = []
    assert not match._extract_project_opportunity("合成技术失败", task, [], failures=failures)
    assert failures[0]["code"] == code
    with get_db() as conn:
        assert conn.execute("SELECT count(*) FROM project_opportunities WHERE match_record_id=?", (task,)).fetchone()[0] == 0


def test_database_failure_rolls_back_instead_of_saving_unknown(client, monkeypatch):
    from contextlib import contextmanager
    user = make_user("save-failure"); make_partner(); task = make_task(user, "合成保存失败")
    monkeypatch.setattr(ai_client, "chat_completion", lambda *a, **k: json.dumps(BASE))
    @contextmanager
    def failing_database():
        with get_db() as connection:
            class Proxy:
                def execute(self, sql, params):
                    result = connection.execute(sql, params)
                    if sql.startswith("INSERT INTO project_opportunities"):
                        raise SQLAlchemyError("synthetic failure after insert")
                    return result
            yield Proxy()
    monkeypatch.setattr(match, "get_db", failing_database)
    failures = []
    assert not match._extract_project_opportunity("合成保存失败", task, [], failures=failures)
    assert failures[0]["code"] == "persistence"
    with get_db() as conn:
        assert conn.execute("SELECT count(*) FROM project_opportunities WHERE match_record_id=?", (task,)).fetchone()[0] == 0
