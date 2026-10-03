"""Transactional Plan/Run/Version lifecycle. Understanding runs outside transactions."""
import hashlib
import json
import uuid
from datetime import datetime,timezone,timedelta
from fastapi import HTTPException
from .database import get_db
from .auth import ensure_account_active
from . import enablement_catalog
from .development_deadlines import run_timeout
from .development_types import DevelopmentRequest,Revise
from .error_diagnostics import record_error, bind_context
from . import task_progress


def now():return datetime.now(timezone.utc).isoformat()
def uid():return str(uuid.uuid4())
def dump(value):return json.dumps(value,ensure_ascii=False,sort_keys=True)
def fail(code,message):raise HTTPException(code,message)

PLAN_COLUMNS='id,owner_user_id,request_id,target_partner_id,status,current_version_id,active_run_id,archived_at,created_at,updated_at'



def clarify(payload: DevelopmentRequest):
    data=payload.model_dump()
    direction=(data['development_direction'] or data['development_goal'] or data['raw_demand']).strip()
    # Legacy scheduling fields remain stored; direction and self-reported baseline drive advice.
    data['development_direction']=direction
    data['development_goal']=direction
    if not data['raw_demand']:data['raw_demand']=direction
    missing=[] if direction else ['development_direction']
    return {'missing_fields':missing,'request':data}


def authorize(conn,plan_id,user):
    row=conn.execute(f'SELECT {PLAN_COLUMNS} FROM development_plans WHERE id=?',(plan_id,)).fetchone()
    if not row or (user['role']!='admin' and row['owner_user_id']!=user['id']):fail(404,'方案不存在或无权访问')
    return dict(row)


def audit(conn,plan_id,actor,action,version_id=None):
    conn.execute('INSERT INTO development_audit_events VALUES (?,?,?,?,?,?)',(uid(),plan_id,version_id,actor,action,now()))


def checked_request(payload,user):
    result=clarify(payload)
    if result['missing_fields']:fail(422,'请描述发展需求')
    data=result['request']
    if data['target_partner_id'] is None and any(data[k] for k in ('source_task_id','source_case_id','source_case_version')):
        fail(422,'来源资料需要关联已有伙伴；不关联时请清除来源资料')
    context=enablement_catalog.context(user,data['target_partner_id'],data['source_task_id'],data['source_case_id'],data['source_case_version'])
    if context['shared_case']:data['source_case_version']=context['shared_case']['source_version']
    return data


def fingerprint(payload):return hashlib.sha256(dump(payload).encode()).hexdigest()

def duplicate(conn,user,submission_id,request_hash):
    row=conn.execute('SELECT * FROM development_runs WHERE owner_user_id=? AND submission_id=?',(user['id'],submission_id)).fetchone()
    if row:
        if row['request_hash']!=request_hash:fail(409,'同一提交标识不能用于不同请求')
        return {'plan_id':row['plan_id'],'run_id':row['id'],'task_type':'development_plan','replayed':True}


def insert_run(conn,plan_id,user,submission_id,base,payload,run_type,request_hash):
    ensure_account_active(conn,user['id'])
    run_id=uid();stamp=now()
    payload={**payload,'progress':task_progress.new('development_plan',run_id,stamp)}
    bind_context(task_id=plan_id, run_id=run_id, request_id=submission_id, stage='submission')
    conn.execute('''INSERT INTO development_runs(id,plan_id,owner_user_id,run_type,submission_id,request_hash,based_on_version_id,status,input_snapshot,created_at)
                    VALUES (?,?,?,?,?,?,?,'pending',?,?)''',(run_id,plan_id,user['id'],run_type,submission_id,request_hash,base,dump(payload),stamp))
    conn.execute('UPDATE development_plans SET active_run_id=?,updated_at=? WHERE id=?',(run_id,stamp,plan_id))
    audit(conn,plan_id,user['id'],run_type)
    return {'plan_id':plan_id,'run_id':run_id,'task_type':'development_plan','replayed':False}


