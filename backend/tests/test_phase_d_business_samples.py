"""V1.2 keeps old fields optional, never a preflight or recommendation gate."""
import json
from backend.tests.test_development_lifecycle import prepared
from backend.tests.test_development_engine import scenario,execute


def test_legacy_fields_do_not_enter_model_context(scenario):
    req=scenario[0][3]
    req.trainee_role='';req.trainee_count=None;req.known_baseline='';req.duration_weeks=None
    req.hours_per_week=None;req.constraints={};req.targets=[]
    _,run,payload=execute(scenario)
    assert run['status']=='ready'
    for messages in scenario[1]:
        body=json.loads(messages[-1]['content'])
        assert not {'trainee_role','trainee_count','known_baseline','duration_weeks','constraints','targets'} & body['request'].keys()
    assert payload['diagnoses'][0]['target_satisfaction']=='needs_assessment'
