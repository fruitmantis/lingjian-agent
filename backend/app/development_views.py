"""Live authorization for historical snapshots; immutable storage stays untouched."""
from .task_failures import public_failures, user_message
from .error_diagnostics import bind_context, record_error
import copy,json,re
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
        if ref['source_type']=='case': continue  # Saved task prose remains readable; file access checks live visibility.
        try:
            head=resources.row_for(conn,'case' if ref['source_type']=='case' else 'resource',ref['source_id'])
            if head['status']=='revoked' or ('authorization_epoch' in ref and head['authorization_epoch']!=ref['authorization_epoch']):return True
            if not head['system_visible']:return True
        except HTTPException:return True
    return False

def readable_payload(conn,row):
    if protected(conn,row):return None
    from .development_context import identified_payload
    payload=identified_payload(conn,row)
    for stage in payload['stages']:
        for item in stage['items']:
            try:
                source=resources.resolve_reference(conn,item['source_type'],item['source_id'],item['source_version'],'system')
                if item['source_type'] != 'case':
                    item['conditions']={k:source.get(k) for k in ('duration_minutes','level','roles','zones','lab_requirements')}
                item['title']=source['title']
                item['availability']='available'
            except HTTPException:item['availability']='unavailable'
    return payload

def presentation(conn,plan):
    """Four task states; a failed Run never replaces an existing successful Version."""
    current=conn.execute('SELECT * FROM development_versions WHERE plan_id=? AND id=?',(plan['id'],plan['current_version_id'])).fetchone()
    current_available=current is not None and not protected(conn,current)
    latest=conn.execute('SELECT status,run_type FROM development_runs WHERE plan_id=? ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END,created_at DESC,id DESC LIMIT 1',(plan['id'],plan['active_run_id'])).fetchone()
    if plan['status']=='archived':state='archived'
    elif latest and latest['status'] in ('pending','running'):state='generating'
    elif current:state='available'
    else:state='generation_failed'
    # Generated status describes existence, not permission to read revoked content.
    return {'state':state,'current_version':current['version_no'] if current else None,
            'current_available':current_available,
            'latest_run_status':latest['status'] if latest else None,
            'latest_run_type':latest['run_type'] if latest else None}

def detail(plan_id,user,version_id=None):
    with get_db() as conn:life.authorize(conn,plan_id,user)
    life.recover(plan_id=plan_id)
    with get_db() as conn:
        conn.execute('BEGIN');plan=life.authorize(conn,plan_id,user)
        request=json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',(plan['request_id'],)).fetchone()[0])
        versions=[dict(r) for r in conn.execute('SELECT id,version_no,based_on_version_id,created_by,created_at FROM development_versions WHERE plan_id=? ORDER BY version_no DESC',(plan_id,))]
        runs=[dict(r) for r in conn.execute('SELECT id,submission_id,run_type,based_on_version_id,status,model_config_id,created_at,started_at,ended_at,error_stage,safe_error_message FROM development_runs WHERE plan_id=? ORDER BY created_at DESC,id DESC',(plan_id,))]
        latest_failure=public_failures(runs[0]['error_stage'],runs[0]['safe_error_message']) if runs and runs[0]['status'] in ('failed','partial','interrupted') else []
        # Historical failure text is untrusted too; expose only current safe messages.
        for run in runs:
            if run['status'] in ('failed','partial','interrupted'):
                safe=public_failures(run['error_stage'],run['safe_error_message'])[0]
                run['error_stage']=safe['stage']
                run['safe_error_message']=safe['message']
        payload=None;hidden=False
        if version_id or plan['current_version_id']:
            row=version_row(conn,plan,version_id);payload=readable_payload(conn,row);hidden=payload is None
            if payload:request.update(payload.get('effective_request',{}))
        partner=conn.execute('SELECT name FROM partners WHERE id=?',(plan['target_partner_id'],)).fetchone()
        from .development_context import exchanges
        conversation=exchanges(conn,plan,request)
        request.pop('_conversation',None)
        conversation=[m for m in conversation if not protected(conn,version_row(conn,plan,m['version_id']))]
        for message in conversation:
            cards=[]
            for ref in message.get('references',[]):
                try:
                    source=resources.resolve_reference(conn,ref['source_type'],ref['source_id'],ref['source_version'],'system')
                    cards.append({**ref,'title':source['title'],'reason':'','availability':'available','conditions':{k:source.get(k) for k in ('duration_minutes','level','roles','zones')}})
                except HTTPException:continue
            message['resources']=cards
        if request.get('_effective_version_id')==plan['current_version_id']:
            request.update(request.get('_effective_request',{}))
        request.pop('_effective_request',None);request.pop('_effective_version_id',None)
        # Source-sensitive user text is also withheld after revocation, including original demand.
        if hidden:request={k:v for k,v in request.items() if k in ('target_partner_id','request_source','targets')};request['targets']=[]
        return {'plan':plan,'presentation':presentation(conn,plan),'partner_name':partner[0] if partner else '不可用伙伴','request':request,'conversation':[] if hidden else conversation,'versions':versions,'runs':runs,'failureDetails':latest_failure,'payload':payload,'hidden':hidden,'notice':REVOKED if hidden else None}

