import pytest
from backend.tests.support.model_test_boundary import require_test_database

@pytest.mark.parametrize("url,valid", [
    ("sqlite://",False), ("",False),
    ("postgresql://u:p@localhost/banfei_validation",True),
    ("postgresql+psycopg://u:p@localhost/banfei_agent_test",True),
    ("postgresql://u:p@127.0.0.1/banfei_agent_test",True),
    ("postgresql://u:p@localhost/banfei_agent",False),
    ("postgresql://u:p@remote/banfei_validation",False),
    ("postgresql://u:p@remote/banfei_agent_test",False),
    ("postgresql://u:p@localhost/banfei_agent_test_copy",False),
    ("postgresql+asyncpg://u:p@localhost/banfei_agent_test",False),
])
def test_fixture_database_boundary(monkeypatch,url,valid):
    scoped=url+"?options=-csearch_path%3Dvalidation_"+"a"*32 if url.startswith('postgresql') else url
    monkeypatch.setenv("DATABASE_URL",scoped)
    monkeypatch.setenv("LINGJIAN_UPLOADS_DIR","/tmp/synthetic-uploads")
    if valid:require_test_database()
    else:
        with pytest.raises(RuntimeError):require_test_database()

@pytest.mark.parametrize('options',['','-csearch_path=public','-csearch_path=validation_bad','-csearch_path=validation_'+('a'*32)+',public'])
def test_public_and_unowned_schemas_are_rejected(monkeypatch,options):
    from sqlalchemy.engine import make_url
    url=make_url('postgresql://localhost/banfei_agent_test').update_query_dict({'options':options})
    monkeypatch.setenv('DATABASE_URL',url.render_as_string(hide_password=False))
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
    sent='\n'.join(m['content'] for m in requests[0]['messages'])
    assert json.dumps(ConversationOutput.model_json_schema(),ensure_ascii=False) in sent
    assert messages==[{'role':'user','content':'Synthetic explanation'}]
    assert len(messages)==1
    with pytest.raises(engine.InvalidOutput):engine.parse(raw,ConversationOutput,[])


def test_reasoning_override_only_for_verified_provider_model():
    from backend.app.ai_client import provider_request_options
    assert provider_request_options("https://api.deepseek.com","deepseek-v4-flash")=={"thinking":{"type":"disabled"}}
    assert provider_request_options("https://elsewhere.test","deepseek-v4-flash")=={}
    assert provider_request_options("https://api.deepseek.com","other-model")=={}


def test_missing_validation_configuration_never_inherits_runtime(monkeypatch):
    from backend.tests.postgres_support import empty_postgres_schema
    monkeypatch.delenv('BANFEI_TEST_DATABASE_URL')
    monkeypatch.setenv('DATABASE_URL','postgresql://localhost/banfei_agent')
    with pytest.raises(RuntimeError,match='BANFEI_TEST_DATABASE_URL'):
        with empty_postgres_schema():pytest.fail('Must fail before schema creation')


@pytest.mark.parametrize('query', ['host=remote','dbname=banfei_agent','options=-csearch_path=public'])
def test_validation_url_rejects_connection_overrides(query):
    from backend.tests.support.model_test_boundary import validation_url
    with pytest.raises(RuntimeError):
        validation_url('postgresql://localhost/banfei_agent_test?'+query)
