"""Live authorization for historical snapshots; immutable storage stays untouched."""
import copy,json
from fastapi import HTTPException
from .database import get_db
from . import development_lifecycle as life, development_engine as engine, enablement as resources
from .development_types import PlanOutput

REVOKED='来源授权已变化，相关方案内容已隐藏。请重新生成或联系管理员。'

def version_row(conn,plan,version_id=None):
    row=conn.execute('SELECT * FROM development_versions WHERE plan_id=? AND id=?',(plan['id'],version_id or plan['current_version_id'])).fetchone()
    if not row:life.fail(404,'版本不存在')
    return row

def protected(conn,row):
    payload=json.loads(row['payload_json'])
    refs=json.loads(row['dependency_json'])
    source=payload.get('effective_request',{})
    if source.get('source_case_id'):
        refs.append({'source_type':'case','source_id':source['source_case_id'],'source_version':source['source_case_version']})
    for ref in refs:
        try:
            head=resources.row_for(conn,'case' if ref['source_type']=='case' else 'resource',ref['source_id'])
            if head['status']=='revoked' or ('authorization_epoch' in ref and head['authorization_epoch']!=ref['authorization_epoch']):return True
            if ref['source_type']=='case':resources.resolve_reference(conn,'case',ref['source_id'],ref['source_version'],'system')
            elif not head['system_visible']:return True
        except HTTPException:return True
    return False

def readable_payload(conn,row):
    if protected(conn,row):return None
    payload=json.loads(row['payload_json'])
    for stage in payload['stages']:
        for item in stage['items']:
            try:
                resources.resolve_reference(conn,item['source_type'],item['source_id'],item['source_version'],'system')
                item['availability']='available'
            except HTTPException:item['availability']='unavailable'
    return payload

def detail(plan_id,user,version_id=None):
    with get_db() as conn:life.authorize(conn,plan_id,user)
    life.recover(plan_id=plan_id)
    with get_db() as conn:
        conn.execute('BEGIN');plan=life.authorize(conn,plan_id,user)
        request=json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',(plan['request_id'],)).fetchone()[0])
        versions=[dict(r) for r in conn.execute('SELECT id,version_no,based_on_version_id,created_by,created_at FROM development_versions WHERE plan_id=? ORDER BY version_no DESC',(plan_id,))]
        runs=[dict(r) for r in conn.execute('SELECT id,run_type,based_on_version_id,status,model_config_id,created_at,started_at,ended_at,error_stage,safe_error_message FROM development_runs WHERE plan_id=? ORDER BY created_at DESC',(plan_id,))]
        payload=None;hidden=False
        if version_id or plan['current_version_id']:
            row=version_row(conn,plan,version_id);payload=readable_payload(conn,row);hidden=payload is None
            if payload:request.update(payload.get('effective_request',{}))
        partner=conn.execute('SELECT name FROM partners WHERE id=?',(plan['target_partner_id'],)).fetchone()
        # Source-sensitive user text is also withheld after revocation, including original demand.
        if hidden:request={k:v for k,v in request.items() if k in ('target_partner_id','request_source','targets')};request['targets']=[]
        return {'plan':plan,'partner_name':partner[0] if partner else '不可用伙伴','request':request,'versions':versions,'runs':runs,'payload':payload,'hidden':hidden,'notice':REVOKED if hidden else None}

def confirm(plan_id,version_id,user):
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE');plan=life.authorize(conn,plan_id,user);life.writable(plan,version_id)
        row=version_row(conn,plan,version_id)
        if protected(conn,row):life.fail(409,REVOKED)
        conn.execute('UPDATE development_plans SET confirmed_version_id=?,updated_at=? WHERE id=?',(version_id,life.now(),plan_id))
        life.audit(conn,plan_id,user['id'],'confirmed',version_id)

