"""Requirement attachments: one upload per task, extracted once and merged for the model only."""
import asyncio
import threading
import uuid

import httpx
import pytest
from fastapi import HTTPException

from backend.app import development_context, enablement_catalog, task_attachment
from backend.app.development_types import DevelopmentRequest
from backend.app.main import app

from backend.app.database import get_db
from backend.app.routers import match as match_router

from .conftest import auth_headers, make_partner, make_task, make_user


def upload(client, user, name="需求说明.txt", content="第一行\n第二行".encode()):
    return client.post(
        "/agent/tasks/attachment",
        headers=auth_headers(user),
        files={"file": (name, content, "text/plain")},
    )


def test_attachment_001_upload_returns_extracted_text_and_sanitized_name(client):
    user = make_user("attachment_upload_user")
    response = upload(client, user, name="../需求说明.txt")
    assert response.status_code == 200
    body = response.json()
    assert body == {"name": "需求说明.txt", "text": "第一行\n第二行", "charCount": 7, "truncated": False}


def test_attachment_002_long_text_is_capped_and_flagged(client):
    user = make_user("attachment_cap_user")
    response = upload(client, user, content=("长" * 9000).encode())
    assert response.status_code == 200
    body = response.json()
    assert len(body["text"]) == 8000
    assert body["charCount"] == 8000
    assert body["truncated"] is True


def test_attachment_003_rejections_are_user_facing(client):
    user = make_user("attachment_reject_user")
    assert upload(client, user, name="程序.exe", content=b"x").status_code == 422
    assert upload(client, user, name="程序.exe", content=b"x").json()["detail"] == "附件仅支持 PDF、DOCX、TXT、Markdown"
    assert upload(client, user, content=b"").json()["detail"] == "附件内容为空"
    assert upload(client, user, content=b"\x00\x01").status_code == 422


def test_attachment_004_retry_rebuilds_the_merged_model_input(client, monkeypatch):
    user = make_user("attachment_retry_user")
    seen = []

    def prepare(requirement, cached=None):
        seen.append(requirement)
        return {"format_version": 2, "stamp": "synthetic", "model": {},
                "understanding": {"in_scope": False, "facts": {}, "tag_suggestions": []}}

    monkeypatch.setattr(match_router.understanding, "prepare", prepare)
    task_id = make_task(user, "ATTACHMENT-RETRY", task_status="failed", recommendations=[])
    with get_db() as conn:
        conn.execute("UPDATE match_records SET attachment_name=?,attachment_text=? WHERE id=?",
                     ("需求说明.txt", "附件正文内容", task_id))

    response = client.post(f"/agent/tasks/{task_id}/retry", headers=auth_headers(user))
    assert response.status_code == 200
    assert seen == ["ATTACHMENT-RETRY\n\n【附件正文】\n附件正文内容"]
    assert response.json()["requirement"] == "ATTACHMENT-RETRY"


def test_attachment_005_create_task_stores_both_columns_and_keeps_the_typed_requirement(client, monkeypatch):
    user = make_user("attachment_create_user")
    monkeypatch.setattr(match_router.executor, "submit", lambda *args: None)
    request_id = str(uuid.uuid4())
    payload = {"requestId": request_id, "requirement": "需要伙伴", "attachment": {"name": "需求.docx", "text": "附件全文"}}

    response = client.post("/agent/tasks", headers=auth_headers(user), json=payload)
    assert response.status_code == 202
    with get_db() as conn:
        row = conn.execute("SELECT requirement,attachment_name,attachment_text FROM match_records WHERE id=?",
                           (request_id,)).fetchone()
    assert row["requirement"] == "需要伙伴"
    assert row["attachment_name"] == "需求.docx"
    assert row["attachment_text"] == "附件全文"

    detail = client.get(f"/agent/tasks/{request_id}", headers=auth_headers(user)).json()
    assert detail["requirement"] == "需要伙伴"
    assert detail["attachmentName"] == "需求.docx"
    assert detail["attachmentText"] == "附件全文"
    other = make_user("attachment_other_owner")
    assert client.get(f"/agent/tasks/{request_id}", headers=auth_headers(other)).status_code == 404

    repeated = client.post("/agent/tasks", headers=auth_headers(user), json=payload)
    assert repeated.status_code == 202
    assert repeated.json()["recordId"] == request_id

    changed = {**payload, "attachment": {"name": "需求.docx", "text": "另一份正文"}}
    assert client.post("/agent/tasks", headers=auth_headers(user), json=changed).status_code == 409


