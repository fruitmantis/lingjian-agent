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
            assert json.dumps(list(schema['properties']), ensure_ascii=False) in prompt
            assert json.dumps(schema, ensure_ascii=False) in prompt
            assert schema['additionalProperties'] is False
            assert '用户自述基础的更新只返回 effective_baseline' in prompt
            assert '即使值为空字符串或 null' in prompt
            assert 'intent_note' not in schema['properties']
            assert 'request_known_baseline' not in schema['properties']
            assert wire['response_format'] == {'type': 'json_object'}
        elif schema['title'] == 'AdviceOutput':
            wire = completion_payload(model_config_from_record(config), messages, schema)
            prompt = wire['messages'][0]['content']
            assert json.dumps(list(schema['properties']), ensure_ascii=False) in prompt
            assert json.dumps(schema, ensure_ascii=False) in prompt
            assert 'interpretation 简洁概括目标' not in prompt
            assert 'partner_assessment 用一段业务语言' not in prompt
            assert 'interpretation' not in schema['properties']
            assert schema['additionalProperties'] is False
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
    '当前没有来自用户自述的团队能力与经验信息，无法评估当前基础。',
    '没有相关能力信息，当前水平待核实。',
])
def test_absent_capability_evidence_is_not_absent_capability(statement):
    engine.strong_guard({'partner_assessment': statement})


@pytest.mark.parametrize('statement', [
    '没有开发能力',
    '没有相关能力。资料待补充。',
    '没有开发能力，但有学习记录。',
    '没有组织侧能力记载可供参考；但确认该伙伴不具备开发能力。',
    '没有能力证据；没有开发能力。',
    '没有团队能力与经验信息；没有开发能力。',
    '没有能力信息；学完课程就具备开发能力。',
    '没有能力信息；能力已提升。',
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
    '学完不代表不具备开发能力。',
])
def test_negated_learning_claim_is_not_a_capability_guarantee(statement):
    engine.strong_guard({'limitations': [statement]})


@pytest.mark.parametrize('statement', [
    '学完就具备开发能力。',
    '学完不代表已具备基础能力，但学完课程就具备开发能力。',
    '学完不代表已具备基础能力，但能力已提升。',
    '学完不代表已具备基础能力；确认该伙伴不具备开发能力。',
])
def test_local_learning_negation_does_not_hide_guarantees_or_other_claims(statement):
    with pytest.raises(engine.InvalidOutput, match='Unsupported capability conclusion'):
        engine.strong_guard({'limitations': [statement]})


@pytest.mark.parametrize('existing', [False, True])
def test_extra_interpretation_in_generation_still_fails_without_overwriting_version(replay, monkeypatch, existing):
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
    assert after['runs'][0]['status'] == 'failed'
    assert after['plan']['current_version_id'] == current
    assert after['versions'] == before['versions']
    assert after['payload'] == before['payload']


@pytest.mark.parametrize('statement', [
    '以下不把未提供经验当作没有相应能力。',
    '不能据此认定该团队没有开发能力。',
    '不能仅凭资料不足推断该团队没有开发能力。',
    '资料未提供不代表没有开发能力。',
    '并非没有开发能力，现有基础待核实。',
    '无法确认该伙伴不具备开发能力。',
    '不能明确不满足，仍需核实。',
    '“没有能力”这一判断未经证实。',
    '原答复引用“没有开发能力”这种说法不成立。',
    '“没有开发能力”无法确认。',
    '资料缺失与“没有能力”不能等同。',
    '“没有能力”与“没有能力记录”不是一回事。',
    '没有开发能力和没有能力记录不能等同。',
    '学完课程不代表具备开发能力。',
    '不能保证学完课程就具备开发能力。',
    '不能据此确认能力已提升。',
    '“学完课程就具备开发能力”这一结论未经证实。',
    '“能力已提升”这一判断需要核实。',
    '以下不把未提供经验当作没有相应能力，不能据此确认不足。',
])
def test_nonassertive_capability_mentions_are_not_factual_conclusions(statement):
    engine.strong_guard({'answer': statement, 'limitations': [statement]})


