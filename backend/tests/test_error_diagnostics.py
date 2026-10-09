"""Real diagnostic content, secrecy, persistence and admin authorization; no live models."""
import json
from sqlalchemy.exc import OperationalError
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from backend.app import ai_client, error_diagnostics as diagnostics
from backend.app.database import get_db
from backend.app.model_resolver import ResolvedModelConfig
from backend.app.routers import match, development
from .conftest import auth_headers, make_user, make_partner, recommendation


def model_reply(monkeypatch, content, status=200):
    with get_db() as conn:
        conn.execute("UPDATE model_configs SET api_key='opaque-provider-credential',api_key_source='db',base_url='https://model.invalid/v1',model_name='test-model'")
    async def post(client, url, **kwargs):
        messages=kwargs['json']['messages'];system=messages[0]['content']
        reply=content
        if status==200:
            if '一次理解项目找伙伴' in system:reply='{"in_scope":true,"facts":{}}'
            elif 'AI 初选' in system:reply='{"candidates":[{"partnerId":"partner-1","verificationFocus":"合成能力核实"}]}'
            else:
                try:
                    values=json.loads(content)
                    values=[{**item,'evidenceCases':[],'evidenceDeliverables':[]} for item in values]
                    reply=json.dumps({'recommendations':values,'supplyStatus':'unknown','gapAnalysis':'待核实'})
                except ValueError:pass
        body={'choices':[{'finish_reason':'stop','message':{'content':reply}}]} if status==200 else {'error':{'message':content}}
        return httpx.Response(status,request=httpx.Request('POST',url),json=body)
    monkeypatch.setattr(httpx.AsyncClient,'post',post)


def saved_errors():
    return diagnostics.recent_errors(100)


def complete_enrichment(monkeypatch):
    def finish(record_id, *args, **kwargs):
        match._set_task_state(record_id, 'ready')
        return 'ready'
    monkeypatch.setattr(match, '_run_task_enrichment', finish)


def test_real_validation_reason_admin_only_and_success_does_not_erase(client, monkeypatch):
    user=make_user('diagnostic-owner');admin=make_user('diagnostic-admin',role='admin');make_partner()
    model_reply(monkeypatch, json.dumps([{**recommendation(), 'matchScore':'92分'}]))
    response=client.post('/agent/match',headers=auth_headers(user),json={'requirement':'隔离验证'})
    assert response.status_code==502 and response.json()['detail']=='本次处理失败，请重试。'
    errors=saved_errors();assert len(errors)==1
    error=errors[0]
    assert 'matchScore 无法解析为数字' in error['message']
    assert error['model']=='test-model' and error['http_status']==200
    assert '92分' in error['response_excerpt'] and '_perform_partner_match' in error['traceback']
    assert error['task_id'] and error['request_id'] and error['time']
    detail=client.get('/agent/tasks/'+error['task_id'],headers=auth_headers(user))
    assert 'matchScore 无法解析' not in detail.text and 'traceback' not in detail.text
    assert client.get('/admin/system/errors').status_code==401
    assert client.get('/admin/system/errors',headers=auth_headers(user)).status_code==403
    response=client.get('/admin/system/errors',headers=auth_headers(admin))
    assert response.headers['cache-control']=='no-store'
    assert response.json()['items'][0]['id']==error['id']
    model_reply(monkeypatch,json.dumps([recommendation()]))
    complete_enrichment(monkeypatch)
    assert client.post('/agent/tasks/'+error['task_id']+'/retry',headers=auth_headers(user)).status_code==200
    assert saved_errors()[0]['id']==error['id']
    assert client.get('/agent/tasks/'+error['task_id'],headers=auth_headers(user)).json()['failureDetails']==[]


def test_provider_error_keeps_status_response_and_masks_secrets(client, monkeypatch, caplog):
    user=make_user('provider-owner');make_partner()
    secret='bf_'+'a'*43
    model_reply(monkeypatch, f'quota rejected opaque-provider-credential {secret} Bearer private-token', status=429)
    response=client.post('/agent/match',headers=auth_headers(user),json={'requirement':'隔离验证'})
    assert response.json()['detail']=='本次处理失败，请重试。'
    error=saved_errors()[0]
    assert error['http_status']==429 and error['model']=='test-model'
    assert 'quota rejected' in error['response_excerpt']
    for output in (diagnostics.log_path().read_text(), caplog.text, json.dumps(error), response.text):
        for value in ('opaque-provider-credential',secret,'private-token'):
            assert value not in output


def test_empty_matching_is_a_normal_result(client, monkeypatch):
    user=make_user('empty-owner');make_partner()
    model_reply(monkeypatch,'[]');complete_enrichment(monkeypatch)
    result=client.post('/agent/match',headers=auth_headers(user),json={'requirement':'没有匹配项'})
    assert result.status_code==200 and result.json()['recommendations']==[] and result.json()['taskStatus']=='ready'
    assert saved_errors()==[]


def test_malformed_response_keeps_actual_parse_failure(client, monkeypatch):
    user=make_user('parse-owner');make_partner()
    model_reply(monkeypatch,'{not valid json')
    result=client.post('/agent/match',headers=auth_headers(user),json={'requirement':'格式验证'})
    assert result.status_code==502
    assert saved_errors()[0]['exception_type']=='ValidationError'
    assert '{not valid json' in saved_errors()[0]['response_excerpt']