def edit(plan_id,body,user):
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE');plan=life.authorize(conn,plan_id,user);life.writable(plan,body.based_on_version_id)
        row=version_row(conn,plan);payload=readable_payload(conn,row)
        if payload is None:life.fail(409,REVOKED)
        request=json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',(plan['request_id'],)).fetchone()[0]);request.update(payload.get('effective_request',{}))
        diagnoses=copy.deepcopy(payload['diagnoses']);known={d['capability_tag_id'] for d in diagnoses}
        if not set(body.corrections)<=known or any(not n.strip() or len(n)>1000 for n in body.corrections.values()):life.fail(422,'判断纠正必须指定已有目标能力并填写确认依据')
        for d in diagnoses:
            if d['capability_tag_id'] in body.corrections:
                d.update(target_satisfaction='not_satisfied',judgment_source='business_correction',problem_type='trainable_gap',confirmation={'actor_user_id':user['id'],'note':body.corrections[d['capability_tag_id']],'source':'explicit_business_correction'})
        pool=engine.candidates(conn,request,diagnoses)
        output=PlanOutput(target_partner_id=plan['target_partner_id'],stages=body.stages,limitations=payload['limitations'],resource_gaps=[]).model_dump()
        try:
            result=engine.assemble(output,request,diagnoses,pool,user['id']);deps=engine.dependencies(conn,pool)
            engine.validate_dependencies(conn,result,deps)
        except (engine.InvalidOutput,HTTPException):life.fail(422,'资源或内容校验失败，请刷新候选资源后重试')
        version_id=life.save_version(conn,plan,body.based_on_version_id,result,deps,user['id'])
        if body.corrections:life.audit(conn,plan_id,user['id'],'business_correction',version_id)
        return {'version_id':version_id}

def options(plan_id,user):
    with get_db() as conn:
        conn.execute('BEGIN');plan=life.authorize(conn,plan_id,user);row=version_row(conn,plan);payload=readable_payload(conn,row)
        if payload is None:life.fail(409,REVOKED)
        request=json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',(plan['request_id'],)).fetchone()[0]);request.update(payload.get('effective_request',{}))
        return engine.candidates(conn,request,payload['diagnoses'])

def transferable(plan_id,user,expected=None,copy_event=False):
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE' if copy_event else 'BEGIN');plan=life.authorize(conn,plan_id,user)
        if plan['status']!='active' or not plan['confirmed_version_id']:life.fail(409,'仅可预览和复制有效方案的已确认版本')
        if expected is not None and expected!=plan['confirmed_version_id']:life.fail(409,'已确认版本发生变化，请重新预览')
        row=version_row(conn,plan,plan['confirmed_version_id'])
        if protected(conn,row):life.fail(409,REVOKED)
        payload=json.loads(row['payload_json']);lines=['伙伴能力发展安排']
        if payload.get('partner_goal_allowed'):lines.append('发展目标：'+payload['overview']['development_goal'])
        # Stage titles, notes, reasons and diagnostics are generated/internal text: never copied.
        for index,stage in enumerate(payload['stages'],1):
            selected=[]
            for item in stage['items']:
                try:data=resources.resolve_reference(conn,item['source_type'],item['source_id'],item['source_version'],'partner')
                except HTTPException:continue
                selected.append({**data,'estimated_hours':item['estimated_hours']})
            if not selected:continue
            lines.append(f'阶段 {index}')
            for data in selected:
                for field,label in [('title','资源'),('summary','说明'),('methods','实践方法'),('source_platform','来源'),('source_url','来源链接'),('prerequisites','先修条件'),('account_requirement','账号要求'),('environment_requirement','环境要求'),('cost','费用'),('language','语言'),('site','站点'),('estimated_hours','预计投入（小时）')]:
                    if data.get(field):lines.append(f'{label}：{data[field]}')
        if len(lines)<=2:lines.append('当前没有可传递的资源安排，请联系内部负责人核实。')
        text='\n'.join(lines)
        try:engine.guard(text,engine.blocked_fragments(conn),allow_urls=True)
        except engine.InvalidOutput:life.fail(409,'内容不满足外发校验，请联系管理员')
        if copy_event:life.audit(conn,plan_id,user['id'],'transfer_copy',row['id'])
        return {'text':text}
