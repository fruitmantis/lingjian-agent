"""V1.2 direction/profile/intent contracts, using only synthetic local model responses."""
import copy,json,uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from backend.app import development_engine as engine,development_lifecycle as life,development_views as views,development_model as model,enablement
from backend.app.database import get_db
from backend.app.development_types import DevelopmentRequest,Submit,Conversation
from backend.tests.test_development_lifecycle import prepared,plan
from backend.tests.test_development_engine import scenario,CANARY
from backend.tests.test_enablement import grant,published
from backend.tests.conftest import make_partner,make_user,auth_headers


def run(scenario,direction,partner='partner-1',user=None):
    user=user or scenario[0][0]
    accepted=life.create(Submit(submission_id=str(uuid.uuid4()),request=DevelopmentRequest(target_partner_id=partner,development_direction=direction,model_input_allowed=True)),user)
    engine.execute(accepted['run_id']);detail=views.detail(accepted['plan_id'],user)
    assert detail['runs'][0]['status']=='ready'
    return detail


def add(admin,kind,title,tag,difficulty='advanced',id=None):
    metadata=enablement.ResourceMetadata(resource_type=kind,title=title,summary=title+'的合成测试用途',target_capability=title,product_direction=title,audience='交付工程师',difficulty=difficulty,cost='paid',account_requirement='需测试账号',environment_requirement='需测试环境',source_platform='synthetic',source_url='https://example.com/synthetic',capability_tag_ids=[tag])
    row=enablement.save('resource',id or str(uuid.uuid4()),enablement.ResourceSave(base_revision=0,metadata=metadata),admin['id']);return published(grant(row,admin),admin)


def items(detail):return [i for s in detail['payload']['stages'] for i in s['items']]


def test_directions_profiles_unmapped_focus_and_latest_profile(scenario):
    admin=scenario[0][2];tag=scenario[0][3].targets[0].capability_tag_id
    add(admin,'course','Agent RAG 集成',tag) # intentionally mapped to a different formal tag
    add(admin,'lab','Agent 系统集成进阶实验',tag)
    make_partner('profile-b')
    with get_db() as conn:
        conn.execute("UPDATE partners SET ai_profile='具备数据库交付与云基础经验',industries='制造' WHERE id='partner-1'")
        conn.execute("UPDATE partners SET ai_profile=NULL,capabilities='',industries='零售' WHERE id='profile-b'")
        before=conn.execute('SELECT count(*) FROM capability_tags').fetchone()[0]
    db=run(scenario,'数据库迁移');agent=run(scenario,'Agent 应用交付');other=run(scenario,'Agent 应用交付','profile-b')
    focuses=lambda d:{f['name'] for f in d['payload']['analysis']['priorities']}
    assert focuses(db)!=focuses(agent)
    assert 'Agent 系统集成与 POC 调优' in focuses(agent)
    assert '应用集成与云服务基础' not in focuses(agent) and '应用集成与云服务基础' in focuses(other)
    assert any('Agent' in i['title'] for i in items(agent)) # metadata search, not tag equality
    assert other['payload']['analysis']['basis_limited']
    assert items(agent)[0]['conditions']['account_requirement']=='需测试账号'
    with get_db() as conn:
        assert conn.execute('SELECT count(*) FROM capability_tags').fetchone()[0]==before
        conn.execute("UPDATE partners SET ai_profile='已完成数据库与云基础项目实践' WHERE id='profile-b'")
    refreshed=run(scenario,'Agent 应用交付','profile-b')
    assert '应用集成与云服务基础' not in focuses(refreshed)
    # Removing a formal label does not prevent natural-language focuses.
    with get_db() as conn:conn.execute("UPDATE capability_tags SET enabled=0 WHERE name='盘古大模型'")
    unmatched=run(scenario,'Agent 应用交付')
    assert any(f['capability_tag_id'] is None for f in unmatched['payload']['analysis']['priorities'])


def test_exploration_not_driven_by_resource_inventory(scenario):
    a=run(scenario,'这个伙伴下一步适合往什么方向发展？')
    tag=scenario[0][3].targets[0].capability_tag_id
    for n in range(4):add(scenario[0][2],'course',f'数据库热门课程{n}',tag)
    b=run(scenario,'这个伙伴下一步适合往什么方向发展？')
    assert a['payload']['analysis']['priorities']==b['payload']['analysis']['priorities']
    first=json.loads(scenario[1][0][-1]['content']);assert 'candidates' not in first


def test_short_labs_unknown_cost_gap_and_no_capability_update(scenario,client):
    tag=scenario[0][3].targets[0].capability_tag_id
    add(scenario[0][2],'lab','数据库进阶实验',tag)
    d=run(scenario,'只给几个数据库进阶实验，不要基础课')
    assert d['payload']['analysis']['intent']=='resources'
    assert {i['source_type'] for i in items(d)}=={'lab'}
    assert not d['payload']['next_steps']
    assert items(d)[0]['conditions']['cost']=='paid'
    assert items(d)[0]['constraint']['state']=='unknown'
    with get_db() as conn:before=tuple(conn.execute("SELECT capabilities,ai_profile FROM partners WHERE id='partner-1'").fetchone())
    i=items(d)[0]
    res=client.post(f"/enablement/resources/lab/{i['source_id']}/redirect",headers=auth_headers(scenario[0][0]),json={'source_version':i['source_version']})
    assert res.status_code==200
    with get_db() as conn:assert tuple(conn.execute("SELECT capabilities,ai_profile FROM partners WHERE id='partner-1'").fetchone())==before
    gap=run(scenario,'C_GAP Agent 应用交付')
    assert not items(gap) and gap['payload']['resource_gaps']