def create(payload,user):
    bind_context(request_id=payload.submission_id,stage='submission')
    digest=fingerprint(payload.model_dump())
    with get_db() as conn:
        replay=duplicate(conn,user,payload.submission_id,digest)
        if replay:return replay
    data=checked_request(payload.request,user)
    data['raw_demand']=payload.request.raw_demand or payload.request.development_direction or payload.request.development_goal
    with get_db() as conn:
        conn.lock_writer()
        replay=duplicate(conn,user,payload.submission_id,digest)
        if replay:return replay
        request_id=uid();plan_id=uid();stamp=now()
        conn.execute('INSERT INTO development_requests VALUES (?,?,?,?,?,?)',(request_id,user['id'],data['target_partner_id'],dump(data),stamp,user['id']))
        conn.execute('''INSERT INTO development_plans(id,owner_user_id,request_id,target_partner_id,status,created_at,updated_at) VALUES (?,?,?,?,'active',?,?)''',(plan_id,user['id'],request_id,data['target_partner_id'],stamp,stamp))
        result=insert_run(conn,plan_id,user,payload.submission_id,None,{'request':data,'instruction':'','understanding':None},'generate',digest)
    # Leaving get_db commits before the router submits background execution.
    return result


def writable(plan,base):
    if plan['status']!='active':fail(409,'方案已归档，请先恢复')
    if plan['active_run_id']:fail(409,'方案正在执行，请等待当前运行结束')
    if plan['current_version_id']!=base:fail(409,'版本冲突：当前版本已变化，请重新载入后编辑')


def revise(plan_id,payload,user):
    if not payload.instruction.strip():fail(422,'请输入本次要求')
    bind_context(task_id=plan_id,request_id=payload.submission_id,stage='submission')
    digest=fingerprint({'plan_id':plan_id,**payload.model_dump()})
    with get_db() as conn:
        plan=authorize(conn,plan_id,user)
        replay=duplicate(conn,user,payload.submission_id,digest)
        if replay:return {'kind':'revise',**replay}
        stored=json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',(plan['request_id'],)).fetchone()[0])
        for item in stored.get('_conversation',[]):
            if item['submission_id']==payload.submission_id:
                if item['fingerprint']!=digest:fail(409,'同一提交标识不能用于不同请求')
                from .development_views import protected,version_row,REVOKED
                if protected(conn,version_row(conn,plan,item['version_id'])):fail(409,REVOKED)
                return {'kind':'explain','answer':item['answer'],'replayed':True}
        writable(plan,payload.based_on_version_id)
        data=stored if payload.request is None else payload.request.model_dump()
        data={k:v for k,v in data.items() if k in DevelopmentRequest.model_fields}
        if data['target_partner_id']!=plan['target_partner_id']:fail(409,'同一方案不能更换目标伙伴')
    data=checked_request(DevelopmentRequest.model_validate(data),user)
    if payload.request is not None:data['_explicit_request']=True
    with get_db() as conn:
        conn.lock_writer();plan=authorize(conn,plan_id,user)
        replay=duplicate(conn,user,payload.submission_id,digest)
        if replay:return {'kind':'revise',**replay}
        writable(plan,payload.based_on_version_id)
        result=insert_run(conn,plan_id,user,payload.submission_id,payload.based_on_version_id,{'request':data,'instruction':payload.instruction,'understanding':None},'revise',digest)
    return {'kind':'revise',**result}


def save_answer(plan_id,payload,user,data,understanding,digest,run=None):
    from .development_context import load
    fresh=load(data,user,plan_id=plan_id,base=payload.based_on_version_id,message=payload.instruction)
    if fresh['stamp']!=understanding['stamp']:fail(409,'资料或当前要求已变化，请刷新后重试')
    result=understanding['analysis']
    with get_db() as conn:
        conn.lock_writer();plan=authorize(conn,plan_id,user)
        if run:
            current_run=conn.execute('SELECT * FROM development_runs WHERE id=?',(run['id'],)).fetchone()
            if not current_run or current_run['status']!='running' or current_run['execution_token']!=run['execution_token'] or plan['active_run_id']!=run['id'] or plan['current_version_id']!=payload.based_on_version_id or expired(current_run):
                fail(409,'运行不再拥有保存权限')
        else:writable(plan,payload.based_on_version_id)
        current=load(data,user,plan_id=plan_id,base=payload.based_on_version_id,message=payload.instruction,connection=conn)
        if current['stamp']!=understanding['stamp']:fail(409,'资料或当前要求已变化，请刷新后重试')
        stored=json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',(plan['request_id'],)).fetchone()[0])
        history=stored.get('_conversation',[])
        for item in history:
            if item['submission_id']==payload.submission_id:
                if item['fingerprint']!=digest:fail(409,'同一提交标识不能用于不同请求')
                return {'kind':'explain','answer':item['answer'],'replayed':True}
        history.append({'submission_id':payload.submission_id,'fingerprint':digest,'version_id':payload.based_on_version_id,'message':payload.instruction,'answer':result['answer'],'references':result['references'],'created_at':now()})
        stored.update(_conversation=history,_effective_version_id=payload.based_on_version_id,_effective_request={
            **fresh['request'],'development_direction':result['effective_direction'],'development_goal':result['effective_direction'],'constraints':result['effective_constraints'],'known_baseline':result.get('effective_baseline',fresh['request'].get('known_baseline',''))})
        conn.execute('UPDATE development_requests SET payload_json=? WHERE id=?',(dump(stored),plan['request_id']))
        audit(conn,plan_id,user['id'],'conversation_explained',payload.based_on_version_id)
        if run: finish_without_version(conn,current_run)
        return {'kind':'explain','answer':result['answer']}


