import copy,json
import pytest
from backend.app import development_engine as engine,development_lifecycle as life,development_model as model,enablement
from backend.app.database import get_db
from backend.app.development_types import Submit
from backend.app.model_resolver import ModelConfigurationError
from backend.tests.test_development_lifecycle import prepared,plan
from backend.tests.test_enablement import grant,published

CANARY='INTERNAL_SECRET_PHASE_B_DO_NOT_SHARE'

@pytest.fixture
def scenario(prepared,monkeypatch):
    user,other,admin,request=prepared;tag=request.targets[0].capability_tag_id
    metadata=enablement.ResourceMetadata(resource_type='course',title='数据库课程',summary='合成共享资源',target_capability='交付',audience='工程师',source_platform='合成平台',source_url='https://example.com/course',capability_tag_ids=[tag])
    row=enablement.save('resource','test-course',enablement.ResourceSave(base_revision=0,metadata=metadata),admin['id'])
    published(grant(row,admin),admin)
    with get_db() as conn:
        conn.execute("INSERT INTO cases VALUES ('secret-case','partner-1','内部案例',?,'2026')",(CANARY,))
        conn.execute("UPDATE partners SET ai_profile=? WHERE id='partner-1'",(CANARY,))
        config=dict(conn.execute('SELECT * FROM model_configs LIMIT 1').fetchone())
    monkeypatch.setattr(model,'configuration',lambda:config)
    captures=[]
    def mock(config,messages,schema):
        captures.append(copy.deepcopy(messages));data=json.loads(messages[-1]['content'])
        from backend.tests.support.development_mock import response
        return json.dumps(response(messages))
    monkeypatch.setattr(model,'completion',mock)
    return prepared,captures,mock


def execute(scenario):
    prepared,_,_=scenario;accepted=life.create(Submit(submission_id='engine-submission',request=prepared[3]),prepared[0]);engine.execute(accepted['run_id'])
    with get_db() as conn:
        run=dict(conn.execute('SELECT * FROM development_runs WHERE id=?',(accepted['run_id'],)).fetchone())
        version=conn.execute('SELECT * FROM development_versions WHERE plan_id=?',(accepted['plan_id'],)).fetchone()
    return accepted,run,json.loads(version['payload_json']) if version else None


def test_model_safe_context_and_strong_judgment_boundary(scenario,caplog):
    accepted,run,version=execute(scenario)
    assert run['status']=='ready' and version
    assert version['diagnoses'][0]['target_satisfaction']=='needs_assessment'
    assert version['diagnoses'][0]['evidence_status']=='partial'
    assert version['diagnoses'][0]['judgment_source']=='model_inference'
    assert version['stages'][0]['items'][0]['constraint']['state']=='unknown'
    for boundary in [scenario[1],version,caplog.text,run['safe_error_message']]:assert CANARY not in json.dumps(boundary)
    for messages in scenario[1]:
        text=json.dumps(messages);assert 'source_url' not in text and 'raw_demand' not in text


@pytest.mark.parametrize('malice',['partner','resource','case','version','url','enum','extra','secret','internal_note','unconfirmed_text'])
def test_malicious_outputs_never_create_versions(scenario,monkeypatch,malice,caplog):
    original=scenario[2]
    def corrupted(config,messages,schema):
        result=json.loads(original(config,messages,schema));diagnose='analyze' in messages[0]['content']
        if malice=='partner':result['target_partner_id']='invented'
        elif malice=='enum' and diagnose:result['intent']='illegal'
        elif malice=='extra':result['internal_debug']='forbidden'
        elif malice=='secret':result['extra']=CANARY
        elif malice=='internal_note':result['internal_note']='不得外发的备注'
        elif malice=='unconfirmed_text' and diagnose:result['basis_limitations']=['该伙伴确认不具备技术能力']
        elif not diagnose:
            item=result['stages'][0]['items'][0]
            if malice=='resource':item['source_id']='invented-resource'
            if malice=='case':item.update(source_type='case',source_id='secret-case')
            if malice=='version':item['source_version']=99
            if malice=='url':item['url']='https://example.com/invented'
        return json.dumps(result)
    monkeypatch.setattr(model,'completion',corrupted)
    accepted,run,version=execute(scenario)
    assert run['status']=='failed' and version is None
    assert plan(accepted['plan_id'])['current_version_id'] is None
    assert CANARY not in str(run['safe_error_message'])+caplog.text


def test_missing_profile_does_not_gate_recommendations(scenario):
    _,run,version=execute(scenario)
    assert run['status']=='ready' and version['stages'][0]['items']
    assert version['analysis']['basis_limited']
    assert version['diagnoses'][0]['target_satisfaction']=='needs_assessment'


def test_legacy_human_gap_field_no_longer_controls_advice(scenario):
    scenario[0][3].targets[0].confirmed_gap=True
    _,run,version=execute(scenario)
    assert run['status']=='ready'
    assert version['diagnoses'][0]['judgment_source']=='model_inference'


@pytest.mark.parametrize('change',['unpublished','not_model_allowed','unknown','conflict'])
def test_candidate_permissions_and_constraint_three_states(scenario,change):
    request=scenario[0][3]
    with get_db() as conn:
        if change=='unpublished':conn.execute("UPDATE enablement_resources SET status='unpublished' WHERE id='test-course'")
        elif change=='not_model_allowed':conn.execute("UPDATE enablement_resources SET model_allowed=0 WHERE id='test-course'")
        elif change=='unknown':request.constraints['language']='中文'
        else:request.trainee_role='商务经理'
    _,run,version=execute(scenario);assert run['status']=='ready'
    items=[i for stage in version['stages'] for i in stage['items']]
    if change in ('unknown','conflict'):assert items and items[0]['constraint']['state']=='unknown'
    else:assert items==[] and version['resource_gaps']


def test_revocation_during_model_call_prevents_save(scenario,monkeypatch):
    original=scenario[2]
    def revoke(c,m,s):
        output=original(c,m,s)
        if 'plan' in m[0]['content']:
            with get_db() as conn:conn.execute("UPDATE enablement_resources SET model_allowed=0,authorization_epoch=authorization_epoch+1 WHERE id='test-course'")
        return output
    monkeypatch.setattr(model,'completion',revoke)
    _,run,version=execute(scenario);assert run['status']=='failed' and version is None


def test_explicit_model_selection_and_external_provider_transport(prepared,monkeypatch):
    with get_db() as conn:conn.execute('UPDATE model_configs SET is_default=0');conn.execute('UPDATE model_usage_configs SET model_config_id=NULL')
    with pytest.raises(ModelConfigurationError):model.configuration()
    with get_db() as conn:
        row=conn.execute('SELECT id FROM model_configs LIMIT 1').fetchone();conn.execute("UPDATE model_usage_configs SET model_config_id=? WHERE scene_key='partner_development'",(row[0],))
    chosen=model.configuration();assert chosen['id']==row[0]
    chosen['base_url']='https://api.deepseek.com/v1'
    import httpx
    requests=[]
    async def handle(request):
        requests.append(request)
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"ok":true}'},'finish_reason':'stop'}]})
    original=httpx.AsyncClient
    monkeypatch.setattr(model.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    assert model.completion(chosen,[{'role':'user','content':'transport validation'}],{})=='{"ok":true}'
    assert len(requests)==1 and requests[0].url.host=='api.deepseek.com'
    for invalid in ['file:///tmp/model','https://user:password@model.invalid/v1']:
        with pytest.raises(ModelConfigurationError):model.completion(dict(chosen,base_url=invalid),[],{})
