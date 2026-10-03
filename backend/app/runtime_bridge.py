"""VM owns authorization, durable run binding, and final persistence; Runtime owns AI calls."""
from contextlib import contextmanager
from contextvars import ContextVar
import json,os,time,uuid
from types import SimpleNamespace
from .runtime_endpoint import validate_endpoint, operation_url
import httpx
from backend.agent_runtime.contracts import PROTOCOL,StageRequest,ModelOptions,digest,source_manifest,model_route
from backend.agent_runtime.workflows import validate_output,validate_budget
from backend.agent_runtime.diagnostics import sanitize_diagnostic, LEGACY_ERRORS, StageFailure
from .database import get_db
from .model_resolver import configuration_stamp,pinned_configuration,model_config_from_record
from .model_timeout_settings import get_settings
from .auth import ensure_account_active
from . import error_diagnostics

# Read wire limits from the deployed protocol definitions; do not duplicate caps.
RUNTIME_INPUT_BUDGET = StageRequest.model_json_schema()['properties']['input_token_budget']['maximum']
RUNTIME_OUTPUT_BUDGET = ModelOptions.model_json_schema()['properties']['max_tokens']['maximum']
_RUN=ContextVar('banfei_runtime_run',default=None)


def stage_output_limit(workflow, stage, data, proposed_output):
    """Reserve output against exact Runtime messages and the unchanged wire limits.

    Count the complete UTF-8 message envelope, including schema and material
    notice, before dispatch. This helper performs no authorization or AI call.
    """
    request = SimpleNamespace(workflow=workflow, stage=stage, data=data,
        material_notice=StageRequest.model_fields['material_notice'].default,
        input_token_budget=RUNTIME_INPUT_BUDGET, model=SimpleNamespace(max_tokens=1))
    messages = validate_budget(request, ceiling=RUNTIME_INPUT_BUDGET)
    input_bytes = len(json.dumps(messages, ensure_ascii=False).encode('utf-8'))
    output = min(proposed_output, RUNTIME_OUTPUT_BUDGET, RUNTIME_INPUT_BUDGET - input_bytes)
    if output < 1:
        raise StageFailure('input_budget_exceeded')
    return output


def initial_selection_output_limit(data, proposed_output):
    """Keep the approved pre-compression initial-selection boundary."""
    try:
        return stage_output_limit('match', 'initial_selection', data, proposed_output)
    except ValueError as error:
        from .task_failures import MatchInputBudgetError
        raise MatchInputBudgetError('初筛完整 Runtime 消息超过输入预算，任务已保留') from error

@contextmanager
def run_scope(workflow,task_id,run_id):
    token=_RUN.set((workflow,str(task_id),str(run_id)))
    try:yield
    finally:_RUN.reset(token)

def mode(workflow):
    selected=os.environ.get('BANFEI_'+workflow.upper()+'_EXECUTOR','local')
    if selected not in ('local','runtime'):raise ValueError('Invalid AI executor mode')
    return selected

def authorize(conn,context):
    workflow,task_id,run_id=context
    if workflow=='match':
        from .routers.match import _require_match_run
        _require_match_run(conn,task_id,run_id,('matching',))
        row=conn.execute('SELECT owner_user_id,archived_at FROM match_records WHERE id=?',(task_id,)).fetchone()
        if not row or row['archived_at']:raise ValueError('Match run no longer active')
    else:
        row=conn.execute('SELECT * FROM development_runs WHERE id=? AND plan_id=?',(run_id,task_id)).fetchone()
        plan=conn.execute('SELECT * FROM development_plans WHERE id=?',(task_id,)).fetchone()
        if not row or row['status']!='running' or not plan or plan['status']!='active' or plan['active_run_id']!=run_id or plan['current_version_id']!=row['based_on_version_id']:raise ValueError('Development run no longer current')
    ensure_account_active(conn,row['owner_user_id'])

def source_stamp(conn):
    # Local invalidation only: neither hidden documents nor credentials leave VM.
    queries=[
      'SELECT id,status,name,intro,capabilities,industries,service_areas,ai_profile,materials_revision,profile_materials_revision,updated_at FROM partners ORDER BY id',
      'SELECT id,partner_id,title,description,visible,updated_at FROM cases ORDER BY id',
      'SELECT id,case_id,filename,processed_at FROM deliverables ORDER BY id',
      'SELECT * FROM enablement_resources ORDER BY id',
      'SELECT * FROM enablement_resource_versions ORDER BY source_id,version',
      'SELECT id,name,enabled FROM capability_tags ORDER BY id',
    ]
    return digest([[dict(r) for r in conn.execute(q)] for q in queries])

