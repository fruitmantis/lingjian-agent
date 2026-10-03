"""Synthetic initial-selection budget tests; no DB or external model requests."""
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
from backend.app import partner_match_context as context
from backend.agent_runtime import provider
from backend.agent_runtime.contracts import StageRequest, ModelOptions, digest, source_manifest, model_route
from backend.agent_runtime.match_types import InitialSelection
from backend.agent_runtime.prompts import matching
from backend.agent_runtime.workflows import validate_output, validate_budget, messages_for
from backend.app import runtime_bridge as bridge

BASE = 'https://synthetic-model.example.test/v1'
CONFIG = {'api_key_source':'db', 'api_key':'synthetic-only', 'base_url':BASE,
          'model_name':'deepseek-flash', 'temperature':.3, 'top_p':1., 'max_tokens':131072}
SCHEMA = InitialSelection.model_json_schema()
MESSAGES = matching('initial_selection', {'facts':{}, 'partners':[]})[0]

class InitialBudgetTests(unittest.TestCase):
    def budget(self, config=CONFIG, messages=MESSAGES, cap=None):
        return context.checked_config(config, messages, SCHEMA, context.INITIAL_CHAR_LIMIT, cap)

    def test_saved_admin_limits_are_honored_including_values_below_2048(self):
        for value in (1, 512, 2048, 4096, 16384):
            with self.subTest(value=value):
                original={**CONFIG, 'max_tokens':value}
                result,_,_=self.budget(original)
                self.assertEqual(result['_match_output_tokens'],value)
                self.assertEqual({k:v for k,v in result.items() if k!='_match_output_tokens'},original)
                self.assertNotIn('_match_output_tokens',original)

    def test_unknown_provider_uses_existing_context_remainder(self):
        result,_,estimate=self.budget()
        self.assertGreater(result['_match_output_tokens'],2048)
        self.assertLessEqual(result['_match_output_tokens'],CONFIG['max_tokens'])
        self.assertEqual(result['_match_output_tokens']+estimate,context.UNKNOWN_CONTEXT_CEILING)

    def test_known_provider_still_honors_saved_maximum(self):
        result,_,_=self.budget({**CONFIG,'base_url':'https://api.deepseek.com'})
        self.assertEqual(result['_match_output_tokens'],131072)
        # Observed VM metadata only, not billed provider usage or real material.
        with patch.object(context,'input_metrics',return_value=(58736,36741)):
            self.assertEqual(self.budget({**CONFIG,'base_url':'https://api.deepseek.com'})[0]['_match_output_tokens'],131072)
            with self.assertRaises(context.MatchInputBudgetError):self.budget()

    def test_context_boundary_never_emits_zero_or_negative_output(self):
        ceiling=context.UNKNOWN_CONTEXT_CEILING
        with patch.object(context,'input_metrics',return_value=(100,ceiling-1)):
            self.assertEqual(self.budget()[0]['_match_output_tokens'],1)
        for estimate in (ceiling,ceiling+1):
            with self.subTest(estimate=estimate),patch.object(context,'input_metrics',return_value=(100,estimate)):
                with self.assertRaises(context.MatchInputBudgetError):self.budget()

    def test_character_limit_remains_fail_closed(self):
        with self.assertRaises(context.MatchInputBudgetError):
            self.budget(messages=[{'role':'system','content':'甲'*61000}])

    def test_other_stages_use_saved_allowance_and_explicit_caller_caps_remain_valid(self):
        self.assertFalse(hasattr(context,'DETAIL_OUTPUT_TOKENS'))
        self.assertFalse(hasattr(context,'SUMMARY_OUTPUT_TOKENS'))
        self.assertGreater(self.budget()[0]['_match_output_tokens'],8192)
        for cap in (8192,512):
            self.assertEqual(self.budget(cap=cap)[0]['_match_output_tokens'],cap)
            with patch.object(context,'input_metrics',return_value=(100,context.UNKNOWN_CONTEXT_CEILING-cap+1)):
                with self.assertRaises(context.MatchInputBudgetError):self.budget(cap=cap)

    def test_existing_v2_provider_receives_budget_without_other_parameter_changes(self):
        data={'facts':{},'partners':[{'partnerId':str(uuid.uuid4())} for _ in range(179)]}
        messages=matching('initial_selection',data)[0]
        budget,_,_=self.budget(messages=messages)
        packet=StageRequest(task_id=uuid.uuid4(),run_id=uuid.uuid4(),session_id=uuid.uuid4(),
            operation_id=uuid.uuid4(),incarnation=uuid.uuid4(),workflow='match',stage='initial_selection',
            data=data,sources=source_manifest(data),snapshot=digest(data),model_fingerprint='a'*64,
            input_token_budget=262144,model=ModelOptions(provider_route=model_route(BASE,'deepseek-flash'),
                name='deepseek-flash',temperature=.3,top_p=1.,max_tokens=budget['_match_output_tokens'],
                timeout_seconds=300.,timeout_retries=3))
        output={'candidates':[{'partnerId':p['partnerId'],'verificationFocus':'核实'*75} for p in data['partners'][:12]]}
        InitialSelection.model_validate(output)
        calls=[]
        def respond(request):
            calls.append(json.loads(request.content))
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(output,ensure_ascii=False)}}]})
        original=httpx.AsyncClient
        def client(**kwargs):return original(transport=httpx.MockTransport(respond),**kwargs)
        environment={'BANFEI_RUNTIME_MODEL_URL':BASE,'BANFEI_RUNTIME_MODEL_NAME':'deepseek-flash',
                     'BANFEI_RUNTIME_MODEL_KEY':'synthetic-only','BANFEI_RUNTIME_CONTEXT_TOKENS':'262144'}
        with patch.dict(os.environ,environment),patch.object(provider.httpx,'AsyncClient',client):
            raw=asyncio.run(provider.completion(packet,lambda _:None))
        self.assertEqual(validate_output(packet,raw),output)
        self.assertEqual(len(calls),1)
        sent=calls[0]
        self.assertEqual(set(sent),{'model','messages','response_format','temperature','top_p','max_tokens'})
        self.assertEqual({k:v for k,v in sent.items() if k!='messages'},
            {'model':'deepseek-flash','response_format':{'type':'json_object'},'temperature':.3,
             'top_p':1.,'max_tokens':budget['_match_output_tokens']})
        self.assertEqual((packet.model.timeout_seconds,packet.model.timeout_retries),(300.,3))
        self.assertNotIn('thinking',sent)


    def runtime_packet(self, data, output):
        return StageRequest(task_id=uuid.uuid4(),run_id=uuid.uuid4(),session_id=uuid.uuid4(),
            operation_id=uuid.uuid4(),incarnation=uuid.uuid4(),workflow='match',stage='initial_selection',
            data=data,sources=source_manifest(data),snapshot=digest(data),model_fingerprint='a'*64,
            input_token_budget=bridge.RUNTIME_INPUT_BUDGET,model=ModelOptions(
                provider_route=model_route('https://api.deepseek.com','deepseek-flash'),
                name='deepseek-flash',temperature=.3,top_p=1.,max_tokens=output,
                timeout_seconds=300.,timeout_retries=3))

    def runtime_bytes(self, data):
        # Independent reconstruction of the deployed v2 message/schema envelope.
        packet=self.runtime_packet(data,1)
        messages,schema=messages_for(packet)
        instruction='Return only a JSON object matching this JSON schema. No extra fields: '+json.dumps(schema,ensure_ascii=False)
        messages=[{**messages[0],'content':messages[0]['content']+'\n\n'+instruction},*messages[1:]]
        return len(json.dumps(messages,ensure_ascii=False).encode('utf-8'))

    def test_qa_cross_budget_reproductions_preserve_all_input(self):
        for count,size in [(1,44000),(12,3600)]:
            with self.subTest(count=count,size=size):
                data={'facts':{},'partners':[{'partnerId':str(uuid.uuid4()),'name':'合成伙伴',
                    'capabilities':'合成能力','industries':'制造','regions':'广东','summary':'',
                    'intro':'甲'*size,'evidenceState':'资料有限，待核实',
                    'visibleCaseCount':0,'visibleDeliverableCount':0} for _ in range(count)]}
                before=json.dumps(data,ensure_ascii=False,sort_keys=True)
                messages=matching('initial_selection',data)[0]
                old_packet=self.runtime_packet(data,131072)
                with self.assertRaises(ValueError):validate_budget(old_packet)
                with patch.dict(os.environ,{'BANFEI_MATCH_EXECUTOR':'runtime'}):
                    config,_,_=self.budget({**CONFIG,'base_url':'https://api.deepseek.com'},messages)
                count_bytes=self.runtime_bytes(data)
                self.assertEqual(config['_match_output_tokens'],262144-count_bytes)
                self.assertGreater(config['_match_output_tokens'],2048)
                packet=self.runtime_packet(data,config['_match_output_tokens'])
                validate_budget(packet)
                self.assertEqual(json.dumps(packet.data,ensure_ascii=False,sort_keys=True),before)
                self.assertEqual(json.dumps(data,ensure_ascii=False,sort_keys=True),before)
                with self.assertRaises(ValueError):
                    validate_budget(packet.model_copy(update={'model':packet.model.model_copy(update={'max_tokens':packet.model.max_tokens+1})}))

    def test_serialized_utf8_and_escaping_count_towards_runtime_remainder(self):
        data={'facts':{},'partners':[{'partnerId':'synthetic','intro':'甲😀\\\"\n'*1200}]}
        size=self.runtime_bytes(data)
        self.assertGreater(size,len(json.dumps(data,ensure_ascii=False)))
        with patch.object(bridge,'RUNTIME_INPUT_BUDGET',size+500):
            self.assertEqual(bridge.initial_selection_output_limit(data,131072),500)
            self.assertEqual(bridge.initial_selection_output_limit(data,128),128)
            self.assertEqual(bridge.initial_selection_output_limit(data,1),1)
        with patch.object(bridge,'RUNTIME_INPUT_BUDGET',size+1):
            self.assertEqual(bridge.initial_selection_output_limit(data,131072),1)
        for ceiling in (size,size-1):
            with patch.object(bridge,'RUNTIME_INPUT_BUDGET',ceiling):
                with self.assertRaises(context.MatchInputBudgetError):bridge.initial_selection_output_limit(data,131072)

    def test_runtime_only_limit_does_not_change_local_executor(self):
        data={'facts':{},'partners':[{'partnerId':'synthetic','intro':'甲'*44000}]}
        messages=matching('initial_selection',data)[0]
        with patch.dict(os.environ,{'BANFEI_MATCH_EXECUTOR':'local'}):
            self.assertEqual(self.budget({**CONFIG,'base_url':'https://api.deepseek.com'},messages)[0]['_match_output_tokens'],131072)


    def test_protocol_output_cap_accepts_all_admin_budget_boundaries(self):
        from backend.app.routers.model_config import ModelConfigUpdate
        ceiling=ModelOptions.model_json_schema()['properties']['max_tokens']['maximum']
        self.assertEqual(bridge.RUNTIME_OUTPUT_BUDGET,ceiling)
        self.assertEqual(bridge.RUNTIME_INPUT_BUDGET,StageRequest.model_json_schema()['properties']['input_token_budget']['maximum'])
        for size in (4,44000):
            data={'facts':{},'partners':[{'partnerId':'synthetic','intro':'甲'*size}]}
            messages=matching('initial_selection',data)[0]
            remainder=bridge.RUNTIME_INPUT_BUDGET-self.runtime_bytes(data)
            for saved in (1,512,2048,131071,131072,131073,384000):
                with self.subTest(size=size,saved=saved):
                    self.assertEqual(ModelConfigUpdate(maxTokens=saved).maxTokens,saved)
                    config={**CONFIG,'base_url':'https://api.deepseek.com','max_tokens':saved}
                    with patch.dict(os.environ,{'BANFEI_MATCH_EXECUTOR':'runtime'}):
                        checked,_,_=self.budget(config,messages)
                    effective=checked['_match_output_tokens']
                    self.assertEqual(effective,min(saved,ceiling,remainder))
                    packet=self.runtime_packet(data,effective)
                    validate_budget(packet)
                    self.assertEqual(packet.data,data)
                    self.assertEqual(config['max_tokens'],saved)
        from pydantic import ValidationError
        for invalid in (0,-1,ceiling+1):
            with self.subTest(invalid=invalid),self.assertRaises(ValidationError):
                self.runtime_packet({'facts':{},'partners':[]},invalid)

    def test_other_wire_constraints_still_reject_without_relaxation(self):
        from pydantic import ValidationError
        from backend.app.routers.model_config import ModelConfigUpdate
        # These pre-existing admin/protocol differences are not silently clamped.
        for admin,wire in [({'temperature':3.0},{'temperature':3.0}),
                           ({'topP':0.0},{'top_p':0.0}),
                           ({'modelName':'x'*201},{'name':'x'*201})]:
            ModelConfigUpdate(**admin)
            base=self.runtime_packet({'facts':{},'partners':[]},2048).model.model_dump()
            with self.assertRaises(ValidationError):ModelOptions.model_validate({**base,**wire})
        for count in (500,501):
            data={'facts':{},'partners':[{'partnerId':'p'+str(i)} for i in range(count)]}
            if count==500:validate_budget(self.runtime_packet(data,2048))
            else:
                with self.assertRaises(ValidationError):self.runtime_packet(data,2048)
        for length in (200,201):
            data={'facts':{},'partners':[{'partnerId':'x'*length}]}
            if length==200:validate_budget(self.runtime_packet(data,2048))
            else:
                with self.assertRaises(ValidationError):self.runtime_packet(data,2048)
        with self.assertRaises(ValidationError):self.runtime_packet({'facts':{},'partners':[],'unexpected':'synthetic'},2048)

if __name__=='__main__':unittest.main()
