"""Fixed evidence and assumption assertions; synthetic data is not business sign-off."""
import json
import pytest
from fastapi import HTTPException
from backend.app import development_engine as engine, development_lifecycle as life, development_model as model
from backend.app.development_types import Submit
from backend.app.database import get_db
from backend.tests.test_development_lifecycle import prepared
from backend.tests.test_development_engine import scenario,execute


@pytest.mark.parametrize('evidence',['missing','partial'])
def test_insufficient_evidence_stays_needs_assessment(scenario,monkeypatch,evidence):
    original=scenario[2]
    def mock(*args):
        result=json.loads(original(*args))
        if 'diagnoses' in result:
            result['diagnoses'][0].update(evidence_status=evidence,target_satisfaction='not_satisfied')
        return json.dumps(result)
    monkeypatch.setattr(model,'completion',mock)
    _,run,payload=execute(scenario);assert run['status']=='ready'
    diagnosis=payload['diagnoses'][0]
    assert diagnosis['target_satisfaction']=='needs_assessment'
    assert diagnosis['evidence_status']==evidence and diagnosis['judgment_source']=='model_inference'
    if evidence=='missing':assert diagnosis['problem_type']=='evidence_gap' and not payload['stages'][0]['items']


def test_explicit_assumption_survives_request_model_context_and_version(scenario):
    user,_,_,request=scenario[0];request.known_baseline=''
    with pytest.raises(HTTPException) as error:life.create(Submit(submission_id='unknown-baseline',request=request),user)
    assert error.value.status_code==422
    with get_db() as conn:assert conn.execute('SELECT count(*) FROM development_plans').fetchone()[0]==0
    assumed='假设入门，实施前由业务负责人确认'
    request.accepted_assumptions={'known_baseline':assumed}
    _,run,payload=execute(scenario);assert run['status']=='ready'
    assert payload['assumptions']=={'known_baseline':assumed}
    assert payload['overview']['known_baseline']==assumed
    assert json.loads(scenario[1][0][-1]['content'])['accepted_assumptions']['known_baseline']==assumed
    with get_db() as conn:
        stored=json.loads(conn.execute('SELECT payload_json FROM development_requests').fetchone()[0])
        assert stored['accepted_assumptions']['known_baseline']==assumed and stored['raw_demand']==request.raw_demand


def test_model_cannot_force_training_to_solve_non_training_constraint(scenario,monkeypatch):
    original=scenario[2];tag=scenario[0][3].targets[0].capability_tag_id
    def mock(*args):
        result=json.loads(original(*args))
        if 'diagnoses' in result:result['diagnoses'][0].update(problem_type='non_training_constraint',pending_verifications=['地域、人力、商务、资质须业务确认'])
        else:result['stages'][0]['items']=[{'source_type':'course','source_id':'test-course','source_version':1,'capability_tag_id':tag,'reason':'用培训解决地域与人力','estimated_hours':1,'note':''}]
        return json.dumps(result)
    monkeypatch.setattr(model,'completion',mock)
    _,run,payload=execute(scenario);assert run['status']=='failed' and payload is None
