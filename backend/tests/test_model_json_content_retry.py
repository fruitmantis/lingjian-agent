"""B/C opt-in JSON envelopes and additive request retries, synthetic PostgreSQL/HTTP."""
import json

import httpx

HTTPX_ASYNC_CLIENT = httpx.AsyncClient
import pytest
from pydantic import ValidationError

from backend.business.common import model_json_object, ModelJSONError
from backend.business import matching
from backend.app import agent_settings, ai_client, development_model, error_diagnostics as diagnostics
from backend.app.database import get_db
from backend.app.model_resolver import model_record, resolve_model_record, ModelConfigurationError
from backend.app.model_timeout_settings import TimeoutSettings
from backend.app.routers import model_config
from .postgres_support import snapshot


@pytest.mark.parametrize('wrap', [lambda s:s,lambda s:' \ufeff'+s+'\n',lambda s:'```json\n'+s+'\n```',lambda s:'```\n'+s+'\n```',lambda s:'这是 JSON：\n'+s+'\n以上是结果。',lambda s:"Here's the JSON:\n"+s])
def test_known_envelopes_preserve_all_values(wrap):
    data={'in_scope':True,'facts':{'businessNeeds':'  原值 {不改} [保留] \\"  '},'unused':{'n':1,'items':[False,None,'未知']}}
    assert model_json_object(wrap(json.dumps(data,ensure_ascii=False)))==data
    result,rejected=matching.parse_understanding(wrap(json.dumps(data,ensure_ascii=False)),'原值',[])
    original=matching.parse_understanding(json.dumps(data,ensure_ascii=False),'原值',[])
    assert (result,rejected)==original


@pytest.mark.parametrize('raw', [
    '', '   ', '{"{"in_scope":true,"facts":{}}', '{{"in_scope":true}}',
    '{"in_scope":true', '{"in_scope":true}}',
    '{"in_scope":true}{"in_scope":false}',
    '结果：{"in_scope":true}\n{"in_scope":false}',
    '[{"in_scope":true}]', '结果：[{"in_scope":true}]',
    json.dumps('{"in_scope":true}'), '"{"in_scope":true}',
    '{"in_scope":true}"', '{"in_scope":true}[]',
])
def test_ambiguous_or_broken_json_is_not_repaired(raw):
    with pytest.raises((ModelJSONError,json.JSONDecodeError)):model_json_object(raw)


def test_existing_schema_and_partial_projection_are_not_relaxed():
    with pytest.raises(ValidationError):matching.parse_understanding('```json\n{"in_scope":"true"}\n```','需求',[])
    with pytest.raises(ValidationError):matching.parse_understanding('{"in_scope":true,"facts":{"complexityLevel":"invented"}}','需求',[])
    raw={'recommendations':[],'analysisRefs':[],'supplyStatus':'gap','gapAnalysis':'已有缺项','unused':'ignored'}
    assert matching.parse_answer('返回：'+json.dumps(raw,ensure_ascii=False))==matching.parse_answer(json.dumps(raw,ensure_ascii=False))
    assert 'unused' not in matching.parse_answer(json.dumps(raw))[0]
    malformed={**raw,'recommendations':[{'partnerId':'invented','evidenceType':'invented'}]}
    output,rejected=matching.parse_answer(json.dumps(malformed))
    assert output['recommendations']==[] and rejected==['recommendation:0']


def synthetic_model(monkeypatch,*,retries=3,endpoint='https://synthetic.invalid/v1',model='synthetic'):
    monkeypatch.setenv('SYNTHETIC_BC_KEY','synthetic-bc-private-key')
    settings=agent_settings.read()
    for owner in (*agent_settings.AGENT_IDS,'processing'):
        current=settings['processing'] if owner=='processing' else settings['agents'][owner]
        cls=agent_settings.ModelSettings if owner=='processing' else agent_settings.AgentSettings
        agent_settings.save(owner,cls(**{**current,'timeoutSeconds':7,'timeoutRetries':retries}))
    with get_db() as conn:
        target=settings['processing']['modelConfigId']
        conn.execute("UPDATE model_providers SET base_url=?,api_key='synthetic-bc-private-key',api_key_source='db'",(endpoint,))
        conn.execute('UPDATE model_configs SET model_name=?',(model,))
    return target