def run_stage(run_id, token, key, state, understanding=None):
    with get_db() as conn:
        conn.lock_writer()
        run=conn.execute('SELECT * FROM development_runs WHERE id=?',(run_id,)).fetchone()
        if not run or run['status']!='running' or run['execution_token']!=token or expired(run):
            fail(409,'运行已失效或超时')
        snapshot=json.loads(run['input_snapshot'])
        if understanding is not None:snapshot['understanding']=understanding
        task_progress.stage(snapshot.get('progress'),key,state)
        conn.execute('UPDATE development_runs SET input_snapshot=? WHERE id=?',(dump(snapshot),run_id))


def finish_progress(conn, run, failed=False, scope_message=None):
    snapshot=json.loads(run['input_snapshot'])
    task_progress.finish(snapshot.get('progress'),failed=failed)
    if scope_message:snapshot['scope_message']=scope_message
    conn.execute('UPDATE development_runs SET input_snapshot=? WHERE id=?',(dump(snapshot),run['id']))


def finish_without_version(conn, run, scope_message=None):
    finish_progress(conn,run,scope_message=scope_message)
    conn.execute("UPDATE development_runs SET status='ready',ended_at=? WHERE id=?",(now(),run['id']))
    conn.execute('UPDATE development_plans SET active_run_id=NULL,updated_at=? WHERE id=? AND active_run_id=?',(now(),run['plan_id'],run['id']))


def complete_scope(run_id, token, message):
    with get_db() as conn:
        conn.lock_writer()
        run=conn.execute('SELECT * FROM development_runs WHERE id=?',(run_id,)).fetchone()
        if not run or run['status']!='running' or run['execution_token']!=token or expired(run):fail(409,'运行已失效或超时')
        finish_without_version(conn,run,message)


def claim(run_id):
    with get_db() as conn:
        conn.lock_writer()
        row=conn.execute('SELECT * FROM development_runs WHERE id=?',(run_id,)).fetchone()
        if not row or row['status']!='pending':return None
        token=uid();stamp=now();conn.execute("UPDATE development_runs SET status='running',execution_token=?,started_at=? WHERE id=?",(token,stamp,run_id))
        return {**dict(row),'execution_token':token,'started_at':stamp}


def expired(run):
    started = datetime.fromisoformat(run['started_at'] or run['created_at'])
    return (datetime.now(timezone.utc) - started).total_seconds() >= run_timeout()


def ensure_execution(run_id, token):
    with get_db() as conn:
        run = conn.execute('SELECT * FROM development_runs WHERE id=?', (run_id,)).fetchone()
        if not run or run['status'] != 'running' or run['execution_token'] != token or expired(run):
            fail(409, '运行已失效或超时')


