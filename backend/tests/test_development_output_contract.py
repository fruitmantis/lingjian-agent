"""Output-shape regressions for the real-provider extra-field failure."""
import json
import uuid

import pytest

from backend.app import development_engine as engine, development_model as model
from backend.app import development_lifecycle as life, development_views as views
from backend.app.ai_client import completion_payload
from backend.app.development_types import Understanding, Submit, DevelopmentRequest, Conversation, Revise, AdviceOutput
from backend.app.model_resolver import model_config_from_record
from backend.tests.test_optional_development_partner import replay, create
from backend.tests.test_development_lifecycle import prepared
from backend.tests.test_development_engine import scenario, execute


def test_understanding_wire_prompt_derives_output_keys_from_schema(replay, monkeypatch):
    original_schema = Understanding.model_json_schema()
    original_advice_schema = AdviceOutput.model_json_schema()
    observed = []
    original_complete = replay[2]
    def capture(config, messages, schema):
        if schema['title'] == 'Understanding':
            payload = json.loads(messages[-1]['content'])
            observed.append(payload)
            # Inspect the final HTTP payload, including the complete schema appended
            # by the common adapter, without accessing a real provider.
            wire = completion_payload(model_config_from_record(config), messages, schema)
            prompt = wire['messages'][0]['content']
            assert json.dumps(schema, ensure_ascii=False) in prompt
            assert schema.get('additionalProperties') is not False
            assert 'effective_baseline' in schema['required']
            assert 'used_refs' in schema['required'] and 'used_profile_chapters' in schema['required']
            assert 'intent_note' not in schema['properties']
            assert 'request_known_baseline' not in schema['properties']
            assert wire['response_format'] == {'type': 'json_object'}
        elif schema['title'] == 'AdviceOutput':
            wire = completion_payload(model_config_from_record(config), messages, schema)
            prompt = wire['messages'][0]['content']
            assert json.dumps(schema, ensure_ascii=False) in prompt
            assert 'interpretation 简洁概括目标' not in prompt
            assert 'partner_assessment 用一段业务语言' not in prompt
            assert 'interpretation' not in schema['properties']
            assert schema.get('additionalProperties') is not False
            assert wire['response_format'] == {'type': 'json_object'}
        return original_complete(config, messages, schema)
    monkeypatch.setattr(model, 'completion', capture)
    accepted, detail = create(replay)
    assert len(observed) == 1
    assert observed[0]['current'] is None and observed[0]['recent_exchanges'] == []
    assert 'known_baseline' in observed[0]['request']
    assert detail['plan']['current_version_id'] and detail['runs'][0]['status'] == 'ready'
    assert Understanding.model_json_schema() == original_schema
    assert AdviceOutput.model_json_schema() == original_advice_schema


@pytest.mark.parametrize('field', ['intent_note', 'request_known_baseline'])
@pytest.mark.parametrize('existing', [False, True])
def test_unknown_empty_fields_project_without_extra_call(replay, monkeypatch, field, existing):
    user = replay[0][0]
    if existing:
        accepted, before = create(replay)
        current = before['plan']['current_version_id']
        run = views.converse(accepted['plan_id'], Conversation(
            submission_id=str(uuid.uuid4()), based_on_version_id=current,
            message='为什么推荐这个方向？'), user)
    else:
        run = life.create(Submit(submission_id=str(uuid.uuid4()), request=DevelopmentRequest(
            development_direction='合成验证：提升数据库迁移能力')), user)
        accepted = run
        before = views.detail(accepted['plan_id'], user)
        current = None
    sent = []
    def invalid(config, messages, schema):
        sent.append(schema['title'])
        result = json.loads(replay[2](config, messages, schema))
        result[field] = ''  # Unknown model-only data is discarded before guard and persistence.
        return json.dumps(result, ensure_ascii=False)
    monkeypatch.setattr(model, 'completion', invalid)
    engine.execute(run['run_id'])
    after = views.detail(accepted['plan_id'], user)
    assert sent == (['Understanding'] if existing else ['Understanding','AdviceOutput'])
    assert after['runs'][0]['status'] == 'ready'
    assert field not in str(after['payload'])
    if existing:
        assert after['plan']['current_version_id'] == current and after['versions'] == before['versions']
        assert after['payload'] == before['payload']
    else:assert after['plan']['current_version_id'] and len(after['versions'])==1










