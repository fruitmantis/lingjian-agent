"""Advisor interaction contracts; all resources and model responses are synthetic."""
from backend.tests.support.legacy_development import legacy_confirmed
import json,uuid,re
import pytest
from fastapi import HTTPException
from backend.app import development_engine as engine,development_views as views,development_model as model
from backend.app.development_types import Conversation
from backend.tests.support.development_execution import finish,answer as completed_answer
from backend.tests.test_development_engine import scenario
from backend.tests.test_development_lifecycle import prepared,plan
from backend.tests.test_v12_agent import run,items,add

@pytest.mark.parametrize('message',['为什么推荐 RAG？','这个课程为什么适合？','这两个实验有什么区别？','哪个实验更难？','有没有更进阶一点的实验？'])
def test_discussion_keeps_current_advice_without_confirmation(scenario,message):
    detail=run(scenario,'Agent 应用交付');pid=detail['plan']['id'];version=detail['plan']['current_version_id']
    result=views.converse(pid,Conversation(submission_id=str(uuid.uuid4()),based_on_version_id=version,message=message),scenario[0][0])
    answer=completed_answer(result,scenario[0][0])
    assert answer.startswith('### 结论\n\n')
    assert 1 <= len(re.findall(r'^#### .+$',answer,re.M)) <= 3
    system=scenario[1][-1][0]['content']
    for requirement in ('解释、比较', 'action=answer', '不创建版本'):
        assert requirement in system

    after=views.detail(pid,scenario[0][0])
    assert after['plan']['current_version_id']==version and plan(pid)['confirmed_version_id'] is None
    assert len(after['runs'])==2 and len(after['versions'])==1


def test_explore_is_small_direction_response_not_resource_package(scenario):
    before=len(scenario[1]);detail=run(scenario,'这个伙伴下一步适合往哪里发展？')
    payload=detail['payload'];assert payload['analysis']['intent']=='explore'
    assert 1<=len(payload['analysis']['priorities'])<=3
    assert payload['analysis']['partner_assessment']
    assert payload['stages']==payload['next_steps']==payload['resource_gaps']==[]
    assert len(scenario[1])-before==1 # only direction analysis, inventory never decides priorities


def test_natural_adjustment_reorders_focus_and_failed_retry_keeps_current(scenario):
    d=run(scenario,'Agent 应用交付');user=scenario[0][0];pid=d['plan']['id'];v1=d['plan']['current_version_id']
    legacy_confirmed(pid,v1,user)
    result=views.converse(pid,Conversation(submission_id=str(uuid.uuid4()),based_on_version_id=v1,message='RAG 暂时放后，先做系统集成'),user)
    assert result['kind']=='revise';engine.execute(result['run_id']);updated=views.detail(pid,user)
    assert updated['payload']['analysis']['priorities'][0]['name']=='Agent 系统集成与 POC 调优'
    assert plan(pid)['confirmed_version_id']==v1
    v2=updated['plan']['current_version_id'];assert v2!=v1
    fail=views.converse(pid,Conversation(submission_id=str(uuid.uuid4()),based_on_version_id=v2,message='模拟调整失败'),user)
    engine.execute(fail['run_id']);after=views.detail(pid,user)
    assert after['runs'][0]['status']=='failed' and len(after['versions'])==2
    assert after['plan']['current_version_id']==v2 and plan(pid)['confirmed_version_id']==v1


def test_readonly_resource_duration_is_metadata_not_generated_estimate(scenario):
    tag=scenario[0][3].targets[0].capability_tag_id
    add(scenario[0][2],'lab','Agent 系统集成实验',tag)
    d=run(scenario,'Agent 应用交付');assert items(d)
    for item in items(d):
        assert 'duration_minutes' in item['conditions']
    assert all(i['focus'] in {f['name'] for f in d['payload']['analysis']['priorities']} for i in items(d))


