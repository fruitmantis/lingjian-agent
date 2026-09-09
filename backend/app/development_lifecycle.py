"""Transactional Plan/Run/Version lifecycle. No model or network dependencies."""
import hashlib
import json
import uuid
from datetime import datetime,timezone,timedelta
from fastapi import HTTPException
from .database import get_db
from . import enablement_catalog
from .development_deadlines import run_timeout
from .development_types import DevelopmentRequest


def now():return datetime.now(timezone.utc).isoformat()
def uid():return str(uuid.uuid4())
def dump(value):return json.dumps(value,ensure_ascii=False,sort_keys=True)
def fail(code,message):raise HTTPException(code,message)

CONSTRAINTS=('language','site','account','network','environment','cost','budget')
ASSUMPTIONS={'development_goal','trainee_role','known_baseline','duration_weeks','hours_per_week','trainee_count',*CONSTRAINTS}


def clarify(payload: DevelopmentRequest):
    data=payload.model_dump()
    direction=(data['development_direction'] or data['development_goal'] or data['raw_demand']).strip()
    # Optional legacy fields remain stored, but never control V1.2 creation/retrieval.
    data['development_direction']=direction
    data['development_goal']=direction
    if not data['raw_demand']:data['raw_demand']=direction
    missing=[k for k,v in [('target_partner_id',data['target_partner_id']),('development_direction',direction)] if not v.strip()]
    return {'missing_fields':missing,'request':data}


def authorize(conn,plan_id,user):
    row=conn.execute('SELECT * FROM development_plans WHERE id=?',(plan_id,)).fetchone()
    if not row or (user['role']!='admin' and row['owner_user_id']!=user['id']):fail(404,'方案不存在或无权访问')
    return dict(row)


def audit(conn,plan_id,actor,action,version_id=None):
    conn.execute('INSERT INTO development_audit_events VALUES (?,?,?,?,?,?)',(uid(),plan_id,version_id,actor,action,now()))


def checked_request(payload,user):
    result=clarify(payload)
    if result['missing_fields']:fail(422,{'message':'请选择伙伴并描述发展方向','missing_fields':result['missing_fields']})
    data=result['request']
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
    run_id=uid();stamp=now()
    conn.execute('''INSERT INTO development_runs(id,plan_id,owner_user_id,run_type,submission_id,request_hash,based_on_version_id,status,input_snapshot,created_at)
                    VALUES (?,?,?,?,?,?,?,'pending',?,?)''',(run_id,plan_id,user['id'],run_type,submission_id,request_hash,base,dump(payload),stamp))
    conn.execute('UPDATE development_plans SET active_run_id=?,updated_at=? WHERE id=?',(run_id,stamp,plan_id))
    audit(conn,plan_id,user['id'],run_type)
    return {'plan_id':plan_id,'run_id':run_id,'task_type':'development_plan','replayed':False}


def create(payload,user):
    digest=fingerprint(payload.model_dump())
    with get_db() as conn:
        replay=duplicate(conn,user,payload.submission_id,digest)
        if replay:return replay
    data=checked_request(payload.request,user)
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        replay=duplicate(conn,user,payload.submission_id,digest)
        if replay:return replay
        request_id=uid();plan_id=uid();stamp=now()
        conn.execute('INSERT INTO development_requests VALUES (?,?,?,?,?,?)',(request_id,user['id'],data['target_partner_id'],dump(data),stamp,user['id']))
        conn.execute('''INSERT INTO development_plans(id,owner_user_id,request_id,target_partner_id,status,created_at,updated_at) VALUES (?,?,?,?,'active',?,?)''',(plan_id,user['id'],request_id,data['target_partner_id'],stamp,stamp))
        return insert_run(conn,plan_id,user,payload.submission_id,None,{'request':data,'instruction':''},'generate',digest)


def writable(plan,base):
    if plan['status']!='active':fail(409,'方案已归档，请先恢复')
    if plan['active_run_id']:fail(409,'方案正在执行，请等待当前运行结束')
    if plan['current_version_id']!=base:fail(409,'版本冲突：当前版本已变化，请重新载入后编辑')


