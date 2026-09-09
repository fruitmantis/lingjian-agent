import pytest
from backend.tests.support.model_test_boundary import require_test_database

@pytest.mark.parametrize("url,path,valid", [
    ("sqlite://", "/tmp/fixture/app.db", True),
    ("postgresql://u:p@localhost/banfei_validation", "/tmp/fixture/app.db", True),
    ("postgresql://u:p@localhost/banfei_agent", "/tmp/fixture/app.db", False),
    ("postgresql://u:p@remote/banfei_validation", "/tmp/fixture/app.db", False),
    ("sqlite://", "/home/runtime/app.db", False),
    ("", "/tmp/fixture/app.db", False),
])
def test_fixture_database_boundary(monkeypatch,url,path,valid):
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("LINGJIAN_DATABASE_PATH", path)
    if valid:require_test_database()
    else:
        with pytest.raises(RuntimeError):require_test_database()

def test_seed_rejects_runtime_before_initialization(monkeypatch):
    from backend.tests.support import seed_validation_db
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/banfei_agent")
    monkeypatch.setattr(seed_validation_db,"initialize_storage",lambda:pytest.fail("must not initialize runtime"))
    with pytest.raises(RuntimeError):seed_validation_db.seed()


def test_deepseek_json_mode_keeps_schema_and_strict_validation(monkeypatch):
    import json, httpx
    from backend.app import development_model as model, development_engine as engine
    from backend.app.development_types import ConversationOutput
    requests=[]
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,json={"choices":[{"message":{"content":json.dumps({"target_partner_id":"synthetic", "kind":"explain", "answer":"ok", "internal_note":"forbidden"})}}]})
    original=httpx.AsyncClient
    monkeypatch.setattr(model.httpx,"AsyncClient",lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    config={"base_url":"https://api.deepseek.com", "api_key":"synthetic", "model_name":"test", "max_tokens":256}
    messages=[{"role":"user","content":"Synthetic explanation"}]
    raw=model.completion(config,messages,ConversationOutput.model_json_schema())
    assert requests[0]["response_format"]=={"type":"json_object"}
    assert 'additionalProperties' in requests[0]["messages"][-1]["content"]
    assert len(messages)==1
    with pytest.raises(engine.InvalidOutput):engine.parse(raw,ConversationOutput,[])


def test_reasoning_override_only_for_verified_provider_model():
    from backend.app.ai_client import provider_request_options
    assert provider_request_options("https://api.deepseek.com","deepseek-v4-flash")=={"thinking":{"type":"disabled"}}
    assert provider_request_options("https://elsewhere.test","deepseek-v4-flash")=={}
    assert provider_request_options("https://api.deepseek.com","other-model")=={}
