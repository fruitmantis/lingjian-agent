"""Offline Runtime -> VM diagnostic regressions; synthetic data, no DB/network."""
import asyncio
import contextlib
import copy
import io
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import httpx
from fastapi.testclient import TestClient
from backend.agent_runtime import server, provider
from backend.agent_runtime.contracts import StageRequest, ModelOptions, digest, source_manifest, model_route
from backend.agent_runtime.diagnostics import StageFailure, sanitize_diagnostic, diagnose
from backend.app import runtime_bridge as bridge, error_diagnostics

MARKER = 'PRIVATE_SYNTHETIC_MATERIAL_937519'
ENV = {'BANFEI_RUNTIME_MODEL_URL':'https://api.deepseek.com',
       'BANFEI_RUNTIME_MODEL_NAME':'deepseek-flash', 'BANFEI_RUNTIME_MODEL_KEY':MARKER,
       'BANFEI_RUNTIME_SHARED_KEY':'synthetic-shared-'+('x'*32),
       'BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED':'1',
       'BANFEI_AGENTARTS_BEARER':'synthetic-platform-only',
       'BANFEI_RUNTIME_URL':'https://example.huaweicloud-agentarts.com/runtimes/synthetic/invocations?endpoint=Latest',
       'BANFEI_MATCH_EXECUTOR':'runtime', 'BANFEI_DEVELOPMENT_EXECUTOR':'runtime',
       'BANFEI_RUNTIME_POLL_SECONDS':'0.001', 'BANFEI_RUNTIME_CONTEXT_TOKENS':'262144'}
ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient


def inputs(workflow):
    if workflow == 'match':
        return 'initial_selection', {'facts':{'technicalNeeds':'合成需求'},
            'partners':[{'partnerId':'synthetic-partner','intro':MARKER}]}, {
            'candidates':[{'partnerId':'synthetic-partner','verificationFocus':'核实交付能力'}]}
    return 'plan', {'request':{'target_partner_id':None,'development_direction':'合成学习需求'},
        'constraints':{},'profile':{},'formal_tags':[],'current':None,'recent_exchanges':[],
        'message':'','analysis':{},'understanding':{},
        'candidates':[{'source_type':'course','source_id':'synthetic-course','source_version':1,'title':MARKER}]}, {
        'target_partner_id':None,'answer':'建议学习合成课程。','stages':[{'title':'学习','items':[
            {'source_type':'course','source_id':'synthetic-course','source_version':1,
             'reason':'对应方向','estimated_hours':1.0}]}]}


def packet(app, workflow, retries=1):
    stage,data,_ = inputs(workflow)
    return StageRequest(task_id=uuid.uuid4(),run_id=uuid.uuid4(),session_id=uuid.uuid4(),
        operation_id=uuid.uuid4(),incarnation=app.state.incarnation,workflow=workflow,stage=stage,
        snapshot=digest(data),sources=source_manifest(data),model_fingerprint='a'*64,
        input_token_budget=262144,data=data,model=ModelOptions(
            provider_route=model_route(ENV['BANFEI_RUNTIME_MODEL_URL'],ENV['BANFEI_RUNTIME_MODEL_NAME']),
            name=ENV['BANFEI_RUNTIME_MODEL_NAME'],temperature=.3,top_p=1,
            max_tokens=2048 if workflow=='match' else 131072,timeout_seconds=300.0,timeout_retries=retries))


class ProviderFixture:
    def __init__(self, workflow, case):
        self.workflow=workflow;self.case=case;self.calls=[]
    def respond(self, request):
        self.calls.append(json.loads(request.content))
        case=self.case
        if case=='timeout' or case=='timeout_then_success' and len(self.calls)==1:
            raise httpx.ReadTimeout(MARKER, request=request)
        if case=='http':return httpx.Response(429,json={'error':{'message':MARKER}},headers={'X-Secret':MARKER})
        if case=='malformed':return httpx.Response(200,text=MARKER)
        _,_,body=inputs(self.workflow)
        if case=='schema':
            body['unexpected_'+MARKER]=MARKER
        if case=='reference':
            if self.workflow=='match':body['candidates'][0]['partnerId']=MARKER
            else:body['stages'][0]['items'][0]['source_id']=MARKER
        finish='length' if case=='length' else MARKER if case=='unknown_finish' else 'stop'
        content='' if case=='empty' else json.dumps(body,ensure_ascii=False)
        return httpx.Response(200,json={'choices':[{'finish_reason':finish,
            'message':{'content':content,'reasoning_content':MARKER}}]})
    def client(self,*args,**kwargs):
        return ORIGINAL_ASYNC_CLIENT(*args,transport=httpx.MockTransport(self.respond),**kwargs)


