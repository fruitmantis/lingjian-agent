"""Current staged matching fixtures. All inputs and provider responses are synthetic."""
import json
from backend.app import development_model, match_understanding as understanding
from backend.app.database import get_db
from backend.app.routers import match
from backend.tests.conftest import make_user,make_task


def install(monkeypatch, answer=None, facts=None):
    with get_db() as conn:
        conn.execute("UPDATE model_configs SET api_key_source='db',api_key='synthetic-only',base_url='https://synthetic.invalid/v1'")
    calls=[]
    def complete(config,messages,schema):
        title=schema['title'];calls.append(title)
        if title=='MatchUnderstanding':return json.dumps({'in_scope':True,'facts':facts or {}})
        if title=='InitialSelection':
            data=json.loads(messages[-1]['content'])
            return json.dumps({'candidates':[{'partnerId':p['partnerId'],'verificationFocus':'核实需求相关能力和限制'} for p in data['partners'][:12]]})
        assert title=='MatchAnswer',title
        value=answer(messages) if callable(answer) else answer
        return json.dumps({'supplyStatus':'partial','gapAnalysis':'需进一步核实','recommendations':value or []},ensure_ascii=False)
    monkeypatch.setattr(development_model,'completion',complete)
    return calls


def snapshot(requirement,owner=None,task_id=None):
    owner=owner or make_user('matching-unit-owner')
    task_id=task_id or make_task(owner,requirement,recommendations=[],task_status='matching')
    value=understanding.prepare(requirement);value['_task_id']=task_id
    with get_db() as conn:understanding.save(conn,task_id,value)
    return value
