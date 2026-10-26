"""Retry the model boundary only: the accepted task and derivative writes stay single."""
import json
from uuid import uuid4

import httpx
import pytest

from backend.app import development_model, match_understanding
from backend.app.development_model import completion as real_completion
from backend.app.database import get_db
from backend.app.routers import match
from .conftest import make_user, recommendation
from .test_profile_report import setup, upload
from .test_model_json_content_retry import synthetic_model, HTTPX_ASYNC_CLIENT


@pytest.mark.parametrize('bad_understanding,bad_answer,invalid_evidence', [(False,False,False),(True,False,False),(False,True,False),(True,True,False),(False,False,True)])
def test_matching_retries_one_stage_without_repeating_saved_work(setup,monkeypatch,bad_understanding,bad_answer,invalid_evidence):
    upload(setup,'synthetic-bc-source.txt','具备TaskRetryQuasar能力，交付边界待核实。')
    synthetic_model(monkeypatch)
    monkeypatch.setattr(development_model,'completion',real_completion)
    owner=make_user('bc-stage-owner');request_id=uuid4();calls=[];writes=[]
    for name in ['_generate_demand_profile','_extract_project_opportunity']:
        original=getattr(match,name)
        def count(*args,_name=name,_original=original,**kwargs):
            writes.append(_name)
            return _original(*args,**kwargs)
        monkeypatch.setattr(match,name,count)
    def handle(request):
        payload=json.loads(request.content)
        kind='MatchUnderstanding' if 'MatchUnderstanding' in payload['messages'][0]['content'] else 'MatchAnswer'
        calls.append((kind,request.content))
        with get_db() as conn:
            task=conn.execute('SELECT * FROM match_records WHERE id=?',(str(request_id),)).fetchone()
            assert task and task['requirement']=='需要TaskRetryQuasar能力，必须本地交付'
            assert conn.execute('SELECT COUNT(*) FROM match_records WHERE owner_user_id=?',(owner['id'],)).fetchone()[0]==1
            assert conn.execute('SELECT COUNT(*) FROM demand_profiles WHERE match_record_id=?',(str(request_id),)).fetchone()[0]==0
            assert conn.execute('SELECT COUNT(*) FROM project_opportunities WHERE match_record_id=?',(str(request_id),)).fetchone()[0]==0
        first=sum(k==kind for k,_ in calls)==1
        if first and (bad_understanding if kind=='MatchUnderstanding' else bad_answer):
            raw='{"{"in_scope":true,"facts":{}}'
        elif kind=='MatchUnderstanding':
            raw='```json\n'+json.dumps({'in_scope':True,'facts':{'technicalNeeds':'TaskRetryQuasar','onsiteRequirement':'必须本地交付'},'unused':'projected'})+'\n```'
        else:
            data=json.loads(payload['messages'][-1]['content']);candidate=data['candidates'][0]
            good={**recommendation(), 'partnerId':candidate['partnerId'],'partnerName':candidate['name'],
                  'evidenceCases':[],'evidenceDeliverables':[],
                  'profileEvidence':['P999-S999' if invalid_evidence else candidate['profilePassages'][0]['source']],
                  'recommendationReason':'TaskRetryQuasar能力有资料支持，本地交付仍待核实。'}
            raw='结果：'+json.dumps({'recommendations':[good],'analysisRefs':[],'supplyStatus':'partial','gapAnalysis':'仍需核实本地交付边界'},ensure_ascii=False)
        return httpx.Response(200,request=request,json={'choices':[{'finish_reason':'stop','message':{'content':raw}}]})
    monkeypatch.setattr(development_model.httpx,'AsyncClient',lambda **kw:HTTPX_ASYNC_CLIENT(transport=httpx.MockTransport(handle),**kw))
    accepted=match.create_task(match.TaskCreateRequest(requestId=request_id,requirement='需要TaskRetryQuasar能力，必须本地交付'),owner)
    match.executor.shutdown(wait=True)
    assert [k for k,_ in calls]==['MatchUnderstanding']*(1+bad_understanding)+['MatchAnswer']*(1+bad_answer)
    for kind in ['MatchUnderstanding','MatchAnswer']:
        bodies=[body for key,body in calls if key==kind]
        assert all(body==bodies[0] for body in bodies)
    assert writes==['_generate_demand_profile','_extract_project_opportunity']
    with get_db() as conn:
        task=conn.execute('SELECT * FROM match_records WHERE id=?',(accepted.recordId,)).fetchone()
        saved=match_understanding.load(conn,accepted.recordId)
        assert task['task_status']=='ready'
        assert len(json.loads(task['recommendations_json']))==len(saved['outcome']['recommendations'])==int(not invalid_evidence)
        assert conn.execute('SELECT COUNT(*) FROM demand_profiles WHERE match_record_id=?',(accepted.recordId,)).fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM project_opportunities WHERE match_record_id=?',(accepted.recordId,)).fetchone()[0]==1
    # Submission replay is still idempotent and does not repeat any model/write.
    again=match.create_task(match.TaskCreateRequest(requestId=request_id,requirement='需要TaskRetryQuasar能力，必须本地交付'),owner)
    assert again.recordId==accepted.recordId and len(calls)==2+bad_understanding+bad_answer


def test_unrecoverable_understanding_keeps_the_failed_original_task(setup,monkeypatch):
    from .test_model_json_content_retry import transport
    synthetic_model(monkeypatch);monkeypatch.setattr(development_model,'completion',real_completion)
    seen=transport(monkeypatch,['{"{"in_scope":true,"facts":{}}'])
    owner=make_user('bc-failed-owner');request_id=uuid4()
    accepted=match.create_task(match.TaskCreateRequest(requestId=request_id,requirement='需要TaskRetryQuasar能力'),owner)
    match.executor.shutdown(wait=True)
    assert len(seen)==2 and seen[0]==seen[1]
    with get_db() as conn:
        task=conn.execute('SELECT * FROM match_records WHERE id=?',(accepted.recordId,)).fetchone()
        assert task['task_status']=='failed' and task['requirement']=='需要TaskRetryQuasar能力'
        assert task['last_error_stage']=='understanding'
        assert conn.execute('SELECT COUNT(*) FROM demand_profiles WHERE match_record_id=?',(accepted.recordId,)).fetchone()[0]==0
        assert conn.execute('SELECT COUNT(*) FROM project_opportunities WHERE match_record_id=?',(accepted.recordId,)).fetchone()[0]==0