@pytest.mark.parametrize('statement', [
    '该团队没有开发能力。',
    '资料不足，因此确认该团队不具备开发能力。',
    '资料未提供，所以团队没有开发能力。',
    '结论就是“没有开发能力”。',
    '该团队“没有开发能力”不代表无法学习。',
    '不能认定没有能力，但该团队没有开发能力。',
    '以下不把未提供经验当作没有相应能力；确认该伙伴不具备开发能力。',
    '以下不把未提供经验当作没有相应能力并确认不足。',
    '“没有能力”这一判断未经证实，不过明确不满足。',
    '原答复引用“没有能力”这种说法不成立。能力已提升。',
    '资料不足不代表没有能力，学完课程就具备开发能力。',
    '不能保证学完课程就具备开发能力，但学完就具备开发能力。',
    '不能确认能力已提升，能力已提升。',
    '不得不承认该团队没有开发能力。',
    '不能不确认该伙伴不具备开发能力。',
])
def test_disclaimers_quotes_and_contrasts_do_not_hide_actual_assertions(statement):
    with pytest.raises(engine.InvalidOutput, match='Unsupported capability conclusion'):
        engine.strong_guard({'answer': statement})


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


@pytest.mark.parametrize('relation', ['不代表','不表示','不能据此认为','并不意味着'])
@pytest.mark.parametrize('position', ['before_learning','inside_learning'])
def test_denied_learning_relation_has_local_polarity(relation,position):
    statement=(relation+'学完即具备完整集成能力。' if position=='before_learning'
               else '学完'+relation+'即具备完整集成能力。')
    engine.strong_guard({'answer':statement,'stages':[{'items':[{'note':statement}]}]})


@pytest.mark.parametrize('statement', [
    '表示学完即具备完整集成能力。',
    '这意味着学完即具备完整集成能力。',
    '可以据此认为学完即具备完整集成能力。',
    '不得不承认学完即具备完整集成能力。',
    '不能不表示学完即具备完整集成能力。',
    '并非不表示学完即具备完整集成能力。',
    '不表示学完即具备完整集成能力，但学完就具备开发能力。',
    '不代表学完即具备完整集成能力；能力已提升。',
    '不能据此认为学完即具备完整集成能力，确认该团队不具备开发能力。',
    '并不意味着学完即具备完整集成能力，然而学完就具备开发能力。',
    '不表示学完即具备完整集成能力，因此学完就具备开发能力。',
    '不表示学完即具备完整集成能力并且学完就具备开发能力。',
    '不表示该实验难度很高并认为学完即具备完整集成能力。',
])
def test_negative_learning_relation_does_not_cover_a_new_assertion(statement):
    with pytest.raises(engine.InvalidOutput,match='Unsupported capability conclusion'):
        engine.strong_guard({'answer':statement})


def test_denial_in_another_field_cannot_cover_a_learning_guarantee():
    with pytest.raises(engine.InvalidOutput,match='Unsupported capability conclusion'):
        engine.strong_guard({'limitations':['不表示学完即具备完整集成能力。'],
                             'stages':[{'items':[{'note':'学完就具备开发能力。'}]}]})


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


@pytest.mark.parametrize('existing',[False,True])
def test_actual_learning_guarantee_fails_without_overwriting_history(scenario,monkeypatch,caplog,existing):
    user=scenario[0][0]
    if existing:
        accepted,_,_=execute(scenario)
        before=views.detail(accepted['plan_id'],user)
        run=life.revise(accepted['plan_id'],Revise(
            submission_id=str(uuid.uuid4()),based_on_version_id=before['plan']['current_version_id'],
            instruction='重新规划能力发展建议'),user)
    else:
        accepted=life.create(Submit(submission_id=str(uuid.uuid4()),request=scenario[0][3]),user)
        run=accepted
        before=views.detail(accepted['plan_id'],user)
    original=scenario[2];sent=[]
    def complete(config,messages,schema):
        sent.append(schema['title'])
        output=json.loads(original(config,messages,schema))
        if schema['title']=='Understanding' and existing:output['action']='regenerate'
        if schema['title']=='AdviceOutput':
            assert output['stages'] and output['stages'][0]['items']
            output['stages'][0]['items'][0]['note']='不表示学完即具备完整集成能力，但学完就具备开发能力。'
        return json.dumps(output,ensure_ascii=False)
    monkeypatch.setattr(model,'completion',complete)
    engine.execute(run['run_id'])
    after=views.detail(accepted['plan_id'],user)
    assert sent==['Understanding','AdviceOutput']
    assert after['runs'][0]['status']=='failed'
    assert after['plan']['current_version_id']==before['plan']['current_version_id']
    assert after['versions']==before['versions']
    assert after['payload']==before['payload']
    assert any('"exception_type": "InvalidOutput"' in r.getMessage()
               and 'Unsupported capability conclusion' in r.getMessage() for r in caplog.records)
