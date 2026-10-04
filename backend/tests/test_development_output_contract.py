"""Output-shape regressions for the real-provider extra-field failure."""
import json
import uuid

import pytest

from backend.app import development_engine as engine, development_model as model
from backend.app import development_lifecycle as life, development_views as views
from backend.app.ai_client import completion_payload
from backend.app.development_types import Understanding, Submit, DevelopmentRequest, Conversation
from backend.app.model_resolver import model_config_from_record
from backend.tests.test_optional_development_partner import replay, create
from backend.tests.test_development_lifecycle import prepared


def test_understanding_wire_prompt_derives_output_keys_from_schema(replay, monkeypatch):
    original_schema = Understanding.model_json_schema()
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
            assert json.dumps(list(schema['properties']), ensure_ascii=False) in prompt
            assert json.dumps(schema, ensure_ascii=False) in prompt
            assert schema['additionalProperties'] is False
            assert '用户自述基础的更新只返回 effective_baseline' in prompt
            assert '即使值为空字符串或 null' in prompt
            assert 'intent_note' not in schema['properties']
            assert 'request_known_baseline' not in schema['properties']
            assert wire['response_format'] == {'type': 'json_object'}
        return original_complete(config, messages, schema)
    monkeypatch.setattr(model, 'completion', capture)
    accepted, detail = create(replay)
    assert len(observed) == 1
    assert observed[0]['current'] is None and observed[0]['recent_exchanges'] == []
    assert 'known_baseline' in observed[0]['request']
    assert detail['plan']['current_version_id'] and detail['runs'][0]['status'] == 'ready'
    assert Understanding.model_json_schema() == original_schema


@pytest.mark.parametrize('field', ['intent_note', 'request_known_baseline'])
@pytest.mark.parametrize('existing', [False, True])
def test_unknown_empty_fields_fail_without_extra_call_or_version(replay, monkeypatch, field, existing):
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
        result[field] = ''  # Matches the real failure; even an empty extra is invalid.
        return json.dumps(result, ensure_ascii=False)
    monkeypatch.setattr(model, 'completion', invalid)
    engine.execute(run['run_id'])
    after = views.detail(accepted['plan_id'], user)
    assert sent == ['Understanding']
    assert after['runs'][0]['status'] == 'failed'
    assert after['plan']['current_version_id'] == current
    assert after['versions'] == before['versions']
    if existing:
        assert after['payload'] == before['payload']


@pytest.mark.parametrize('statement', [
    '未关联伙伴资料，没有组织侧能力记载可供参考，因此仅能从用户提供的信息出发组织资源建议。',
    '没有相关能力的记录，能力情况待核实。',
    '没有相关能力证据，不能据此推断实际水平。',
    '没有能力记录而能力仍待核实。',
    '没有相关证据，能力情况未知。',
])
def test_absent_capability_evidence_is_not_absent_capability(statement):
    engine.strong_guard({'partner_assessment': statement})


@pytest.mark.parametrize('statement', [
    '没有开发能力',
    '没有相关能力。资料待补充。',
    '没有开发能力，但有学习记录。',
    '没有组织侧能力记载可供参考；但确认该伙伴不具备开发能力。',
    '没有能力证据；没有开发能力。',
    '没有能力记录；学完课程就具备开发能力。',
    '没有能力证据；能力已提升。',
    '没有开发能力\n证据已提供。',
    '没有开发能力\n的记录已提供。',
])
def test_evidence_phrase_does_not_hide_an_actual_strong_claim(statement):
    with pytest.raises(engine.InvalidOutput, match='Unsupported capability conclusion'):
        engine.strong_guard({'partner_assessment': statement})


@pytest.mark.parametrize('statement', [
    '推荐课程与实验不构成能力证明，学完不代表已具备迁移回退与验证的项目能力。',
    '学完并不意味着已经具备开发能力。',
    '学完不等于具备项目能力。',
])
def test_negated_learning_claim_is_not_a_capability_guarantee(statement):
    engine.strong_guard({'limitations': [statement]})


@pytest.mark.parametrize('statement', [
    '学完就具备开发能力。',
    '学完不代表已具备基础能力，但学完课程就具备开发能力。',
    '学完不代表已具备基础能力，但能力已提升。',
    '学完不代表已具备基础能力；确认该伙伴不具备开发能力。',
    '学完不代表不具备开发能力。',
])
def test_local_learning_negation_does_not_hide_guarantees_or_other_claims(statement):
    with pytest.raises(engine.InvalidOutput, match='Unsupported capability conclusion'):
        engine.strong_guard({'limitations': [statement]})