def test_database_failure_still_records_task_and_stack(client, monkeypatch, caplog):
    user=make_user('db-owner')
    @contextmanager
    def broken():
        raise OperationalError(None,None,Exception('synthetic database unavailable'))
        yield
    monkeypatch.setattr(match,'get_db',broken)
    request_id='c6338961-9625-43c0-a7f4-a424924fe8af'
    result=client.post('/agent/tasks',headers=auth_headers(user),json={'requestId':request_id,'requirement':'隔离故障'})
    assert result.status_code==500 and result.json()['detail']=='服务异常，请联系管理员。'
    error=saved_errors()[0]
    assert error['task_id']==request_id and error['request_id']==request_id
    assert 'synthetic database unavailable' in error['message'] and 'broken' in error['traceback']
    assert 'BANFEI_ERROR' in caplog.text


def test_without_task_uses_request_id_and_retains_program_stack(client, monkeypatch):
    user=make_user('request-owner')
    def broken(*args):
        raise RuntimeError('synthetic program exception')
    monkeypatch.setattr(development.life,'create',broken)
    result=client.post('/development/plans',headers=auth_headers(user),json={'submission_id':'request-test','request':{'target_partner_id':'uncreated','development_direction':'隔离验证'}})
    assert result.status_code==500
    error=saved_errors()[0]
    assert error['task_id'] is None and error['request_id']==result.headers['x-request-id']
    assert 'broken' in error['traceback'] and 'synthetic program exception' in error['message']


def test_log_write_failure_falls_back_to_server_logger(monkeypatch, caplog):
    def unavailable():raise PermissionError('private location')
    monkeypatch.setattr(diagnostics,'log_path',unavailable)
    with diagnostics.diagnostic_scope(task_id='t-fallback'):
        try:raise RuntimeError('fallback diagnosis')
        except RuntimeError as error:diagnostics.record_error(error,'persistence')
    assert 'fallback diagnosis' in caplog.text and 't-fallback' in caplog.text
    assert 'private location' not in caplog.text


@pytest.mark.parametrize('value',[
    'password="secret with spaces"', '{"access_token":"opaque-token"}',
    "{'apiKey': 'opaque-key'}", 'Bearer raw-authorization',
    'https://u:dbpass@host/path?token=urlsecret', 'bf_'+'b'*43,
    'eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyIjoiMSJ9.signature',
    'api_key=unquoted-secret',
])
def test_credential_redaction(value):
    output=diagnostics.excerpt(value)
    for secret in ('secret with spaces','opaque-token','opaque-key','raw-authorization','dbpass','urlsecret','bf_','eyJhbGci','unquoted-secret'):
        assert secret not in output
    assert 'REDACTED' in output


def test_incomplete_log_line_and_reverse_time_order():
    first=diagnostics.record_error(ValueError('first diagnosis'),'analysis')
    second=diagnostics.record_error(ValueError('second diagnosis'),'generation')
    with diagnostics.log_path().open('a') as stream:stream.write('{incomplete')
    assert [item['id'] for item in saved_errors()]==[second,first]
    assert len(diagnostics.recent_errors(1))==1


def test_private_encryption_key_and_cookie_are_redacted(monkeypatch):
    monkeypatch.setenv('BANFEI_IDENTITY_ENCRYPTION_KEY','opaque-encryption-material')
    with diagnostics.diagnostic_scope():
        diagnostics.record_error(ValueError('opaque-encryption-material\nCookie: first=hidden-one; second=hidden-two'),'request')
    text=diagnostics.log_path().read_text()
    assert 'opaque-encryption-material' not in text and 'hidden-one' not in text and 'hidden-two' not in text


def test_sql_bind_values_and_validation_input_are_not_logged():
    from sqlalchemy.exc import StatementError
    from pydantic import BaseModel, ValidationError
    error=StatementError('write failed','INSERT INTO users VALUES (?)',{'password':'opaque-bound-password'},RuntimeError('constraint rejected'))
    diagnostics.record_error(error,'persistence')
    class Input(BaseModel):count:int
    try:Input(count='opaque-user-input')
    except ValidationError as error:diagnostics.record_error(error,'validation')
    text=diagnostics.log_path().read_text()
    assert 'opaque-bound-password' not in text and 'opaque-user-input' not in text
    assert 'constraint rejected' in text and 'int_parsing' in text


def test_configuration_message_and_required_input_remain_distinct(client, monkeypatch):
    user=make_user('required-owner')
    response=client.post('/agent/tasks',headers=auth_headers(user),json={'requestId':'82dfd258-9e5f-43af-8c1c-3477594bf849','requirement':' '})
    assert response.status_code==422 and '请输入项目需求' in response.text
    assert client.get('/agent/tasks').status_code==401


def test_failed_status_write_retains_both_original_and_database_error(client, monkeypatch):
    from backend.app.task_failures import PublicTaskError
    user=make_user('double-failure')
    def invalid(*args):raise PublicTaskError(ValueError('synthetic invalid recommendation field'))
    def unavailable(*args, **kwargs):raise OperationalError(None,None,Exception('synthetic status write unavailable'))
    monkeypatch.setattr(match.understanding,'prepare',lambda *_:{'understanding':{'in_scope':True,'facts':{},'tag_suggestions':[]}})
    monkeypatch.setattr(match,'_perform_partner_match',invalid)
    monkeypatch.setattr(match,'_set_task_state',unavailable)
    response=client.post('/agent/match',headers=auth_headers(user),json={'requirement':'隔离双重故障'})
    assert response.status_code==502
    errors=saved_errors()
    assert len(errors)==2
    assert {error['stage'] for error in errors}=={'partner_match','persistence'}
    assert all(error['task_id'] for error in errors)
    assert any('synthetic status write unavailable' in error['message'] for error in errors)
    assert any('synthetic invalid recommendation field' in error['message'] for error in errors)
