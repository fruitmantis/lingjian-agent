"""Offline VM/cloud parity and wire-budget regressions for main synchronization."""
import asyncio
import json
import os
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import httpx
from backend.agent_runtime import provider, workflows
from backend.agent_runtime.contracts import StageRequest, ModelOptions, model_route, digest, source_manifest
from backend.agent_runtime.development_types import Understanding
from backend.agent_runtime.diagnostics import StageFailure
from backend.agent_runtime.prompts import development
from backend.agent_runtime.provider_options import provider_request_options
from backend.app import ai_client, runtime_bridge as bridge, development_engine as engine


def data_for(stage):
    if stage == 'understanding': return {'requirement':'合成需求','standard_tags':[]}
    if stage == 'initial_selection': return {'facts':{},'partners':[{'partnerId':'p1','intro':'合成'}]}
    if stage == 'detailed_review': return {'facts':{},'candidates':[{'partnerId':'p1','intro':'合成'}]}
    data={'request':{'target_partner_id':None,'development_direction':'合成学习'},'constraints':{},
          'profile':{},'formal_tags':[],'current':None,'recent_exchanges':[],'message':'合成'}
    if stage in ('plan','patch'):
        data.update(analysis={},understanding={'edit_item_ids':[],'edit_answer_spans':[]},candidates=[])
    return data


def packet(stage, data, output):
    workflow='match' if stage in ('understanding','initial_selection','detailed_review') else 'development'
    return StageRequest(task_id=uuid.uuid4(),run_id=uuid.uuid4(),session_id=uuid.uuid4(),
        operation_id=uuid.uuid4(),incarnation=uuid.uuid4(),workflow=workflow,stage=stage,
        data=data,sources=source_manifest(data),snapshot=digest(data),model_fingerprint='a'*64,
        input_token_budget=bridge.RUNTIME_INPUT_BUDGET,model=ModelOptions(
            provider_route=model_route('https://api.deepseek.com','deepseek-flash'),
            name='deepseek-flash',temperature=.3,top_p=1.,max_tokens=output,
            timeout_seconds=300.,timeout_retries=3))