@pytest.mark.parametrize('message',['为什么推荐这个方向？','这两个实验有什么区别？'])
def test_draft_explanations_do_not_create_run_or_version_and_are_durable(scenario,message):
    d=run(scenario,'数据库迁移');pid=d['plan']['id'];v1=d['plan']['current_version_id'];user=scenario[0][0]
    body=Conversation(submission_id=str(uuid.uuid4()),based_on_version_id=v1,message=message)
    a=views.converse(pid,body,user);assert a['kind']=='explain' and a['answer']
    assert views.converse(pid,body,user)==a
    after=views.detail(pid,user);assert len(after['versions'])==len(after['runs'])==1
    assert after['conversation'][-1]['answer']==a['answer']
    assert after['plan']['confirmed_version_id'] is None
    with pytest.raises(HTTPException):views.converse(pid,body.model_copy(update={'message':'changed'}),user)
    with pytest.raises(HTTPException) as exc:views.converse(pid,body,scenario[0][1])
    assert exc.value.status_code==404


def test_conversation_modify_creates_run_draft_and_preserves_confirmed(scenario):
    tag=scenario[0][3].targets[0].capability_tag_id;add(scenario[0][2],'lab','数据库进阶实验',tag)
    d=run(scenario,'数据库迁移');pid=d['plan']['id'];v1=d['plan']['current_version_id'];user=scenario[0][0]
    views.confirm(pid,v1,user)
    body=Conversation(submission_id=str(uuid.uuid4()),based_on_version_id=v1,message='不要基础课，多给实验')
    result=views.converse(pid,body,user);assert result['kind']=='revise'
    assert views.converse(pid,body,user)['run_id']==result['run_id']
    engine.execute(result['run_id']);d=views.detail(pid,user)
    assert len(d['versions'])==2 and d['plan']['confirmed_version_id']==v1
    assert {i['source_type'] for i in items(d)}=={'lab'}
    with pytest.raises(HTTPException):views.converse(pid,body.model_copy(update={'submission_id':str(uuid.uuid4())}),user)


def test_three_distinct_owners_and_partners_execute_independently(scenario):
    users=[scenario[0][0],scenario[0][1],make_user('v12-third')];partners=['partner-1','v12-b','v12-c']
    for p in partners[1:]:make_partner(p)
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(lambda pair:run(scenario,'数据库迁移',pair[1],pair[0]),zip(users,partners)))
    assert len({d['plan']['current_version_id'] for d in results})==3
    for d,u,p in zip(results,users,partners):
        assert d['plan']['owner_user_id']==u['id'] and d['payload']['target_partner_id']==p
        assert len(d['versions'])==1


def test_profile_consent_is_not_system_visibility(scenario):
    user=scenario[0][0]
    accepted=life.create(Submit(submission_id='no-profile-consent',request=DevelopmentRequest(target_partner_id='partner-1',development_direction='数据库迁移')),user)
    engine.execute(accepted['run_id']);d=views.detail(accepted['plan_id'],user)
    assert d['runs'][0]['status']=='ready'
    sent=json.loads(scenario[1][0][-1]['content'])['profile']
    assert sent=={'basis_limited':True,'notice':'未获准使用画像摘要，仅依据发展方向'}
    assert CANARY not in json.dumps(scenario[1])


def test_conversation_output_rejected_for_fake_reference_or_secret(scenario,monkeypatch):
    d=run(scenario,'数据库迁移');pid=d['plan']['id'];user=scenario[0][0]
    original=scenario[2]
    def malicious(c,m,s):
        output=json.loads(original(c,m,s))
        if 'converse' in m[0]['content']:output['answer']=CANARY
        return json.dumps(output)
    monkeypatch.setattr(model,'completion',malicious)
    with pytest.raises(HTTPException):views.converse(pid,Conversation(submission_id=str(uuid.uuid4()),based_on_version_id=d['plan']['current_version_id'],message='为什么'),user)
    assert not views.detail(pid,user)['conversation']


def test_simple_resource_search_does_not_call_model(scenario,monkeypatch):
    add(scenario[0][2],'lab','数据库进阶实验',scenario[0][3].targets[0].capability_tag_id)
    def forbidden(*args):raise AssertionError('Simple search must not invoke a model')
    monkeypatch.setattr(model,'configuration',forbidden);monkeypatch.setattr(model,'completion',forbidden)
    d=run(scenario,'只给几个数据库进阶实验，不要基础课')
    assert items(d) and not scenario[1]


def test_explanation_cannot_be_misrouted_to_revision(scenario,monkeypatch):
    d=run(scenario,'数据库迁移');user=scenario[0][0]
    monkeypatch.setattr(model,'completion',lambda *args:json.dumps({'target_partner_id':'partner-1','kind':'revise','answer':'','references':[]}))
    with pytest.raises(HTTPException):views.converse(d['plan']['id'],Conversation(submission_id=str(uuid.uuid4()),based_on_version_id=d['plan']['current_version_id'],message='为什么推荐这个方向？'),user)
    after=views.detail(d['plan']['id'],user)
    assert len(after['versions'])==len(after['runs'])==1
