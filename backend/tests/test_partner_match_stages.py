"""PG recall and a single validated public matching result."""
from backend.app.routers import match
from backend.app.database import get_db
from .conftest import make_partner
from .test_profile_report import setup,upload
from .conftest import recommendation
from backend.business import matching

def test_invalid_partner_raw_answer_and_supply_are_not_published(setup):
    pid=setup[3];row=None
    with get_db() as conn:row=dict(conn.execute('SELECT * FROM partners WHERE id=?',(pid,)).fetchone())
    raw={**recommendation(),'partnerId':pid,'partnerName':row['name']}
    invalid={**raw,'partnerId':'invented-id','partnerName':'InventedPartner'}
    rejections=[]
    recs=match._validated_recommendations([raw,invalid],[row],{pid:[]},{pid:[]},rejections)
    output={'answer':'推荐InventedPartner，供给完全充分。','gapAnalysis':'InventedPartner足够。','supplyStatus':'sufficient'}
    result=match._validated_outcome(recs,output,bool(rejections),[(row,{},[],[])])
    assert len(recs)==1 and result['recommendations']==[r.model_dump() for r in recs]
    assert row['name'] in result['answer'] and 'InventedPartner' not in str(result)
    assert result['supplyStatus']=='partial'

def test_hidden_sources_are_removed_from_accepted_card_and_answer(setup):
    upload(setup,'PrivateSourceLabel.txt','具备测试能力。')
    pid=setup[3]
    with get_db() as conn:row=dict(conn.execute('SELECT * FROM partners WHERE id=?',(pid,)).fetchone())
    raw={**recommendation(),'partnerId':pid,'partnerName':row['name'],'recommendationReason':'依据PrivateSourceLabel.txt https://private.invalid/file 具备能力','riskNotes':'PrivateSourceLabel.txt待核实'}
    recs=match._validated_recommendations([raw],[row],{pid:[]},{pid:[]})
    result=match._validated_outcome(recs,{'supplyStatus':'partial'},False,[(row,{},[],[])])
    assert 'PrivateSourceLabel.txt' not in str(result) and 'https://private.invalid' not in str(result)
    assert result['recommendations']==[r.model_dump() for r in recs]

def test_detail_prompt_preserves_explicit_hard_requirements():
    prompt=matching.detail_messages('{"facts":{"qualificationRequirements":"必须持证","onsiteRequirement":"必须驻场"}}')
    assert '不得放宽' in prompt[0]['content'] and '必须持证' in prompt[1]['content']

def test_task_persisted_before_understanding_and_no_all_partner_model_call(setup,monkeypatch):
    import json
    from uuid import uuid4
    from backend.app import development_model,match_understanding,agent_settings
    from .conftest import make_user
    upload(setup,'recall.txt','具备TaskFlowQuasar能力。')
    for i in range(15): make_partner('flow-distractor-'+str(i),'无关伙伴'+str(i))
    calls=[];owner=make_user('source-match-owner')
    def complete(config,messages,schema):
        calls.append(schema['title'])
        with get_db() as conn:
            task=dict(conn.execute('SELECT * FROM match_records WHERE owner_user_id=?',(owner['id'],)).fetchone())
            assert task['requirement']=='需要TaskFlowQuasar能力，必须本地交付'
        if schema['title']=='MatchUnderstanding':
            return json.dumps({'in_scope':True,'facts':{'technicalNeeds':'TaskFlowQuasar','onsiteRequirement':'必须本地交付'},'tag_suggestions':[]})
        assert schema['title']=='MatchAnswer'
        data=json.loads(messages[-1]['content'])
        assert len(data['candidates'])<16 and data['facts']['onsiteRequirement']=='必须本地交付'
        candidate=data['candidates'][0]
        assert candidate['partnerId']==setup[3]
        good={**recommendation(),'partnerId':setup[3],'partnerName':'验证伙伴','evidenceCases':[],'evidenceDeliverables':[],
              'recommendationReason':'TaskFlowQuasar能力有资料支持，本地交付仍待核实。'}
        bad={**good,'partnerId':'invalid-id','partnerName':'InvalidOutsidePartner'}
        return json.dumps({'answer':'InvalidOutsidePartner完全符合','gapAnalysis':'InvalidOutsidePartner覆盖','supplyStatus':'sufficient','recommendations':[good,bad]})
    monkeypatch.setenv('LLM_API_KEY','synthetic-key')
    monkeypatch.setattr(development_model,'completion',complete)
    accepted=match.create_task(match.TaskCreateRequest(requestId=uuid4(),requirement='需要TaskFlowQuasar能力，必须本地交付'),owner)
    match.executor.shutdown(wait=True)
    with get_db() as conn:
        task=dict(conn.execute('SELECT * FROM match_records WHERE id=?',(accepted.recordId,)).fetchone())
        saved=match_understanding.load(conn,accepted.recordId)
    assert calls==['MatchUnderstanding','MatchAnswer']
    assert task['task_status'] in ('ready','partial')
    assert saved['initial_selection']['method']=='postgres_keywords'
    assert 'InvalidOutsidePartner' not in str(saved['outcome'])
    assert json.loads(task['recommendations_json'])==saved['outcome']['recommendations']
    assert saved['outcome']['supplyStatus']=='partial'


def test_ordinary_history_masks_current_hidden_source_identity_without_rewriting_history(setup):
    from .conftest import make_user,make_task,auth_headers
    from backend.app import match_understanding
    c,admin,_,pid,_=setup
    upload(setup,'HiddenLegacySource.txt','具有测试业务事实。')
    owner=make_user('legacy-hidden-owner')
    rec={**recommendation(),'partnerId':pid,'partnerName':'验证伙伴','recommendationReason':'HiddenLegacySource.txt显示测试业务事实',
         'evidenceCases':'HiddenLegacySource.txt','evidenceDeliverables':'https://hidden.invalid/item'}
    task=make_task(owner,'原始需求应保留',recommendations=[rec])
    with get_db() as conn:
        match_understanding.save(conn,task,{'visible_answer':'依据HiddenLegacySource.txt https://hidden.invalid/item支持测试业务事实'})
    public=c.get('/agent/tasks/'+task,headers=auth_headers(owner))
    assert public.status_code==200
    assert 'HiddenLegacySource.txt' not in public.text and 'https://hidden.invalid' not in public.text
    assert '测试业务事实' in public.text and public.json()['requirement']=='原始需求应保留'
    private=c.get('/agent/tasks/'+task,headers=admin)
    assert 'HiddenLegacySource.txt' in private.text
    with get_db() as conn:
        assert 'HiddenLegacySource.txt' in conn.execute('SELECT recommendations_json FROM match_records WHERE id=?',(task,)).fetchone()[0]