def final_job(client, request):
    headers={'X-Banfei-Runtime-Key':ENV['BANFEI_RUNTIME_SHARED_KEY'],
             'X-Hw-Agentarts-Session-Id':str(request.session_id)}
    response=client.post('/jobs',headers=headers,json=request.model_dump(mode='json'))
    assert response.status_code==202
    for _ in range(200):
        job=client.get('/jobs/'+str(request.operation_id),headers=headers).json()
        if job['status'] in ('completed','failed','awaiting_retry'):return job,headers
        time.sleep(.005)
    raise AssertionError('Synthetic job did not terminate')


class DiagnosticTests(unittest.TestCase):
    def test_both_second_stages_report_safe_distinct_failures(self):
        expected={'length':('model_output_incomplete','ValueError'),
                  'schema':('output_schema_invalid','ValidationError'),
                  'reference':('output_reference_invalid','ValueError'),
                  'http':('provider_http_error','HTTPStatusError'),
                  'malformed':('provider_response_invalid','ValueError'),
                  'empty':('model_output_empty','ValueError'),
                  'unknown_finish':('model_output_incomplete','ValueError')}
        for workflow in ('match','development'):
            for case,(reason,error_type) in expected.items():
                with self.subTest(workflow=workflow,case=case):
                    fixture=ProviderFixture(workflow,case)
                    with patch.dict(os.environ,ENV),patch.object(httpx,'AsyncClient',side_effect=fixture.client), TestClient(server.create_app()) as client, self.assertLogs('banfei.runtime') as logs:
                        job,_=final_job(client,packet(client.app,workflow))
                    self.assertEqual(job['status'],'failed');self.assertEqual(job['error'],'runtime_execution_failed')
                    d=job['diagnostic'];self.assertEqual((d['reason_code'],d['error_type']),(reason,error_type))
                    self.assertFalse(d['retryable']);self.assertEqual(d['upstream_http_status'],429 if case=='http' else 200)
                    if case=='length':self.assertEqual(d['finish_reason'],'length')
                    if case in ('schema','reference'):self.assertEqual(d['finish_reason'],'stop')
                    if case=='unknown_finish':self.assertEqual(d['finish_reason'],'unknown')
                    self.assertEqual(len(fixture.calls),1)
                    self.assertNotIn(MARKER,json.dumps(job)+str(logs.output))

    def test_valid_outputs_enable_supported_thinking_and_keep_other_controls(self):
        for workflow in ('match','development'):
            for host,name,thinking in [('api.deepseek.com','deepseek-flash',{'type':'enabled'}),
                ('api.deepseek.com','deepseek-v4-flash',{'type':'enabled'}),
                ('other.example','deepseek-v4-flash',None),('api.deepseek.com','another-model',None)]:
                with self.subTest(workflow=workflow,host=host,name=name):
                    fixture=ProviderFixture(workflow,'valid')
                    with patch.dict(os.environ,{**ENV,'BANFEI_RUNTIME_MODEL_URL':'https://'+host,'BANFEI_RUNTIME_MODEL_NAME':name}),patch.object(httpx,'AsyncClient',side_effect=fixture.client):
                        req=packet(server.create_app(),workflow)
                        req.model.name=name;req.model.provider_route=model_route('https://'+host,name)
                        raw=asyncio.run(provider.completion(req,lambda _:None))
                    self.assertIsInstance(raw,str);self.assertEqual(json.loads(raw),inputs(workflow)[2])
                    sent=fixture.calls[0]
                    self.assertEqual(sent.get('thinking'),thinking)
                    self.assertEqual(sent['max_tokens'],2048 if workflow=='match' else 131072)
                    self.assertEqual((sent['temperature'],sent['top_p']),(.3,1))
                    self.assertEqual(sent['response_format'],{'type':'json_object'})
                    self.assertNotIn('reasoning_effort',sent);self.assertEqual(len(fixture.calls),1)

    def test_only_existing_timeout_policy_allows_retry_and_clears_stale_diagnostic(self):
        for outcome in ('timeout','timeout_then_success'):
            with self.subTest(outcome=outcome):
                fixture=ProviderFixture('match',outcome)
                with patch.dict(os.environ,ENV),patch.object(httpx,'AsyncClient',side_effect=fixture.client),TestClient(server.create_app()) as client:
                    req=packet(client.app,'match',retries=1);job,headers=final_job(client,req)
                    self.assertEqual(job['status'],'awaiting_retry');self.assertTrue(job['diagnostic']['retryable'])
                    self.assertEqual(len(fixture.calls),1)
                    r=client.post('/jobs/'+str(req.operation_id)+'/retry',headers=headers,
                        json={'incarnation':str(req.incarnation),'after_attempt':1})
                    self.assertEqual(r.status_code,202)
                    for _ in range(200):
                        job=client.get('/jobs/'+str(req.operation_id),headers=headers).json()
                        if job['status'] in ('completed','failed'):break
                        time.sleep(.005)
                    self.assertEqual(len(fixture.calls),2)
                    if outcome=='timeout':
                        self.assertEqual(job['diagnostic']['reason_code'],'model_timeout_exhausted')
                        self.assertFalse(job['diagnostic']['retryable'])
                    else:
                        self.assertEqual(job['status'],'completed');self.assertNotIn('diagnostic',job);self.assertNotIn('error',job)
                    self.assertNotIn(MARKER,json.dumps(job))

    def test_awaiting_timeout_state_boundaries_do_not_retain_old_diagnostics(self):
        for workflow in ('match','development'):
            for action in ('cancel','lease_expired','retry'):
                with self.subTest(workflow=workflow,action=action):
                    fixture=ProviderFixture(workflow,'timeout_then_success')
                    with patch.dict(os.environ,ENV),patch.object(httpx,'AsyncClient',side_effect=fixture.client),TestClient(server.create_app()) as client:
                        req=packet(client.app,workflow,retries=1);job,headers=final_job(client,req)
                        self.assertEqual(job['status'],'awaiting_retry')
                        self.assertEqual(job['diagnostic']['reason_code'],'model_timeout')
                        self.assertTrue(job['diagnostic']['retryable'])
                        path='/jobs/'+str(req.operation_id)
                        if action=='cancel':
                            response=client.delete(path,headers=headers)
                            self.assertEqual(response.status_code,200)
                        else:
                            if action=='lease_expired':
                                client.app.state.jobs[str(req.operation_id)]['_lease']=time.monotonic()-1
                            response=client.post(path+'/retry',headers=headers,
                                json={'incarnation':str(req.incarnation),'after_attempt':1})
                            self.assertEqual(response.status_code,409 if action=='lease_expired' else 202)
                        if action=='retry':
                            # Check the immediate acknowledgement, before execute() can
                            # clear metadata: this was the reviewed stale-response gap.
                            immediate=response.json()
                            self.assertEqual(immediate['status'],'running')
                            self.assertEqual(immediate['attempt'],2)
                            self.assertNotIn('diagnostic',immediate);self.assertNotIn('error',immediate)
                            for _ in range(200):
                                current=client.get(path,headers=headers).json()
                                if current['status']=='completed':break
                                time.sleep(.005)
                            self.assertEqual(current['status'],'completed')
                            self.assertNotIn('diagnostic',current);self.assertNotIn('error',current)
                            self.assertEqual(len(fixture.calls),2)
                        else:
                            current=client.get(path,headers=headers).json()
                            reason='vm_cancelled' if action=='cancel' else 'vm_lease_expired'
                            self.assertEqual(current['status'],'interrupted')
                            self.assertEqual(current['error'],reason)
                            self.assertEqual(current['diagnostic']['reason_code'],reason)
                            self.assertFalse(current['diagnostic']['retryable'])
                            self.assertEqual(current['diagnostic'],sanitize_diagnostic(current['diagnostic'],'interrupted'))
                            self.assertEqual(current['attempt'],1);self.assertEqual(len(fixture.calls),1)
                            if action=='cancel':self.assertEqual(response.json()['diagnostic'],current['diagnostic'])

    def test_remote_whitelist_rejects_secret_values_unknown_fields_and_bool_integers(self):
        unsafe={'reason_code':'output_reference_invalid','error_type':MARKER,'retryable':True,
                'upstream_http_status':True,'finish_reason':MARKER,'prompt':MARKER,'headers':{'Authorization':MARKER}}
        self.assertEqual(sanitize_diagnostic(unsafe,'failed'),{
            'reason_code':'output_reference_invalid','error_type':'ValueError','retryable':False})
        for value in (None,True,MARKER,{}, {'reason_code':MARKER}, {'reason_code':[MARKER]}):
            self.assertIsNone(sanitize_diagnostic(value))
        error=type(MARKER,(Exception,),{})(MARKER)
        self.assertNotIn(MARKER,json.dumps(diagnose(error)))
        self.assertFalse(sanitize_diagnostic({'reason_code':'model_timeout','retryable':True},'failed')['retryable'])

    def test_runtime_to_bridge_persists_and_admin_displays_only_safe_metadata(self):
        for workflow in ('match','development'):
            for case in ('length','schema','reference','http'):
                with self.subTest(workflow=workflow,case=case):
                    saved,error,fixture=self.bridge_case(workflow,case)
                    states=[v for k,v in saved.items() if k.startswith('runtime_stage:')]
                    self.assertEqual(len(states),1);state=states[0]
                    self.assertEqual(state['status'],'failed');self.assertEqual(state['error'],'runtime_execution_failed')
                    self.assertEqual(state['diagnostic'],error.runtime_diagnostic)
                    self.assertEqual(len(fixture.calls),1)
                    with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'BANFEI_ERROR_LOG_PATH':str(Path(d)/'errors.jsonl')}),error_diagnostics.diagnostic_scope(task_id='synthetic-task',response_excerpt=MARKER):
                        error_diagnostics.record_error(error)
                        record=error_diagnostics.recent_errors()[0]
                    self.assertEqual(record['runtime_diagnostic'],state['diagnostic'])
                    self.assertIn(state['diagnostic']['reason_code'],record['message'])
                    self.assertIsNone(record['response_excerpt'])
                    self.assertNotIn(MARKER,json.dumps(record)+json.dumps(saved)+str(error))

    def test_legacy_reply_without_diagnostic_still_fails_safely(self):
        saved,error,fixture=self.bridge_case('match','schema',legacy=True)
        state=next(v for k,v in saved.items() if k.startswith('runtime_stage:'))
        self.assertEqual(state['status'],'failed');self.assertEqual(state['error'],'runtime_execution_failed')
        self.assertNotIn('diagnostic',state);self.assertNotIsInstance(error,StageFailure)
        self.assertIn('explicitly retry',str(error));self.assertEqual(len(fixture.calls),1)

    def test_bridge_rebuilds_untrusted_diagnostic_before_storage_or_exception(self):
        saved,error,_=self.bridge_case('development','reference',tamper=True)
        state=next(v for k,v in saved.items() if k.startswith('runtime_stage:'))
        self.assertNotIn('error',state);self.assertNotIn('finish_reason',state['diagnostic'])
        self.assertFalse(state['diagnostic']['retryable'])
        self.assertNotIn(MARKER,json.dumps(saved)+str(error))

    def bridge_case(self,workflow,case,legacy=False,tamper=False):
        fixture=ProviderFixture(workflow,case);saved={};app=server.create_app()
        @contextlib.contextmanager
        def db():yield SimpleNamespace(lock_writer=lambda:None)
        class Adapter:
            def __enter__(self):self.client=TestClient(app).__enter__();return self
            def __exit__(self,*args):self.client.__exit__(*args)
            def request(self,method,url,**kwargs):
                parsed=urlsplit(url);path=parsed.path.split('/invocations',1)[1]
                if parsed.query:path+='?'+parsed.query
                response=self.client.request(method,path,**kwargs)
                if '/jobs' in path:
                    data=response.json()
                    if legacy:data.pop('diagnostic',None)
                    if tamper and 'diagnostic' in data:
                        data['diagnostic'].update(error_type=MARKER,finish_reason=MARKER,retryable=True,prompt=MARKER)
                        data['error']=MARKER
                    response=httpx.Response(response.status_code,json=data,request=response.request)
                return response
            def get(self,url,**kwargs):return self.request('GET',url,**kwargs)
            def post(self,url,**kwargs):return self.request('POST',url,**kwargs)
            def delete(self,url,**kwargs):return self.request('DELETE',url,**kwargs)
        with patch.dict(os.environ,ENV),patch.object(httpx,'AsyncClient',side_effect=fixture.client),patch.multiple(bridge,
                get_db=db,authorize=lambda *args:None,source_stamp=lambda _: 'same',
                load=lambda conn,key:copy.deepcopy(saved.get(key)),save=lambda conn,key,value:saved.update({key:copy.deepcopy(value)}),
                pinned_configuration=lambda *args:None,configuration_stamp=lambda cfg:{'fingerprint':'a'*64},
                model_config_from_record=lambda cfg:SimpleNamespace(base_url='https://api.deepseek.com',model='deepseek-flash',temperature=.3,top_p=1,max_tokens=131072),
                get_settings=lambda:SimpleNamespace(timeoutSeconds=300.0,timeoutRetries=3),client_for=Adapter),bridge.run_scope(workflow,str(uuid.uuid4()),str(uuid.uuid4())):
            stage,data,_=inputs(workflow)
            with self.assertRaises(ValueError) as caught:
                bridge.execute_stage(workflow,stage,data,{'_match_output_tokens':2048} if workflow=='match' else {},lambda: self.fail('local fallback'))
        return saved,caught.exception,fixture


if __name__=='__main__':unittest.main()