def revise(plan_id,payload,user):
    digest=fingerprint({'plan_id':plan_id,**payload.model_dump()})
    with get_db() as conn:
        authorize(conn,plan_id,user)
        replay=duplicate(conn,user,payload.submission_id,digest)
        if replay:return replay
    if payload.request is None:
        with get_db() as conn:
            plan=authorize(conn,plan_id,user)
            data=json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',(plan['request_id'],)).fetchone()[0])
            if plan['current_version_id']:
                saved=json.loads(conn.execute('SELECT payload_json FROM development_versions WHERE id=?',(plan['current_version_id'],)).fetchone()[0])
                data.update(saved.get('effective_request',{}))
            data={k:v for k,v in data.items() if k in DevelopmentRequest.model_fields}
        data=checked_request(DevelopmentRequest.model_validate(data),user)
    else:data=checked_request(payload.request,user)
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE');plan=authorize(conn,plan_id,user)
        replay=duplicate(conn,user,payload.submission_id,digest)
        if replay:return replay
        writable(plan,payload.based_on_version_id)
        if data['target_partner_id']!=plan['target_partner_id']:fail(409,'同一方案不能更换目标伙伴')
        return insert_run(conn,plan_id,user,payload.submission_id,payload.based_on_version_id,{'request':data,'instruction':payload.instruction},'revise',digest)


def claim(run_id):
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
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


def finish_failure(run_id,token,stage,status='failed'):
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row=conn.execute('SELECT * FROM development_runs WHERE id=?',(run_id,)).fetchone()
        if not row or row['execution_token']!=token or row['status']!='running':return
        conn.execute('UPDATE development_runs SET status=?,ended_at=?,error_stage=?,safe_error_message=? WHERE id=?',(status,now(),stage,'本次处理未完成，旧版本保持不变。请重试或联系管理员。',run_id))
        conn.execute('UPDATE development_plans SET active_run_id=NULL,updated_at=? WHERE id=? AND active_run_id=?',(now(),row['plan_id'],run_id))


def save_version(conn,plan,base,payload,dependencies,actor,run_id=None):
    if plan['current_version_id']!=base:fail(409,'版本冲突：较早请求不能覆盖新版本')
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
        conn.execute('BEGIN IMMEDIATE')
        run=conn.execute('SELECT * FROM development_runs WHERE id=?',(run_id,)).fetchone()
        if not run or run['status']!='running' or run['execution_token']!=token or expired(run):fail(409,'运行已失效或超时')
        plan=dict(conn.execute('SELECT * FROM development_plans WHERE id=?',(run['plan_id'],)).fetchone())
        if plan['status']!='active' or plan['active_run_id']!=run_id:fail(409,'运行不再拥有保存权限')
        validate(conn,payload,dependencies)
        if expired(run):fail(409,'运行已超时')
        version_id=save_version(conn,plan,run['based_on_version_id'],payload,dependencies,run['owner_user_id'],run_id)
        if expired(run):fail(409,'运行已超时')
        conn.execute("UPDATE development_runs SET status='ready',ended_at=? WHERE id=?",(now(),run_id))
        conn.execute('UPDATE development_plans SET active_run_id=NULL WHERE id=?',(plan['id'],))
        return version_id


def confirm(plan_id,version_id,user):
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE');plan=authorize(conn,plan_id,user);writable(plan,version_id)
        if not version_id or not conn.execute('SELECT id FROM development_versions WHERE id=? AND plan_id=?',(version_id,plan_id)).fetchone():fail(404,'版本不存在')
        conn.execute('UPDATE development_plans SET confirmed_version_id=?,updated_at=? WHERE id=?',(version_id,now(),plan_id))
        audit(conn,plan_id,user['id'],'confirmed',version_id)


def archive(plan_id,user,restore=False):
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE');plan=authorize(conn,plan_id,user)
        if plan['active_run_id']:fail(409,'运行中不能归档或恢复，请等待执行结束')
        conn.execute('UPDATE development_plans SET status=?,archived_at=?,updated_at=? WHERE id=?',('active' if restore else 'archived',None if restore else now(),now(),plan_id))
        audit(conn,plan_id,user['id'],'restored' if restore else 'archived')


def recover(startup=False,owner_user_id=None,plan_id=None):
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        threshold=(datetime.now(timezone.utc)-timedelta(seconds=run_timeout())).isoformat()
        rows=conn.execute("SELECT id,plan_id FROM development_runs WHERE status IN ('pending','running') AND (?=1 OR COALESCE(started_at,created_at)<?) AND (? IS NULL OR owner_user_id=?) AND (? IS NULL OR plan_id=?)",(int(startup),threshold,owner_user_id,owner_user_id,plan_id,plan_id)).fetchall()
        for row in rows:
            conn.execute("UPDATE development_runs SET status='interrupted',ended_at=?,safe_error_message='执行已中断，旧版本保持不变',error_stage='interrupted' WHERE id=?",(now(),row['id']))
            conn.execute('UPDATE development_plans SET active_run_id=NULL WHERE id=? AND active_run_id=?',(row['plan_id'],row['id']))