def test_attachment_006_detail_without_attachment_has_no_name(client, monkeypatch):
    user = make_user("attachment_legacy_user")
    monkeypatch.setattr(match_router.executor, "submit", lambda *args: None)
    request_id = str(uuid.uuid4())
    response = client.post("/agent/tasks", headers=auth_headers(user),
                           json={"requestId": request_id, "requirement": "没有附件"})
    assert response.status_code == 202
    detail = client.get(f"/agent/tasks/{request_id}", headers=auth_headers(user)).json()
    assert detail["attachmentName"] is None
    assert detail["attachmentText"] is None


def test_attachment_007_health_responds_while_document_extraction_is_blocked(client, monkeypatch):
    user = make_user("attachment_concurrent_user")
    headers = auth_headers(user)
    released = threading.Event()
    original = task_attachment.extract_text

    async def scenario():
        started = asyncio.Event()
        loop = asyncio.get_running_loop()

        def blocked_extract(*args):
            loop.call_soon_threadsafe(started.set)
            assert released.wait(5), "extraction was not released"
            return original(*args)

        monkeypatch.setattr(task_attachment, "extract_text", blocked_extract)
        # Ensures the regressed synchronous implementation fails without hanging the suite.
        safety_release = threading.Timer(3, released.set)
        safety_release.start()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as http:
            pending = asyncio.create_task(http.post("/agent/tasks/attachment", headers=headers,
                files={"file": ("需求.txt", "完整需求".encode(), "text/plain")}))
            try:
                await asyncio.wait_for(started.wait(), 2)
                health = await asyncio.wait_for(http.get("/health"), 1)
                assert health.status_code == 200
                assert not released.is_set(), "document parsing blocked the event loop"
            finally:
                released.set()
                safety_release.cancel()
                response = await pending
        assert response.status_code == 200
        assert response.json()["text"] == "完整需求"

    asyncio.run(scenario())


@pytest.mark.parametrize("body", [None, "附件中的交付与资格要求"])
def test_attachment_008_development_source_keeps_full_requirement_and_owner_boundary(client, body):
    owner = make_user("attachment_development_owner")
    other = make_user("attachment_development_other")
    make_partner()
    task_id = make_task(owner, "  手输项目要求  ")
    with get_db() as conn:
        conn.execute("UPDATE match_records SET attachment_name=?,attachment_text=? WHERE id=?",
                     ("需求.txt" if body else None, body, task_id))
    source = enablement_catalog.context(owner, "partner-1", task_id)
    expected = task_attachment.merged("  手输项目要求  ", body)
    assert source["project"]["requirement"] == expected
    request = DevelopmentRequest(target_partner_id="partner-1", source_task_id=task_id,
                                 development_direction="围绕项目要求给出发展建议", model_input_allowed=True)
    loaded = development_context.load(request.model_dump(), owner)
    assert loaded["input"]["profile"]["source_project"]["requirement"] == expected
    for user, partner_id in [(other, "partner-1"), (owner, "unrecommended-partner")]:
        with pytest.raises(HTTPException) as error:
            enablement_catalog.context(user, partner_id, task_id)
        assert error.value.status_code == 404
    with get_db() as conn:
        row = conn.execute("SELECT requirement,attachment_text FROM match_records WHERE id=?", (task_id,)).fetchone()
        assert row["requirement"] == "  手输项目要求  " and row["attachment_text"] == body


