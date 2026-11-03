"""Requirement attachments: one upload per task, extracted once and merged for the model only."""
import uuid

from backend.app.database import get_db
from backend.app.routers import match as match_router

from .conftest import auth_headers, make_task, make_user


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
