"""Scope is classified in the same understanding request, before task creation."""
import json
from pathlib import Path
import os
import pytest
from fastapi import HTTPException
from backend.app import development_model as model, development_lifecycle as life
from backend.app.database import get_db
from backend.app.development_types import Submit
from backend.app.routers import match
from backend.tests.test_unified_flow import unified, prepared

@pytest.mark.parametrize('mode',['development','match'])
@pytest.mark.parametrize('invalid',[False,True])
def test_integrated_scope_rejection_and_real_parse_errors(unified,monkeypatch,mode,invalid):
    original=unified[2]
    def respond(config,messages,schema):
        if invalid:return '{"in_scope":"not-a-boolean"}'
        if mode=='match':return '{"in_scope":false}'
        output=json.loads(original(config,messages,schema));output['in_scope']=False
        return json.dumps(output)
    monkeypatch.setattr(model,'completion',respond)
    with pytest.raises(HTTPException) as error:
        if mode=='match':match.match_partners(match.MatchRequest(requirement='合成范围外请求'),unified[0][0])
        else:life.create(Submit(submission_id='scope-unified-check',request=unified[0][3]),unified[0][0])
    assert error.value.status_code==(502 if invalid else 422)
    with get_db() as conn:
        assert conn.execute('SELECT count(*) FROM development_plans').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM match_records').fetchone()[0]==0
    log=Path(os.environ['BANFEI_ERROR_LOG_PATH'])
    if invalid:assert log.exists() and ('ValidationError' in log.read_text() or 'InvalidOutput' in log.read_text())
    else:assert not log.exists() or not log.read_text().strip()