@pytest.mark.parametrize('existing', [False, True])
def test_extra_interpretation_in_generation_is_discarded(replay, monkeypatch, existing):
    user = replay[0][0]
    if existing:
        accepted, before = create(replay)
        current = before['plan']['current_version_id']
        run = life.revise(accepted['plan_id'], Revise(
            submission_id=str(uuid.uuid4()), based_on_version_id=current,
            instruction='重新规划能力发展建议'), user)
    else:
        accepted = life.create(Submit(submission_id=str(uuid.uuid4()), request=DevelopmentRequest(
            development_direction='合成验证：数据库迁移能力发展')), user)
        run = accepted
        before = views.detail(accepted['plan_id'], user)
        current = None
    sent = []
    def invalid(config, messages, schema):
        sent.append(schema['title'])
        output = json.loads(replay[2](config, messages, schema))
        if schema['title'] == 'Understanding' and existing:
            output['action'] = 'regenerate'
        if schema['title'] == 'AdviceOutput':
            output['interpretation'] = '不属于本阶段响应的合成说明'
        return json.dumps(output, ensure_ascii=False)
    monkeypatch.setattr(model, 'completion', invalid)
    engine.execute(run['run_id'])
    after = views.detail(accepted['plan_id'], user)
    assert sent == ['Understanding', 'AdviceOutput']
    assert after['runs'][0]['status'] == 'ready'
    assert after['plan']['current_version_id'] != current
    assert len(after['versions'])==len(before['versions'])+1
    assert '不属于本阶段响应的合成说明' not in str(after['payload'])






def test_generation_persists_a_denied_inference_in_the_final_answer(replay, monkeypatch):
    text='以下不把未提供经验当作没有相应能力。仅依据明确自述和合成目录提出建议。'
    original=replay[2]
    def complete(config,messages,schema):
        result=json.loads(original(config,messages,schema))
        if schema['title']=='AdviceOutput':result['answer']=text
        return json.dumps(result,ensure_ascii=False)
    monkeypatch.setattr(model,'completion',complete)
    _, detail=create(replay)
    assert detail['runs'][0]['status']=='ready'
    assert detail['plan']['current_version_id']
    assert detail['payload']['answer']==text








def test_generation_persists_the_actual_denied_learning_note(scenario,monkeypatch):
    note='可作为动手验证载体，不表示学完即具备完整集成能力。'
    original=scenario[2];candidate=None
    def complete(config,messages,schema):
        nonlocal candidate
        output=json.loads(original(config,messages,schema))
        if schema['title']=='AdviceOutput':
            assert output['stages'] and output['stages'][0]['items']
            item=output['stages'][0]['items'][0]
            pool=json.loads(messages[-1]['content'])['candidates']
            candidate=next(r for r in pool if r['source_id']==item['source_id'])
            item['note']=note
        return json.dumps(output,ensure_ascii=False)
    monkeypatch.setattr(model,'completion',complete)
    accepted,run,payload=execute(scenario)
    detail=views.detail(accepted['plan_id'],scenario[0][0])
    assert run['status']=='ready' and detail['plan']['current_version_id']
    item=payload['stages'][0]['items'][0]
    assert item['note']==note
    assert candidate and tuple(item[k] for k in ('source_type','source_id','source_version'))==tuple(
        candidate[k] for k in ('source_type','source_id','source_version'))
    assert detail['payload']['stages'][0]['items'][0]['note']==note
