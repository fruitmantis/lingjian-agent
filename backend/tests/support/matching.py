"""Current staged matching fixtures. All inputs and provider responses are synthetic."""
import json
from backend.app import development_model, match_understanding as understanding
from backend.app.database import get_db
from backend.app.routers import match
from backend.tests.conftest import make_user,make_task


def install(monkeypatch, answer=None, facts=None):
    with get_db() as conn:
        conn.execute("UPDATE model_providers SET api_key_source='db',api_key='synthetic-only',base_url='https://synthetic.invalid/v1'")
    calls=[]
    def complete(config,messages,schema):
        title=schema['title'];calls.append(title)
        if title=='MatchUnderstanding':return json.dumps({'in_scope':True,'facts':facts or {}})
        if title=='InitialSelection':
            data=json.loads(messages[-1]['content'])
            return json.dumps({'candidates':[{'partnerId':p['partnerId'],'verificationFocus':'核实需求相关能力和限制'} for p in data['partners'][:12]]})
        assert title=='MatchAnswer',title
        value=answer(messages) if callable(answer) else answer
        return json.dumps({'supplyStatus':'partial','gapAnalysis':'需进一步核实','analysisRefs':[],'recommendations':[({**item,'profileEvidence':[ref.get('source') if isinstance(ref,dict) else ref for ref in item.get('profileEvidence',[])]} if isinstance(item,dict) else item) for item in (value or [])]},ensure_ascii=False)
    monkeypatch.setattr(development_model,'completion',complete)
    return calls


def snapshot(requirement,owner=None,task_id=None):
    owner=owner or make_user('matching-unit-owner')
    task_id=task_id or make_task(owner,requirement,recommendations=[],task_status='matching')
    value=understanding.prepare(requirement);value['_task_id']=task_id
    with get_db() as conn:understanding.save(conn,task_id,value)
    return value



def current_protocol(provider):
    """Synthetic fixture adapter: same declared IDs, current mandatory wire shape."""
    def complete(config,messages,schema):
        raw=provider(config,messages,schema)
        if schema.get('title')!='MatchAnswer':return raw
        try:value=json.loads(raw)
        except (ValueError,TypeError):return raw
        if not isinstance(value,dict) or not isinstance(value.get('recommendations'),list):return raw
        value.setdefault('analysisRefs',[])
        for card in value['recommendations']:
            if not isinstance(card,dict):continue
            refs=card.get('profileEvidence',[])
            if isinstance(refs,list):card['profileEvidence']=[ref.get('source') if isinstance(ref,dict) else ref for ref in refs]
            card.setdefault('evidenceCases',[]);card.setdefault('evidenceDeliverables',[])
        return json.dumps(value,ensure_ascii=False)
    return complete


def owned_case_file(conn,partner_id,tmp_path):
    """Persist synthetic references in the current per-test isolated schema."""
    from uuid import uuid4
    from datetime import datetime,timezone
    case_id='case-'+uuid4().hex;file_id='file-'+uuid4().hex
    stamp=datetime.now(timezone.utc).isoformat()
    path=tmp_path/'synthetic-delivery.txt';path.write_text('合成交付说明')
    conn.execute('INSERT INTO cases(id,partner_id,title,description,category_id,visible,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                 (case_id,partner_id,'合成案例','合成项目已交付','delivery-1',1,stamp,stamp))
    conn.execute('INSERT INTO deliverables(id,case_id,filename,file_path,file_type,created_at,extracted_text,processing_status,processed_at) VALUES (?,?,?,?,?,?,?,?,?)',
                 (file_id,case_id,'synthetic-delivery.txt',str(path),'txt',stamp,'合成交付说明','ready',stamp))
    case=dict(conn.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone())
    file=dict(conn.execute('SELECT d.*,c.title AS case_title FROM deliverables d JOIN cases c ON c.id=d.case_id WHERE d.id=?',(file_id,)).fetchone())
    return case,file
