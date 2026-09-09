"""Live authorization for historical snapshots; immutable storage stays untouched."""
from .task_failures import public_failures
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

def presentation(conn,plan):
    """Read-time Plan availability, independent of the latest Run's execution result."""
    current=conn.execute('SELECT * FROM development_versions WHERE plan_id=? AND id=?',(plan['id'],plan['current_version_id'])).fetchone()
    confirmed=conn.execute('SELECT * FROM development_versions WHERE plan_id=? AND id=?',(plan['id'],plan['confirmed_version_id'])).fetchone()
    current_available=current is not None and not protected(conn,current)
    confirmed_available=confirmed is not None and not protected(conn,confirmed)
    latest=conn.execute('SELECT status,run_type FROM development_runs WHERE plan_id=? ORDER BY CASE WHEN id=? THEN 0 ELSE 1 END,created_at DESC,id DESC LIMIT 1',(plan['id'],plan['active_run_id'])).fetchone()
    if plan['status']=='archived':state='archived'
    elif confirmed_available:state='available'
    elif current_available:state='draft'
    elif current or confirmed:state='restricted'
    elif latest and latest['status'] in ('pending','running'):state='generating'
    else:state='generation_failed'
    return {'state':state,'current_version':current['version_no'] if current else None,
            'confirmed_version':confirmed['version_no'] if confirmed else None,
            'current_is_confirmed':bool(current and confirmed and current['id']==confirmed['id']),
            'current_available':current_available,'confirmed_available':confirmed_available,
            'latest_run_status':latest['status'] if latest else None,
            'latest_run_type':latest['run_type'] if latest else None}

def detail(plan_id,user,version_id=None):
    with get_db() as conn:life.authorize(conn,plan_id,user)
    life.recover(plan_id=plan_id)
    with get_db() as conn:
        conn.execute('BEGIN');plan=life.authorize(conn,plan_id,user)
        request=json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',(plan['request_id'],)).fetchone()[0])
        versions=[dict(r) for r in conn.execute('SELECT id,version_no,based_on_version_id,created_by,created_at FROM development_versions WHERE plan_id=? ORDER BY version_no DESC',(plan_id,))]
        runs=[dict(r) for r in conn.execute('SELECT id,run_type,based_on_version_id,status,model_config_id,created_at,started_at,ended_at,error_stage,safe_error_message FROM development_runs WHERE plan_id=? ORDER BY created_at DESC,id DESC',(plan_id,))]
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
        conversation=request.pop('_conversation',[])
        conversation=[m for m in conversation if not protected(conn,version_row(conn,plan,m['version_id']))]
        # Modification messages already live in Run input snapshots; do not duplicate them.
        for run in conn.execute("SELECT id,based_on_version_id,input_snapshot,status,created_at FROM development_runs WHERE plan_id=? AND run_type='revise'",(plan_id,)):
            if run['based_on_version_id'] and protected(conn,version_row(conn,plan,run['based_on_version_id'])):continue
            instruction=engine.safe_text(json.loads(run['input_snapshot']).get('instruction',''),engine.blocked_fragments(conn))
            if instruction:
                response='建议已更新，可以继续查看或讨论。' if run['status']=='ready' else '本次调整未完成，已有建议仍可使用。' if run['status'] in ('failed','partial','interrupted') else '正在处理本次调整，已有版本仍可使用。'
                conversation.append({'submission_id':run['id'],'message':instruction,'answer':response,'created_at':run['created_at']})
        conversation.sort(key=lambda m:m['created_at'])
        # Source-sensitive user text is also withheld after revocation, including original demand.
        if hidden:request={k:v for k,v in request.items() if k in ('target_partner_id','request_source','targets')};request['targets']=[]
        return {'plan':plan,'presentation':presentation(conn,plan),'partner_name':partner[0] if partner else '不可用伙伴','request':request,'conversation':[] if hidden else conversation,'versions':versions,'runs':runs,'failureDetails':public_failures(runs[0]['error_stage'],runs[0]['safe_error_message']) if runs and runs[0]['status'] in ('failed','partial','interrupted') else [],'payload':payload,'hidden':hidden,'notice':REVOKED if hidden else None}

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
        if body.corrections:life.fail(422,'请通过自然语言反馈事实，正式画像仍由既有机制维护')
        analysis=payload.get('analysis',{'priorities':[]})
        pool=engine.candidates(conn,request,analysis)
        output={'target_partner_id':plan['target_partner_id'],'stages':[v.model_dump() for v in body.stages],
                'limitations':payload.get('limitations',[]),'resource_gaps':[],
                'answer':payload.get('answer',''),'next_steps':payload.get('next_steps',[])}
        try:
            result=engine.assemble(output,request,analysis,pool,user['id']);deps=engine.dependencies(conn,pool+analysis.get('profile_basis',{}).get('shared_evidence',[]))
            engine.validate_dependencies(conn,result,deps)
        except (engine.InvalidOutput,HTTPException):life.fail(422,'资源或内容校验失败，请刷新候选资源后重试')
        version_id=life.save_version(conn,plan,body.based_on_version_id,result,deps,user['id'])
        return {'version_id':version_id}