@pytest.mark.parametrize("length", [1599, 1600, 1601, 8000, 10000])
def test_attachment_009_full_source_requirement_reaches_development_wire(client, monkeypatch, length):
    import json
    from backend.app import ai_client, development_engine
    from backend.app.development_types import Understanding
    from backend.app.task_failures import MatchInputBudgetError
    from backend.business import development

    owner = make_user("attachment_long_source_owner")
    make_partner()
    typed = "需" * (2000 if length == 10000 else 10)
    tail = "尾部交付要求必须保留"
    prefix_length = len(task_attachment.merged(typed, "x")) - 1
    body = "附" * (length - prefix_length - len(tail)) + tail
    assert len(body) <= task_attachment.MAX_TEXT
    task_id = make_task(owner, typed)
    with get_db() as conn:
        conn.execute("UPDATE match_records SET attachment_name=?,attachment_text=? WHERE id=?",
                     ("需求.txt", body, task_id))
    request = DevelopmentRequest(target_partner_id="partner-1", source_task_id=task_id,
                                 development_direction="围绕项目要求给出发展建议", model_input_allowed=True)
    payload = development_context.load(request.model_dump(), owner)["input"]
    expected = task_attachment.merged(typed, body)
    assert len(expected) == length
    assert payload["profile"]["source_project"]["requirement"] == expected
    config = {"api_key": "synthetic-only", "base_url": "http://127.0.0.1:1/v1", "model_name": "synthetic",
              "max_tokens": 4096, "temperature": 0.3, "top_p": 1.0, "_input_char_limit": 60000}
    messages, schema = development.request("analyze", payload, Understanding)
    wire, metrics = ai_client.prepared_completion(config, messages, schema)
    sent = json.loads(json.loads(wire)["messages"][-1]["content"])
    assert sent["profile"]["source_project"]["requirement"] == expected
    assert metrics["characters"] <= 60000

    if length == 10000:
        payload["current"] = {"answer": "当前有效正文" * 10000}
        monkeypatch.setattr(development_engine.model, "completion", lambda *args: pytest.fail("Over-budget input must not call a model"))
        with pytest.raises(MatchInputBudgetError):
            development_engine.call(config, "analyze", payload, Understanding, [])
        assert payload["profile"]["source_project"]["requirement"] == expected


@pytest.mark.parametrize("tail", ["私有案例原文不应进入模型请求", "INTERNAL_SECRET_attachment"])
def test_attachment_010_full_source_still_filters_sensitive_text_and_requires_permission(client, monkeypatch, tail):
    import json
    from backend.app import development_engine
    from .conftest import recommendation

    owner = make_user("attachment_sensitive_source_owner")
    make_partner()
    item = recommendation()
    item["riskNotes"] = "风险待核实" * 500
    task_id = make_task(owner, "手输需求", recommendations=[item])
    with get_db() as conn:
        conn.execute("UPDATE match_records SET attachment_name=?,attachment_text=? WHERE id=?",
                     ("需求.txt", "附" * 1700 + tail, task_id))
    monkeypatch.setattr(development_engine, "blocked_fragments", lambda conn: ["私有案例原文不应进入模型请求"])
    request = DevelopmentRequest(target_partner_id="partner-1", source_task_id=task_id,
                                 development_direction="围绕项目要求给出发展建议", model_input_allowed=True)
    payload = development_context.load(request.model_dump(), owner)["input"]
    assert payload["profile"]["source_project"]["requirement"] == ""
    assert payload["profile"]["source_project"]["risk_notes"] == item["riskNotes"][:1600]
    assert tail not in json.dumps(payload, ensure_ascii=False)
    request.model_input_allowed = False
    assert "source_project" not in development_context.load(request.model_dump(), owner)["input"]["profile"]