def transport(monkeypatch,events,*,on_send=None):
    seen=[];original=HTTPX_ASYNC_CLIENT
    def handle(request):
        seen.append({'body':request.content,'timeout':dict(request.extensions['timeout'])})
        if on_send:on_send(len(seen))
        event=events[min(len(seen)-1,len(events)-1)]
        if event=='timeout':raise httpx.ReadTimeout('synthetic-bc-private-key')
        if event=='connection':raise httpx.ConnectError('synthetic-bc-private-key')
        if isinstance(event,int):return httpx.Response(event,request=request)
        if isinstance(event,tuple):content,finish=event
        else:content,finish=event,'stop'
        return httpx.Response(200,request=request,json={'choices':[{'finish_reason':finish,'message':{'content':content}}]})
    monkeypatch.setattr(development_model.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    return seen


@pytest.mark.parametrize('raw,success,attempts', [
    ('\ufeff```json\n{"ok":true}\n```',True,1),
    ('说明：{"ok":true}，探测结果。',True,1),
    ('{"ok":true,"unused":{"ok":false}}',True,1),
    ('{"ok":true,"unused":"INTERNAL_SECRET_UNUSED"}',True,1),
    ('{"wrapper":{"ok":true}}',False,2),
    ('{"ok":false,"wrapper":{"ok":true}}',False,2),
    ('{"ok":"true"}',False,2),('{"ok":1}',False,2),
    ('{"ok":true}{"ok":false}',False,2),
    ('[{"ok":true}]',False,2),('{"{"ok":true}',False,2),
    (('', 'stop'),False,2), (('{"ok":true}','length'),False,2),
])
def test_probe_validates_top_level_strict_ok_after_envelope_parsing(monkeypatch,raw,success,attempts):
    target=synthetic_model(monkeypatch);seen=transport(monkeypatch,[raw])
    with get_db() as conn:before=snapshot(conn)
    result=model_config.test_connection(target)
    assert result.success is success and len(seen)==attempts
    assert result.message==('连接及 JSON 格式校验通过' if success else '连接成功，但返回内容未通过校验')
    with get_db() as conn:assert snapshot(conn)==before


@pytest.mark.parametrize('bad', ['{"{"ok":true}', ('','stop'), ('{"ok":true}','length')])
def test_probe_content_failure_gets_one_fresh_complete_response(monkeypatch,bad):
    target=synthetic_model(monkeypatch);seen=transport(monkeypatch,[bad,'{"ok":true}'])
    assert model_config.test_connection(target).success and len(seen)==2
    assert seen[0]==seen[1] and ai_client.last_retry_count()==1


@pytest.mark.parametrize('event,message', [(401,'认证失败'),(429,'请求受限'),(500,'服务返回异常'),('connection','无法连接')])
def test_probe_transport_errors_are_distinct_and_not_content_retried(monkeypatch,event,message):
    target=synthetic_model(monkeypatch);seen=transport(monkeypatch,[event])
    result=model_config.test_connection(target)
    assert not result.success and message in result.message and len(seen)==1
    assert result.message!='连接成功，但返回内容未通过校验'


@pytest.mark.parametrize('events,retries,success,count', [
    (['{broken','{"ok":true}'],0,True,2),
    (['timeout'],0,False,1),(['timeout'],3,False,4),
    (['timeout','{broken','timeout','timeout','{"ok":true}'],3,True,5),
    (['{broken','timeout','timeout','timeout','{"ok":true}'],3,True,5),
    (['timeout','timeout','timeout','{broken','{"ok":true}'],3,True,5),
    (['{broken','timeout'],3,False,5),
    (['timeout','timeout','timeout','{broken','{broken'],3,False,5),
    (['{broken'],3,False,2),
])
def test_content_and_timeout_retries_add_and_never_multiply(monkeypatch,events,retries,success,count):
    target=synthetic_model(monkeypatch,retries=retries);seen=transport(monkeypatch,events)
    result=model_config.test_connection(target)
    assert result.success is success and len(seen)==count
    assert len(seen)<=retries+2 and all(item==seen[0] for item in seen)
    assert ai_client.last_retry_count()==len(seen)-1


def test_content_retry_keeps_frozen_policy_but_next_probe_reads_changes(monkeypatch):
    target=synthetic_model(monkeypatch)
    def update(n):
        if n==1:
            current=agent_settings.read()['processing']
            agent_settings.save('processing',agent_settings.ModelSettings(**{**current,'timeoutSeconds':11,'timeoutRetries':0}))
    seen=transport(monkeypatch,['{broken','timeout','timeout','timeout','{"ok":true}'],on_send=update)
    assert model_config.test_connection(target).success and len(seen)==5
    assert all(set(item['timeout'].values())=={7} for item in seen)
    following=transport(monkeypatch,['{"ok":true}'])
    assert model_config.test_connection(target).success and set(following[0]['timeout'].values())=={11}


def test_configuration_change_stops_content_retry(monkeypatch):
    target=synthetic_model(monkeypatch)
    def update(n):
        if n==1:
            with get_db() as conn:conn.execute('UPDATE model_configs SET temperature=0.9 WHERE id=?',(target,))
    seen=transport(monkeypatch,['{broken','{"ok":true}'],on_send=update)
    result=model_config.test_connection(target)
    assert not result.success and len(seen)==1


@pytest.mark.parametrize('agent',['partner_development','processing'])
def test_other_structured_calls_do_not_gain_content_retry(monkeypatch,agent):
    synthetic_model(monkeypatch);seen=transport(monkeypatch,[('', 'stop'),'{"ok":true}'])
    selected=resolve_model_record(agent)
    with pytest.raises(ai_client.ModelResponseError):development_model.completion(selected,[],{})
    assert len(seen)==1


def test_retry_metadata_omits_credentials_and_full_business_input(monkeypatch,caplog):
    synthetic_model(monkeypatch);seen=transport(monkeypatch,['{broken','{"in_scope":true}'])
    selected=resolve_model_record('partner_match');private='REQUEST_START_'+('合成私人需求'*600)+'_REQUEST_END'
    with diagnostics.diagnostic_scope(stage='understanding'):
        result=development_model.validated_completion(selected,[{'role':'user','content':private}],{},model_json_object)
    assert result=={'in_scope':True} and len(seen)==2
    logs=caplog.text+diagnostics.log_path().read_text()
    assert 'synthetic-bc-private-key' not in logs and private not in logs and 'REQUEST_START_' not in logs
    events=[json.loads(record.message.split('MODEL_CONTENT_RETRY ',1)[1]) for record in caplog.records if record.message.startswith('MODEL_CONTENT_RETRY ')]
    assert len(events)==1 and events[0]['attempt_count']==1 and events[0]['content_retries']==0 and events[0]['max_attempts']==5 and events[0]['retrying']


@pytest.mark.parametrize('base_url,thinking', [('https://api.deepseek.com',True),('https://api.deepseek.com',False),('https://maas.invalid/v1',True),('https://maas.invalid/v1',False)])
def test_content_retry_preserves_official_thinking_boundary(monkeypatch,base_url,thinking):
    synthetic_model(monkeypatch,endpoint=base_url,model='deepseek-flash')
    current=agent_settings.read()['agents']['partner_match'];agent_settings.save('partner_match',agent_settings.AgentSettings(**{**current,'thinking':thinking}))
    seen=transport(monkeypatch,['{broken','{"ok":true}'])
    selected=resolve_model_record('partner_match')
    assert development_model.validated_completion(selected,[],{},model_json_object)=={'ok':True}
    payload=json.loads(seen[0]['body'])
    assert seen[0]==seen[1]
    if base_url=='https://api.deepseek.com':assert payload['thinking']=={'type':'enabled' if thinking else 'disabled'}
    else:assert 'thinking' not in payload


def test_budget_counts_match_only_opt_in_attempts():
    policy=TimeoutSettings()
    assert policy.call_budget()==1200 and policy.call_budget(content_retry=True)==1500
    assert policy.run_budget()==2460 and policy.match_run_budget()==3090
    zero=TimeoutSettings(timeoutSeconds=300,timeoutRetries=0)
    assert zero.call_budget()==300 and zero.call_budget(content_retry=True)==600
    assert zero.run_budget()==660 and zero.match_run_budget()==1290