def test_difficulty_discussion_cannot_be_misclassified_as_revision(scenario,monkeypatch):
    d=run(scenario,'Agent 应用交付');v=d['plan']['current_version_id']
    calls=[];original=scenario[2]
    def invalid(c,m,s):
        calls.append(s['title']);output=json.loads(original(c,m,s));output['action']='regenerate'
        return json.dumps(output)
    monkeypatch.setattr(model,'completion',invalid)
    accepted=views.converse(d['plan']['id'],Conversation(submission_id=str(uuid.uuid4()),based_on_version_id=v,message='哪个实验更难？'),scenario[0][0])
    after,failed=finish(accepted,scenario[0][0])
    assert calls==['Understanding'] and failed['status']=='failed'
    assert after['plan']['current_version_id']==v and len(after['versions'])==1



@pytest.mark.parametrize('answer', [
    '### 结论\n\n优先验证系统集成。\n\n#### 接口约束\n\n- 核实输入输出。\n- 准备异常处理。',
    '### 结论\n\n两类实验各有侧重。\n\n#### 数据接入\n\n先检查数据条件。\n\n#### 评估方式\n\n1. 明确评估样本。\n2. 验证实际效果。\n\n#### 选择条件\n\n按目标选择。',
])
def test_formatted_discussion_persists_and_replays_without_versions(scenario,monkeypatch,answer):
    detail=run(scenario,'Agent 应用交付');user=scenario[0][0];pid=detail['plan']['id'];version=detail['plan']['current_version_id']
    def complete(c,m,s):
        output=json.loads(scenario[2](c,m,s));output.update(action='answer',answer=answer,references=[])
        return json.dumps(output)
    monkeypatch.setattr(model,'completion',complete)
    body=Conversation(submission_id=str(uuid.uuid4()),based_on_version_id=version,message='请解释当前建议')
    accepted=views.converse(pid,body,user)
    assert completed_answer(accepted,user)==answer
    monkeypatch.setattr(model,'completion',lambda *args:pytest.fail('Replayed explanation must not call the model'))
    replay=views.converse(pid,body,user)
    assert replay['replayed'] and replay['run_id']==accepted['run_id']
    assert completed_answer(replay,user)==answer
    after=views.detail(pid,user)
    assert after['conversation'][0]['answer']==answer and len(after['conversation'])==1
    assert after['plan']['current_version_id']==version and len(after['versions'])==1 and len(after['runs'])==2


def test_empty_answer_records_actual_reason_and_preserves_advice(scenario,monkeypatch,client):
    from backend.app.error_diagnostics import recent_errors
    from backend.tests.conftest import auth_headers
    detail=run(scenario,'Agent 应用交付');pid=detail['plan']['id'];version=detail['plan']['current_version_id']
    user=scenario[0][0]
    calls=[]
    def empty(c,m,s):
        calls.append(s['title']);output=json.loads(scenario[2](c,m,s));output.update(action='answer',answer='  ')
        return json.dumps(output)
    monkeypatch.setattr(model,'completion',empty)
    body={'submission_id':'empty-answer-request','based_on_version_id':version,'message':'请解释当前建议'}
    response=client.post(f'/development/plans/{pid}/conversation',headers=auth_headers(user),json=body)
    assert response.status_code==200
    after,failed=finish(response.json(),user,execute=False)
    assert failed['status']=='failed' and calls==['Understanding']
    error=next(e for e in recent_errors() if e['message']=='Answer is empty')
    assert error['task_id']==pid and error['request_id']==body['submission_id']
    assert 'prepare' in error['traceback']
    after=views.detail(pid,user)
    assert after['plan']['current_version_id']==version and not after['conversation']
    assert len(after['versions'])==1 and len(after['runs'])==2


def test_question_with_explicit_modification_can_still_create_version(scenario,monkeypatch):
    detail=run(scenario,'数据库迁移');user=scenario[0][0];pid=detail['plan']['id'];base=detail['plan']['current_version_id']
    original=scenario[2]
    def modify(c,m,s):
        output=json.loads(original(c,m,s))
        if s['title']=='Understanding':output['action']='regenerate'
        return json.dumps(output)
    monkeypatch.setattr(model,'completion',modify)
    accepted=views.converse(pid,Conversation(submission_id=str(uuid.uuid4()),based_on_version_id=base,message='为什么推荐课程？请修改建议，优先选择实验'),user)
    after,finished=finish(accepted,user)
    assert finished['status']=='ready' and len(after['versions'])==2
    assert after['plan']['current_version_id']!=base
