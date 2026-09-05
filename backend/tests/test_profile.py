import json

import pytest

from backend.app.database import get_db
from backend.app.routers import profile

from .conftest import auth_headers, make_partner, make_user


def partner_row(partner_id):
    with get_db() as conn:
        return dict(conn.execute("SELECT * FROM partners WHERE id = ?", (partner_id,)).fetchone())


def mock_profile_calls(monkeypatch, structured, narrative="合成画像正文"):
    responses = iter([structured, narrative])

    def complete(*_args, **_kwargs):
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(profile, "chat_completion", complete)


@pytest.mark.parametrize("structured", [
    RuntimeError("synthetic extraction failure"), "not json", "[]", "{}",
    '{"capabilities":null,"service_areas":" ","industries":[]}',
    '{"capabilities":"不在正式字典中的能力"}',
])
def test_profile_preserves_existing_fields_when_extraction_is_unusable(client, monkeypatch, structured):
    admin = make_user("profile_admin", role="admin")
    partner = make_partner()
    before = partner_row(partner["id"])
    mock_profile_calls(monkeypatch, structured)
    response = client.post(f"/partners/{partner['id']}/profile", headers=auth_headers(admin))
    assert response.status_code == 200
    after = partner_row(partner["id"])
    assert after["ai_profile"] == "合成画像正文"
    for field in ("capabilities", "service_areas", "industries"):
        assert after[field] == before[field]
    assert after["updated_at"] != before["updated_at"]


def test_profile_updates_only_valid_supplied_fields(client, monkeypatch):
    admin = make_user("profile_valid_admin", role="admin")
    partner = make_partner()
    before = partner_row(partner["id"])
    mock_profile_calls(monkeypatch, json.dumps({
        "capabilities": "数据库，不在正式字典中的能力,数据库", "service_areas": " 华东 ",
    }))
    response = client.post(f"/partners/{partner['id']}/profile", headers=auth_headers(admin))
    assert response.status_code == 200
    after = partner_row(partner["id"])
    assert after["capabilities"] == "数据库"
    assert after["service_areas"] == "华东"
    assert after["industries"] == before["industries"]


def test_profile_preserves_capabilities_when_no_formal_tags_are_enabled(client, monkeypatch):
    admin = make_user("profile_empty_dictionary", role="admin")
    partner = make_partner()
    before = partner_row(partner["id"])
    with get_db() as conn:
        conn.execute("UPDATE capability_tags SET enabled = 0")
    mock_profile_calls(monkeypatch, '{"capabilities":"数据库"}')
    assert client.post(f"/partners/{partner['id']}/profile", headers=auth_headers(admin)).status_code == 200
    assert partner_row(partner["id"])["capabilities"] == before["capabilities"]


@pytest.mark.parametrize("structured", ['{"capabilities":"数据库"}', RuntimeError("synthetic extraction failure")])
def test_profile_does_not_write_if_narrative_fails(client, monkeypatch, structured):
    admin = make_user("profile_failure_admin", role="admin")
    partner = make_partner()
    before = partner_row(partner["id"])
    mock_profile_calls(monkeypatch, structured, RuntimeError("synthetic narrative failure"))
    response = client.post(f"/partners/{partner['id']}/profile", headers=auth_headers(admin))
    assert response.status_code == 502
    assert partner_row(partner["id"]) == before