def finish_failure(run_id,token,stage,status='failed',error=None):
    from .task_failures import failure
    if error is not None:record_error(error,stage,run_id=run_id)
    with get_db() as conn:
        conn.lock_writer()
        row=conn.execute('SELECT * FROM development_runs WHERE id=?',(run_id,)).fetchone()
        if not row or row['execution_token']!=token or row['status']!='running':return
        bind_context(task_id=row['plan_id'], run_id=run_id)
        record_error(error or RuntimeError('Execution exceeded the configured run deadline' if stage=='run_timeout' else 'Execution interrupted'), stage, task_id=row['plan_id'], run_id=run_id, request_id=row['submission_id'])
        finish_progress(conn,row,failed=True)
        message=dump([failure(stage,error)])
        conn.execute('UPDATE development_runs SET status=?,ended_at=?,error_stage=?,safe_error_message=? WHERE id=?',(status,now(),stage,message,run_id))
        conn.execute('UPDATE development_plans SET active_run_id=NULL,updated_at=? WHERE id=? AND active_run_id=?',(now(),row['plan_id'],run_id))


def save_version(conn,plan,base,payload,dependencies,actor,run_id=None):
    if plan['current_version_id']!=base:fail(409,'版本冲突：较早请求不能覆盖新版本')
    for item in (i for stage in payload['stages'] for i in stage['items']):item.setdefault('item_id',uid())
    version_id=uid();number=conn.execute('SELECT COALESCE(MAX(version_no),0)+1 FROM development_versions WHERE plan_id=?',(plan['id'],)).fetchone()[0]
    conn.execute('INSERT INTO development_versions VALUES (?,?,?,?,?,?,?,?,?)',(version_id,plan['id'],number,base,run_id,dump(payload),dump(dependencies),actor,now()))
    ordinal=0
    for stage in payload['stages']:
        for item in stage['items']:
            conn.execute('INSERT INTO development_version_items VALUES (?,?,?,?)',(uid(),version_id,ordinal,dump({'stage':stage['title'],**item})))
            ordinal+=1
    for diagnosis in payload['diagnoses']:
        conn.execute('INSERT INTO development_diagnoses VALUES (?,?,?)',(version_id,diagnosis['capability_tag_id'],dump(diagnosis)))
    conn.execute('UPDATE development_plans SET current_version_id=?,updated_at=? WHERE id=?',(version_id,now(),plan['id']))
    audit(conn,plan['id'],actor,'version_created',version_id)
    return version_id


def complete(run_id,token,payload,dependencies,validate):
    with get_db() as conn:
        conn.lock_writer()
        run=conn.execute('SELECT * FROM development_runs WHERE id=?',(run_id,)).fetchone()
        if not run or run['status']!='running' or run['execution_token']!=token or expired(run):fail(409,'运行已失效或超时')
        plan=dict(conn.execute(f'SELECT {PLAN_COLUMNS} FROM development_plans WHERE id=?',(run['plan_id'],)).fetchone())
        if plan['status']!='active' or plan['active_run_id']!=run_id:fail(409,'运行不再拥有保存权限')
        validate(conn,payload,dependencies)
        if expired(run):fail(409,'运行已超时')
        version_id=save_version(conn,plan,run['based_on_version_id'],payload,dependencies,run['owner_user_id'],run_id)
        if expired(run):fail(409,'运行已超时')
        finish_progress(conn,run)
        conn.execute("UPDATE development_runs SET status='ready',ended_at=? WHERE id=?",(now(),run_id))
        conn.execute('UPDATE development_plans SET active_run_id=NULL WHERE id=?',(plan['id'],))
        return version_id


def archive(plan_id,user,restore=False):
    with get_db() as conn:
        conn.lock_writer();plan=authorize(conn,plan_id,user)
        if plan['active_run_id']:fail(409,'运行中不能归档或恢复，请等待执行结束')
        conn.execute('UPDATE development_plans SET status=?,archived_at=?,updated_at=? WHERE id=?',('active' if restore else 'archived',None if restore else now(),now(),plan_id))
        audit(conn,plan_id,user['id'],'restored' if restore else 'archived')