def edit(plan_id,body,user):
    bind_context(task_id=plan_id, stage='validation')
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE');plan=life.authorize(conn,plan_id,user);life.writable(plan,body.based_on_version_id)
        row=version_row(conn,plan);payload=readable_payload(conn,row)
        if payload is None:life.fail(409,REVOKED)
        request=json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',(plan['request_id'],)).fetchone()[0]);request.update(payload.get('effective_request',{}))
        if body.corrections:life.fail(422,'请通过自然语言反馈事实，正式画像仍由既有机制维护')
        analysis=payload.get('analysis',{'priorities':[]})
        pool=engine.candidates(conn,request,analysis)
        output={'target_partner_id':plan['target_partner_id'],'stages':[v.model_dump() for v in body.stages],
                'limitations':payload.get('limitations',[]),'resource_gaps':[],
                'answer':payload.get('answer',''),'next_steps':payload.get('next_steps',[])}
        try:
            result=engine.assemble(output,request,analysis,pool,user['id']);deps=engine.dependencies(conn,pool+analysis.get('profile_basis',{}).get('shared_evidence',[]))
            engine.validate_dependencies(conn,result,deps)
        except (engine.InvalidOutput,HTTPException) as error:
            record_error(error, 'validation', task_id=plan_id)
            life.fail(422,'资源或内容校验失败，请刷新候选资源后重试')
        version_id=life.save_version(conn,plan,body.based_on_version_id,result,deps,user['id'])
        return {'version_id':version_id}

def options(plan_id,user):
    with get_db() as conn:
        conn.execute('BEGIN');plan=life.authorize(conn,plan_id,user);row=version_row(conn,plan);payload=readable_payload(conn,row)
        if payload is None:life.fail(409,REVOKED)
        request=json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',(plan['request_id'],)).fetchone()[0]);request.update(payload.get('effective_request',{}))
        return engine.candidates(conn,request,payload.get('analysis',{'priorities':[]}))

def transferable(plan_id,user,expected=None,copy_event=False):
    bind_context(task_id=plan_id, stage='transfer_validation')
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE' if copy_event else 'BEGIN');plan=life.authorize(conn,plan_id,user)
        if plan['status']!='active' or not plan['current_version_id']:life.fail(409,'仅可预览和复制有效方案的当前版本')
        if expected is not None and expected!=plan['current_version_id']:life.fail(409,'当前版本发生变化，请重新预览')
        row=version_row(conn,plan,plan['current_version_id'])
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
                for field,label in [('title','资源'),('summary','说明'),('methods','实践方法'),('source_platform','来源'),('source_url','来源链接'),('course_goals','课程目标'),('outline','课程大纲'),('lab_goals','实验目标'),('lab_requirements','基本要求'),('estimated_hours','预计投入（小时）')]:
                    if data.get(field):lines.append(f'{label}：{data[field]}')
        if len(lines)<=2:lines.append('当前没有可传递的资源安排，请联系内部负责人核实。')
        text='\n'.join(lines)
        try:engine.guard(text,engine.blocked_fragments(conn),allow_urls=True)
        except engine.InvalidOutput as error:
            record_error(error, 'transfer_validation', task_id=plan_id)
            life.fail(409,'内容不满足外发校验，请联系管理员')
        if copy_event:life.audit(conn,plan_id,user['id'],'transfer_copy',row['id'])
        return {'text':text,'version_id':row['id']}


def converse(plan_id,body,user):
    from .development_types import Revise
    return life.revise(plan_id,Revise(submission_id=body.submission_id,based_on_version_id=body.based_on_version_id,instruction=body.message),user)
