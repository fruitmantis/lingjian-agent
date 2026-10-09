"""Public model failures must not expose upstream diagnostics or content."""
import httpx
import pytest

from backend.app import ai_client, profile_sources
from backend.app.database import get_db
from backend.app.routers import model_config, profile
from .conftest import auth_headers, make_partner, make_user
from .test_profile_report import setup, upload, organize, profile as source_profile


@pytest.mark.parametrize("data", [
    None, [], {}, {"choices": []}, {"choices": [None]},
    {"choices": [{"message": None}]}, {"choices": [{"message": {"content": " "}}]},
    {"choices": [{"message": {"content": [{"text": 123}]}}]},
    {"choices": [{"finish_reason": "length", "message": {"content": "truncated"}}]},
    {"choices": [{"finish_reason": "content_filter", "message": {"content": "filtered"}}]},
])
def test_incomplete_or_malformed_completion_is_rejected(data):
    with pytest.raises(ai_client.ModelResponseError):
        ai_client._completion_content(data)


def test_text_content_parts_remain_supported():
    assert ai_client._completion_content({"choices": [{"message": {"content": [{"type": "text", "text": "合成"}, {"text": "结果"}]}}]}) == "合成结果"


@pytest.mark.parametrize("failure", ["timeout", "http401", "http429", "http500", "exception", "empty", "truncated", "missing", "wrong_schema", "success"])
def test_manual_connection_test_validates_content_and_sanitizes_errors(client, monkeypatch, failure):
    admin = make_user("connection_admin", role="admin")
    config = model_config.create_config(model_config.ModelConfigCreate(name="synthetic", apiKey="synthetic-private-key", modelName="test", baseUrl="https://model.invalid/private-path",temperature=.4,maxTokens=131072))
    marker = "synthetic-private-key Authorization Bearer synthetic-token private-customer-data"
    class FakeClient:
        def __init__(self, **kwargs): assert kwargs['timeout']==300
        async def __aenter__(self): return self
        async def __aexit__(self, *_args): pass
        async def post(self, url, **kwargs):
            payload=kwargs['json']
            assert payload['response_format']=={'type':'json_object'}
            assert (payload['temperature'],payload['max_tokens'])==(.4,131072)
            req = httpx.Request("POST", url)
            if failure == "timeout": raise httpx.ReadTimeout(marker, request=req)
            if failure == "exception": raise RuntimeError(marker)
            if failure.startswith("http"):
                return httpx.Response(int(failure[4:]), request=req, text=marker)
            content = '' if failure=='empty' else '{"ok":"true"}' if failure=='wrong_schema' else '{"ok":true}'
            data = {"choices": [{"finish_reason": "length" if failure == "truncated" else "stop", "message": {"content": content}}]}
            return httpx.Response(200, request=req, json={} if failure == "missing" else data)
    original = httpx.AsyncClient
    monkeypatch.setattr(model_config.development_model.httpx, "AsyncClient", lambda **kwargs: original(**kwargs) if 'transport' in kwargs else FakeClient(**kwargs))
    response = client.post(f"/admin/model-configs/{config.id}/test", headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()["success"] is (failure == "success")
    for text in ("synthetic-private-key", "synthetic-token", "private-customer-data", "private-path", "Authorization"):
        assert text not in response.text


def _failed_source_with_valid_profile(setup):
    """Use existing isolated fixtures; only the selected source needs a retry."""
    _,_,_,pid,_=setup
    upload(setup,'valid-error-baseline.txt','RetainedValidSyntheticQuasar。')
    organize(setup)
    fid=upload(setup,'selected-error-source.txt','UnprocessedRetrySyntheticQuasar。')
    with get_db() as conn:
        current=profile_sources.source(conn,pid,'document',fid)
        profile_sources.put(conn,current,'failed',error='synthetic explicit retry')
        profile_sources.rebuild(conn,pid)
        before=dict(conn.execute('SELECT * FROM partners WHERE id=?',(pid,)).fetchone())
        cached=dict(conn.execute('SELECT * FROM partner_documents WHERE id=?',(fid,)).fetchone())
    assert 'RetainedValidSyntheticQuasar' in before['ai_profile']
    assert 'UnprocessedRetrySyntheticQuasar' not in before['ai_profile']
    return fid,before,cached


def test_profile_failure_preserves_data_without_exposing_exception(setup, monkeypatch):
    client,admin,_,pid,_=setup
    fid,before,cached=_failed_source_with_valid_profile(setup)
    calls=[]
    def fail(_config,messages,_schema):
        import json
        calls.append(json.loads(messages[-1]['content'])['material'])
        raise RuntimeError("synthetic-secret raw-model-JSON internal-prompt")
    monkeypatch.setattr(profile_sources.development_model,"completion",fail)
    response=client.post(f"/partners/{pid}/documents/{fid}/retry",headers=admin)
    # Retry acknowledges the selected file; the separately persisted state reports failure.
    assert response.status_code==200
    assert calls==[cached['extracted_text']]
    public=source_profile(setup)
    assert public['profile_status']=='failed' and public.get('profile_sources') is None
    for text in ("synthetic-secret","raw-model-JSON","internal-prompt"):
        assert text not in response.text and text not in str(public)
    with get_db() as conn:
        contribution=conn.execute("SELECT state,sections_json FROM partner_profile_sources WHERE partner_id=? AND source_kind='document' AND source_id=?",(pid,fid)).fetchone()
        assert contribution['state']=='failed' and contribution['sections_json']=='[]'
        after=dict(conn.execute('SELECT * FROM partners WHERE id=?',(pid,)).fetchone())
        assert {k:v for k,v in after.items() if k!='profile_updated_at'}=={
            k:v for k,v in before.items() if k!='profile_updated_at'}
        assert dict(conn.execute('SELECT * FROM partner_documents WHERE id=?',(fid,)).fetchone())==cached


def test_batch_profile_does_not_copy_nested_exception(client, monkeypatch):
    make_partner()
    admin = make_user("batch_error_admin", role="admin")
    def fail(*_args, **_kwargs):
        raise RuntimeError("synthetic-secret raw-model-JSON internal-prompt")
    monkeypatch.setattr(profile_sources, "sync", fail)
    response = client.post("/partners/batch-profile", headers=auth_headers(admin))
    assert response.status_code == 200
    assert response.json()["failed"] == 1
    assert "synthetic-secret" not in response.text and "raw-model-JSON" not in response.text


def test_reasoning_parts_are_not_returned_as_public_text():
    data = {"choices": [{"message": {"content": [
        {"type": "reasoning", "text": "synthetic-private-thought"},
        {"type": "text", "text": "可展示的结果"},
    ]}}]}
    assert ai_client._completion_content(data) == "可展示的结果"


def test_inline_reasoning_tags_are_rejected():
    with pytest.raises(ai_client.ModelResponseError):
        ai_client._completion_content({"choices": [{"message": {"content": "<think>synthetic-private-thought</think>结果"}}]})


@pytest.mark.parametrize("narrative", ["", '{"internal":"synthetic-secret"}', '```json\n{"raw":"synthetic-secret"}\n```'])
def test_profile_does_not_persist_raw_structured_output(setup, monkeypatch, narrative):
    client,admin,_,pid,_=setup
    fid,before,cached=_failed_source_with_valid_profile(setup)
    calls=[]
    def malformed(_config,messages,_schema):
        import json
        calls.append(json.loads(messages[-1]['content'])['material'])
        return narrative
    monkeypatch.setattr(profile_sources.development_model,"completion",malformed)
    response=client.post(f"/partners/{pid}/documents/{fid}/retry",headers=admin)
    assert response.status_code==200
    assert calls==[cached['extracted_text']]
    public=source_profile(setup)
    assert public['profile_status']=='failed'
    assert "synthetic-secret" not in response.text and "synthetic-secret" not in str(public)
    with get_db() as conn:
        contribution=conn.execute("SELECT state,sections_json FROM partner_profile_sources WHERE partner_id=? AND source_kind='document' AND source_id=?",(pid,fid)).fetchone()
        assert contribution['state']=='failed' and contribution['sections_json']=='[]'
        saved=conn.execute('SELECT ai_profile FROM partners WHERE id=?',(pid,)).fetchone()[0]
        assert saved==before['ai_profile'] and 'RetainedValidSyntheticQuasar' in saved
        assert 'UnprocessedRetrySyntheticQuasar' not in saved and 'synthetic-secret' not in saved
        if narrative:assert narrative not in saved
        assert dict(conn.execute('SELECT * FROM partner_documents WHERE id=?',(fid,)).fetchone())==cached