def recover(startup=False,owner_user_id=None,plan_id=None):
    with get_db() as conn:
        conn.lock_writer()
        # A terminal Run cannot own the execution lock. Repair old interrupted
        # finalization without changing the current result or creating a task.
        conn.execute("""UPDATE development_plans SET active_run_id=NULL
            WHERE (? IS NULL OR owner_user_id=?) AND (? IS NULL OR id=?)
              AND EXISTS (SELECT 1 FROM development_runs r
                  WHERE r.id=development_plans.active_run_id AND r.plan_id=development_plans.id
                    AND r.status IN ('failed','partial','interrupted','ready'))""",
                     (owner_user_id,owner_user_id,plan_id,plan_id))
        threshold=(datetime.now(timezone.utc)-timedelta(seconds=run_timeout())).isoformat()
        rows=conn.execute("SELECT * FROM development_runs WHERE status IN ('pending','running') AND (?=1 OR COALESCE(started_at,created_at)<?) AND (? IS NULL OR owner_user_id=?) AND (? IS NULL OR plan_id=?)",(int(startup),threshold,owner_user_id,owner_user_id,plan_id,plan_id)).fetchall()
        for row in rows:
            from .runtime_bridge import interrupt_operations
            interrupt_operations(conn,row['id'])
            finish_progress(conn,row,failed=True)
            record_error(RuntimeError('Service restart interrupted unfinished execution' if startup else 'Stale execution exceeded the recovery deadline'), 'interrupted', task_id=row['plan_id'], run_id=row['id'])
            conn.execute("UPDATE development_runs SET status='interrupted',ended_at=?,safe_error_message='执行已中断，旧版本保持不变',error_stage='interrupted' WHERE id=?",(now(),row['id']))
            conn.execute('UPDATE development_plans SET active_run_id=NULL WHERE id=? AND active_run_id=?',(row['plan_id'],row['id']))


def retry(plan_id,payload,user):
    with get_db() as conn:authorize(conn,plan_id,user)
    recover(plan_id=plan_id,owner_user_id=None if user['role']=='admin' else user['id'])
    bind_context(task_id=plan_id,request_id=payload.submission_id,stage='submission')
    digest=fingerprint({'plan_id':plan_id,'retry_run_id':payload.run_id,**payload.model_dump()})
    with get_db() as conn:
        plan=authorize(conn,plan_id,user)
        replay=duplicate(conn,user,payload.submission_id,digest)
        if replay:return replay
        stored=json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',(plan['request_id'],)).fetchone()[0])
        for message in stored.get('_conversation',[]):
            if message['submission_id']==payload.submission_id:
                if message['fingerprint']!=digest:fail(409,'同一提交标识不能用于不同请求')
                from .development_views import protected,version_row,REVOKED
                if protected(conn,version_row(conn,plan,message['version_id'])):fail(409,REVOKED)
                return {'kind':'explain','answer':message['answer'],'replayed':True}
        original=conn.execute('SELECT * FROM development_runs WHERE id=? AND plan_id=?',(payload.run_id,plan_id)).fetchone()
        if not original:fail(404,'运行记录不存在')
        writable(plan,payload.based_on_version_id)
        latest=conn.execute('SELECT id FROM development_runs WHERE plan_id=? ORDER BY created_at DESC,id DESC LIMIT 1',(plan_id,)).fetchone()
        if latest['id']!=payload.run_id or original['status'] not in ('failed','partial','interrupted'):fail(409,'运行状态已变化，请重新载入')
        if original['based_on_version_id']!=payload.based_on_version_id:fail(409,'版本冲突：请基于当前建议重新提出调整')
        snapshot=json.loads(original['input_snapshot'])
    data=checked_request(DevelopmentRequest.model_validate({k:v for k,v in snapshot['request'].items() if k in DevelopmentRequest.model_fields}),user)
    if snapshot['request'].get('_explicit_request'):data['_explicit_request']=True
    with get_db() as conn:
        conn.lock_writer();plan=authorize(conn,plan_id,user)
        replay=duplicate(conn,user,payload.submission_id,digest)
        if replay:return replay
        writable(plan,payload.based_on_version_id)
        latest=conn.execute('SELECT * FROM development_runs WHERE plan_id=? ORDER BY created_at DESC,id DESC LIMIT 1',(plan_id,)).fetchone()
        if latest['id']!=payload.run_id or latest['status'] not in ('failed','partial','interrupted'):fail(409,'运行状态已变化，请重新载入')
        if latest['based_on_version_id']!=payload.based_on_version_id:fail(409,'版本冲突：请基于当前建议重新提出调整')
        result=insert_run(conn,plan_id,user,payload.submission_id,payload.based_on_version_id,{'request':data,'instruction':snapshot['instruction'],'understanding':snapshot.get('understanding')},latest['run_type'],digest)
    return result