def load(conn,key):
    row=conn.execute('SELECT value FROM app_metadata WHERE key=?',(key,)).fetchone()
    return json.loads(row[0]) if row else None

def save(conn,key,value):
    conn.execute('INSERT INTO app_metadata(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,json.dumps(value,separators=(',',':'))))

def client_for():return httpx.Client(timeout=15,follow_redirects=False,trust_env=False)

def endpoint():
    return validate_endpoint(os.environ.get('BANFEI_RUNTIME_URL', ''),
        local_test=os.environ.get('BANFEI_RUNTIME_LOCAL_TEST') == '1',
        external_approved=os.environ.get('BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED') == '1')


def execute_stage(workflow,stage,data,config,local_call):
    if mode(workflow)=='local':return local_call()
    context=_RUN.get()
    if not context or context[0]!=workflow:raise ValueError('Runtime stage requires a persisted business run')
    base,is_local=endpoint();secret=os.environ.get('BANFEI_RUNTIME_SHARED_KEY','')
    auth=os.environ.get('BANFEI_AGENTARTS_BEARER','')
    if len(secret)<32 or (not is_local and not auth):raise ValueError('Runtime server-side credentials not configured')
    error_diagnostics.register_secret(secret);error_diagnostics.register_secret(auth)
    preflight=config.get('_runtime_preflight',lambda: True)
    if preflight() is False:raise ValueError('Prepared source snapshot changed before dispatch')
    stamp=configuration_stamp(config);selected=model_config_from_record(config);policy=get_settings()
    session_key='runtime_session:'+context[2];operation_key='runtime_stage:'+context[2]+':'+stage
    with get_db() as conn:
        conn.lock_writer();authorize(conn,context)
        material=source_stamp(conn)
        session=load(conn,session_key)
        if session is None:
            session={'session_id':str(uuid.uuid4()),'destination':digest(base),'incarnation':None}
            save(conn,session_key,session)
        if session['destination']!=digest(base):raise ValueError('Runtime destination changed during run')
        if load(conn,operation_key) is not None:raise ValueError('Stage already dispatched; reconcile or explicitly retry the VM run')
    headers={'X-Banfei-Runtime-Key':secret,'X-Hw-Agentarts-Session-Id':session['session_id'],'Content-Type':'application/json'}
    if auth:headers['Authorization']='Bearer '+auth
    def guard():
        if preflight() is False:raise ValueError("Prepared source snapshot or permission changed")
        with get_db() as conn:
            authorize(conn,context);pinned_configuration(stamp,conn)
            if source_stamp(conn)!=material:raise ValueError('Source version or permission changed during Runtime execution')
    packet=None
    with client_for() as client:
        try:
            guard()
            if session['incarnation'] is None:
                response=client.get(operation_url(base, 'runtime-info'),headers=headers);response.raise_for_status();info=response.json()
                if info.get('protocol')!=PROTOCOL:raise ValueError('Runtime protocol mismatch')
                if info.get('provider_route')!=model_route(selected.base_url,selected.model):raise ValueError('Runtime provider/model route does not match selected configuration')
                session['incarnation']=str(uuid.UUID(info['incarnation']))
                with get_db() as conn:
                    conn.lock_writer();authorize(conn,context)
                    current=load(conn,session_key)
                    if current!= {**session,'incarnation':None}:raise ValueError('Concurrent Runtime session handshake')
                    save(conn,session_key,session)
            packet=StageRequest(task_id=context[1],run_id=context[2],session_id=session['session_id'],incarnation=session['incarnation'],
                operation_id=uuid.uuid5(uuid.UUID(context[2]),stage),workflow=workflow,stage=stage,snapshot=digest(data),
                model_fingerprint=stamp['fingerprint'],input_token_budget=RUNTIME_INPUT_BUDGET,data=data,sources=source_manifest(data),
                model=ModelOptions(provider_route=model_route(selected.base_url,selected.model),name=selected.model,temperature=selected.temperature,top_p=selected.top_p,
                  max_tokens=stage_output_limit(workflow,stage,data,min(selected.max_tokens,config.get('_match_output_tokens',RUNTIME_OUTPUT_BUDGET))),
                  timeout_seconds=policy.timeoutSeconds,timeout_retries=policy.timeoutRetries))
            validate_budget(packet)
            encoded=packet.model_dump(mode='json');expected={k:encoded[k] for k in ('protocol','task_id','run_id','session_id','operation_id','incarnation','workflow','stage','snapshot','model_fingerprint')}
            state={**expected,'status':'dispatching','attempt':0,'material_stamp':material}
            with get_db() as conn:
                conn.lock_writer();authorize(conn,context)
                if load(conn,operation_key) is not None:raise ValueError('Stage dispatch conflict')
                save(conn,operation_key,state)
            guard()
            # Exactly one POST. If acknowledgement is lost, GET reconciles this operation.
            # A 404/new incarnation must fail: never run a potentially-paid stage twice.
            try:
                response=client.post(operation_url(base, 'jobs'),headers=headers,json=encoded);response.raise_for_status()
            except httpx.TransportError:response=None
            limit=time.monotonic()+packet.model.timeout_seconds*(packet.model.timeout_retries+1)+45
            previous_rank=-1;previous_attempt=0;previous_time=''
            ranks={'accepted':0,'running':1,'awaiting_retry':1,'completed':2,'failed':2,'interrupted':2}
            granted_attempts=set()
            while time.monotonic()<limit:
                guard()
                if response is None:
                    for retry in range(3):
                        try:
                            response=client.get(operation_url(base, 'jobs/'+str(packet.operation_id)),headers=headers);response.raise_for_status();break
                        except httpx.TransportError:
                            if retry==2:raise
                            time.sleep(.2*(retry+1));guard()
                result=response.json()
                if any(result.get(k)!=v for k,v in expected.items()):raise ValueError('Runtime result binding mismatch')
                status=result.get('status');attempt=result.get('attempt',0);updated=result.get('updated_at','')
                if status not in ranks or ranks[status]<previous_rank or not isinstance(attempt,int) or attempt<previous_attempt or not isinstance(updated,str) or updated<previous_time:raise ValueError('Out-of-order Runtime progress')
                previous_rank=ranks[status];previous_attempt=attempt;previous_time=updated
                state.update(status=status,attempt=attempt,updated_at=updated)
                state.pop('diagnostic',None);state.pop('error',None)
                safe=sanitize_diagnostic(result.get('diagnostic'),status)
                if status in ('awaiting_retry','failed','interrupted'):
                    if safe:state['diagnostic']=safe
                    legacy_error=result.get('error')
                    if type(legacy_error) is str and legacy_error in LEGACY_ERRORS:
                        state['error']=legacy_error
                with get_db() as conn:
                    conn.lock_writer();authorize(conn,context)
                    if source_stamp(conn)!=material:raise ValueError('Source revoked before progress persistence')
                    save(conn,operation_key,state)
                if status=='completed':
                    raw=json.dumps(result['result'],ensure_ascii=False)
                    validate_output(packet,raw);guard();return raw
                if status=='awaiting_retry':
                    if not 1<=attempt<=packet.model.timeout_retries:raise ValueError('Unexpected Runtime retry request')
                    if attempt in granted_attempts:raise ValueError('Retry acknowledgement unresolved; explicit task retry required')
                    guard()
                    state['retry_authorized_after_attempt']=attempt
                    with get_db() as conn:
                        conn.lock_writer();authorize(conn,context);pinned_configuration(stamp,conn)
                        if source_stamp(conn)!=material:raise ValueError('Source revoked before retry authorization')
                        save(conn,operation_key,state)
                    guard()
                    granted_attempts.add(attempt)
                    try:
                        response=client.post(operation_url(base, 'jobs/'+str(packet.operation_id)+'/retry'),headers=headers,
                            json={'incarnation':packet.incarnation.hex,'after_attempt':attempt})
                        response.raise_for_status()
                    except httpx.TransportError:response=None
                    continue
                if status in ('failed','interrupted'):
                    if safe:
                        raise StageFailure(safe['reason_code'], **{k:v for k,v in safe.items() if k not in ('reason_code','error_type')})
                    raise ValueError('Runtime stage failed; explicitly retry task')
                response=None;time.sleep(min(5,max(.001,float(os.environ.get('BANFEI_RUNTIME_POLL_SECONDS','1')))))
            raise TimeoutError('Runtime stage did not complete within its bounded budget')
        except Exception:
            if packet is not None:
                try:client.delete(operation_url(base, 'jobs/'+str(packet.operation_id)),headers=headers)
                except Exception:pass  # Lease expiry also stops orphaned retries; never replay.
                try:
                    with get_db() as conn:
                        conn.lock_writer()
                        current=load(conn,operation_key)
                        if current and current.get('status') in ('dispatching','accepted','running','awaiting_retry'):
                            current['status']='interrupted';save(conn,operation_key,current)
                except Exception:pass
            raise


def interrupt_operations(conn,run_id):
    if not run_id:return
    prefix='runtime_stage:'+str(run_id)+':%'
    for row in conn.execute('SELECT key,value FROM app_metadata WHERE key LIKE ?',(prefix,)).fetchall():
        value=json.loads(row['value'])
        if value.get('status') in ('dispatching','accepted','running','awaiting_retry'):
            value['status']='interrupted'
            save(conn,row['key'],value)