class MainSyncTests(unittest.TestCase):
    def test_provider_option_is_shared_and_does_not_disable_other_models(self):
        self.assertIs(ai_client.provider_request_options,provider_request_options)
        self.assertIs(provider.provider_request_options,provider_request_options)
        for name in ('deepseek-flash','deepseek-v4-flash'):
            self.assertEqual(provider_request_options('https://api.deepseek.com/v1',name),{'thinking':{'type':'enabled'}})
            self.assertEqual(provider_request_options('https://api.deepseek.com.evil.test',name),{})
        self.assertEqual(provider_request_options('https://dashscope.aliyuncs.com/compatible-mode/v1','glm-5.3'),{})
        self.assertEqual(provider_request_options('https://api.deepseek.com','unknown'),{})

    def test_all_six_stages_count_complete_messages_and_keep_protocol_ceiling(self):
        self.assertEqual(bridge.RUNTIME_INPUT_BUDGET,262144)
        self.assertEqual(bridge.RUNTIME_OUTPUT_BUDGET,131072)
        for stage in workflows.CONTRACTS:
            data=data_for(stage);original=json.dumps(data,ensure_ascii=False,sort_keys=True)
            wire=packet(stage,data,1)
            messages,schema=workflows.messages_for(wire)
            instruction='Return only a JSON object matching this JSON schema. No extra fields: '+json.dumps(schema,ensure_ascii=False)
            complete=[{**messages[0],'content':messages[0]['content']+'\n\n'+instruction},*messages[1:]]
            size=len(json.dumps(complete,ensure_ascii=False).encode('utf-8'))
            for saved in (1,512,2048,8192,131072,131073,384000):
                with self.subTest(stage=stage,saved=saved):
                    output=bridge.stage_output_limit(wire.workflow,stage,data,saved)
                    self.assertEqual(output,min(saved,131072,262144-size))
                    workflows.validate_budget(packet(stage,data,output))
            for remaining in (1,4096):
                with patch.object(bridge,'RUNTIME_INPUT_BUDGET',size+remaining):
                    output=bridge.stage_output_limit(wire.workflow,stage,data,384000)
                    self.assertEqual(output,remaining)
                    valid=packet(stage,data,output);workflows.validate_budget(valid,ceiling=size+remaining)
                    with self.assertRaises(StageFailure):
                        workflows.validate_budget(valid.model_copy(update={'model':valid.model.model_copy(update={'max_tokens':output+1})}),ceiling=size+remaining)
            for remaining in (0,-1):
                with patch.object(bridge,'RUNTIME_INPUT_BUDGET',size+remaining),self.assertRaises(StageFailure):
                    bridge.stage_output_limit(wire.workflow,stage,data,384000)
            self.assertEqual(json.dumps(data,ensure_ascii=False,sort_keys=True),original)

    def test_shared_prompt_and_strict_schema_keep_unknown_fields_invalid(self):
        before=Understanding.model_json_schema();data=data_for('analyze')
        messages,schema=development('analyze',data,Understanding)
        self.assertIn(json.dumps(list(schema['properties']),ensure_ascii=False),messages[0]['content'])
        self.assertEqual(Understanding.model_json_schema(),before)
        self.assertFalse(schema['additionalProperties'])
        valid={'target_partner_id':None,'intent':'explore','interpretation':'合成方向','in_scope':True,
               'action':'answer','effective_direction':'合成方向','effective_baseline':'','answer':'合成答复'}
        wire=packet('analyze',data,10000)
        workflows.validate_output(wire,json.dumps(valid))
        for key in ('intent_note','request_known_baseline'):
            with self.assertRaises(ValueError):workflows.validate_output(wire,json.dumps({**valid,key:''}))
            with self.assertRaises(engine.InvalidOutput):engine.parse(json.dumps({**valid,key:''}),Understanding,[])

    def test_capability_evidence_boundary_is_identical_on_vm_and_cloud(self):
        accepted=['没有组织侧能力记载可供参考。','没有能力的证据，实际情况待核实。',
                  '没有能力记录而能力仍待核实。','没有相关证据，能力情况未知。']
        rejected=['没有开发能力','没有相关能力。资料待补充。','没有能力证据；没有开发能力。',
                  '没有能力记录；学完课程就具备开发能力。','没有能力证据；能力已提升。',
                  '没有开发能力\n证据已提供。','确认该伙伴不具备开发能力']
        for text in accepted:
            with self.subTest(text=text):
                value={'nested':[{'partner_assessment':text}]}
                workflows.strong_guard(value);engine.strong_guard(value)
        for text in rejected:
            with self.subTest(text=text):
                value={'nested':[{'partner_assessment':text}]}
                with self.assertRaises(StageFailure):workflows.strong_guard(value)
                with self.assertRaises(engine.InvalidOutput):engine.strong_guard(value)

    def test_runtime_long_reasoning_keeps_final_answer_and_never_retries_length(self):
        answer={'target_partner_id':None,'answer':'合成答复'*900,'stages':[]}
        raw=json.dumps(answer,ensure_ascii=False);wire=packet('plan',data_for('plan'),131072)
        original=httpx.AsyncClient
        for finish in ('stop','length'):
            calls=[]
            def respond(request):
                calls.append(json.loads(request.content))
                return httpx.Response(200,json={'choices':[{'finish_reason':finish,'message':{
                    'reasoning_content':'合成思考'*15000,'content':raw}}]})
            def client(**kwargs):return original(transport=httpx.MockTransport(respond),**kwargs)
            env={'BANFEI_RUNTIME_MODEL_URL':'https://api.deepseek.com','BANFEI_RUNTIME_MODEL_NAME':'deepseek-flash',
                 'BANFEI_RUNTIME_MODEL_KEY':'synthetic-only','BANFEI_RUNTIME_CONTEXT_TOKENS':'262144'}
            with patch.dict(os.environ,env),patch.object(provider.httpx,'AsyncClient',client):
                if finish=='stop':self.assertEqual(asyncio.run(provider.completion(wire,lambda _:None)),raw)
                else:
                    with self.assertRaises(StageFailure):asyncio.run(provider.completion(wire,lambda _:None))
            self.assertEqual(len(calls),1)
            self.assertEqual(calls[0]['thinking'],{'type':'enabled'})
            self.assertEqual(calls[0]['max_tokens'],131072)

if __name__=='__main__':unittest.main()