def options(plan_id,user):
    with get_db() as conn:
        conn.execute('BEGIN');plan=life.authorize(conn,plan_id,user);row=version_row(conn,plan);payload=readable_payload(conn,row)
        if payload is None:life.fail(409,REVOKED)
        request=json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',(plan['request_id'],)).fetchone()[0]);request.update(payload.get('effective_request',{}))
        return engine.candidates(conn,request,payload.get('analysis',{'priorities':[]}))

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


def converse(plan_id,body,user):
    """Explain against a reauthorized snapshot; only a modification gets a Run/Version.

    Messages use the existing Request JSON, never the immutable Version or an audit text
    field. Both request and answer are withheld when their source version is revoked.
    """
    from .development_types import ConversationOutput,Revise
    from . import development_model as model
    digest=life.fingerprint(body.model_dump())
    with get_db() as conn:
        conn.execute('BEGIN');plan=life.authorize(conn,plan_id,user)
        # Replays are checked before active-run conflicts, just like lifecycle submissions.
        stored=json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',(plan['request_id'],)).fetchone()[0])
        for message in stored.get('_conversation',[]):
            if message['submission_id']==body.submission_id:
                if message['fingerprint']!=digest:life.fail(409,'同一消息标识不能用于不同内容')
                if protected(conn,version_row(conn,plan,message['version_id'])):life.fail(409,REVOKED)
                return {'kind':'explain','answer':message['answer']}
        run=conn.execute('SELECT id,input_snapshot,based_on_version_id FROM development_runs WHERE plan_id=? AND submission_id=?',(plan_id,body.submission_id)).fetchone()
        if run:
            if json.loads(run['input_snapshot']).get('instruction')!=body.message or run['based_on_version_id']!=body.based_on_version_id:life.fail(409,'同一消息标识不能用于不同内容')
            return {'kind':'revise','plan_id':plan_id,'run_id':run['id'],'replayed':True}
        life.writable(plan,body.based_on_version_id)
        row=version_row(conn,plan);payload=readable_payload(conn,row)
        if payload is None:life.fail(409,REVOKED)
        blocked=engine.blocked_fragments(conn);engine.guard(body.message,blocked)
        deps=json.loads(row['dependency_json'])
        pool=[];model_refs=[]
        used={engine.key(i) for stage in payload['stages'] for i in stage['items']}
        for ref in deps:
            try:
                resolved=resources.resolve_reference(conn,ref['source_type'],ref['source_id'],ref['source_version'],'model')
                model_refs.append(ref)
                if engine.key(ref) in used:pool.append(resolved)
            except HTTPException:continue
        # Never send historical free text whose model permission has since changed.
        current={'direction':payload.get('overview',{}).get('development_direction',''),'resources':pool}
        if len(model_refs)==len(deps):
            current['analysis']={k:v for k,v in payload.get('analysis',{}).items() if k in ('interpretation','partner_assessment','priorities','reusable_basis','basis_limitations')}
        engine.guard(current,blocked)
    try:
        response=engine.call(model.configuration(),'converse',{'target_partner_id':plan['target_partner_id'],'message':body.message,'current':current},ConversationOutput,blocked)
        engine.strong_guard(response)
        if response['kind']=='revise' and re.search(r'^(为什么|为何|请解释|解释一下|哪个.{0,8}(更难|适合)|有没有更进阶)|为什么适合|有什么区别|有什么差别|哪个实验更难|如何比较',body.message.strip()):
            raise engine.InvalidOutput('Explanation cannot modify a version')
        if response['target_partner_id']!=plan['target_partner_id']:raise engine.InvalidOutput('Invented partner')
        if not {engine.key(ref) for ref in response['references']}<={engine.key(ref) for ref in pool}:raise engine.InvalidOutput('Invented reference')
    except Exception:life.fail(422,'本次交流未完成，建议版本保持不变，请重试')
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE');fresh=life.authorize(conn,plan_id,user);life.writable(fresh,body.based_on_version_id)
        if protected(conn,version_row(conn,fresh)):life.fail(409,REVOKED)
        for ref in model_refs:resources.resolve_reference(conn,ref['source_type'],ref['source_id'],ref['source_version'],'model')
        if response['kind']=='explain':
            if not response['answer'].strip():life.fail(422,'解释内容为空，请重试')
            stored=json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?',(fresh['request_id'],)).fetchone()[0])
            history=stored.get('_conversation',[])
            if any(m['submission_id']==body.submission_id for m in history):life.fail(409,'消息已处理，请刷新')
            history.append({'submission_id':body.submission_id,'fingerprint':digest,'version_id':body.based_on_version_id,'message':body.message,'answer':response['answer'],'created_at':life.now()})
            stored['_conversation']=history
            conn.execute('UPDATE development_requests SET payload_json=? WHERE id=?',(life.dump(stored),fresh['request_id']))
            life.audit(conn,plan_id,user['id'],'conversation_explained',body.based_on_version_id)
            return {'kind':'explain','answer':response['answer']}
    result=life.revise(plan_id,Revise(submission_id=body.submission_id,based_on_version_id=body.based_on_version_id,instruction=body.message),user)
    return {'kind':'revise',**result}
