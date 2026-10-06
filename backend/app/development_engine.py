"""Minimal-context diagnosis and candidate-constrained plan assembly."""
import copy,json,re
from backend.business import development
from backend.business.development import (
    InvalidOutput, key, guard, parse, request_projection, validate_analysis, strong_guard, advice_context,
)
from .error_diagnostics import diagnostic_scope, bind_context, register_secret, record_error
from threading import Timer
from contextvars import copy_context
from .development_deadlines import run_timeout
from fastapi import HTTPException
from . import development_lifecycle as life,development_model as model,enablement as resources
from .database import get_db
from . import agent_settings
from .development_types import DirectionAnalysis,AdviceOutput,Understanding,AdvicePatch,DevelopmentRequest


def blocked_fragments(conn):
    # These values are used locally as leak sentinels, never sent to any model.
    values=[r[0] for r in conn.execute("SELECT description FROM cases WHERE visible=0")]
    return [v for v in values if v and len(v.strip())>=12]


def dependencies(conn,refs):
    result=[]
    for ref in {key(r):r for r in refs}.values():
        kind='case' if ref['source_type']=='case' else 'resource'
        if kind=='case':
            from .case_content import visible_case
            stamp={'case_updated_at':visible_case(conn,ref['source_id'])['updated_at']}
        else: stamp={'authorization_epoch':resources.row_for(conn,kind,ref['source_id'])['authorization_epoch']}
        result.append({**{k:ref[k] for k in ('source_type','source_id','source_version')},**stamp})
    return result


def validate_dependencies(conn,payload,deps):
    if payload['target_partner_id'] is not None:
        partner=conn.execute('SELECT status FROM partners WHERE id=?',(payload['target_partner_id'],)).fetchone()
        if not partner or partner[0]!='active':raise InvalidOutput('Target partner unavailable')
    tags={r[0] for r in conn.execute('SELECT id FROM capability_tags WHERE enabled=1')}
    if not {d['capability_tag_id'] for d in payload['diagnoses']}<=tags:raise InvalidOutput('Target capability unavailable')
    for ref in deps:
        resources.resolve_reference(conn,ref['source_type'],ref['source_id'],ref['source_version'],'model')
        kind='case' if ref['source_type']=='case' else 'resource'
        if kind=='case':
            from .case_content import visible_case
            if ref.get('case_updated_at')!=visible_case(conn,ref['source_id'])['updated_at']:raise InvalidOutput('Case changed')
        elif resources.row_for(conn,kind,ref['source_id'])['authorization_epoch']!=ref['authorization_epoch']:raise InvalidOutput('Permission changed')
    guard(payload,blocked_fragments(conn))
    for focus in payload.get('analysis',{}).get('priorities',[]):
        if focus.get('capability_tag_id') and focus['capability_tag_id'] not in tags:raise InvalidOutput('Invented formal tag')


def call(config,stage,payload,contract,blocked):
    for secret in blocked:register_secret(secret)
    guard(payload,blocked)
    messages,schema=development.request(stage,payload,contract)
    return parse(model.completion(config,messages,schema),contract,blocked)


def safe_text(value,blocked,limit=1600):
    if not value:return ''
    text=str(value)
    try:guard(text,blocked)
    except InvalidOutput:return ''
    return text[:limit]


def profile_context(conn,request):
    """Explicit request consent applies only to this fixed summary projection, never attachments.

    API callers without consent still get direction-based advice; visibility alone
    does not authorize profile transmission.
    Internal case bodies, deliverable contents/filenames and project risk prose stay local.
    """
    if request['target_partner_id'] is None:
        return {'basis_limited':True,'shared_evidence':[],'notice':'未关联已有伙伴资料，仅依据用户提供的信息；未说明的能力待核实'}
    if not request.get('model_input_allowed'):return {'basis_limited':True,'notice':'未获准使用画像摘要，仅依据发展方向'}
    row=conn.execute("SELECT * FROM partners WHERE id=? AND status='active'",(request['target_partner_id'],)).fetchone()
    if not row:raise InvalidOutput('Partner unavailable')
    from .business_taxonomy import canonical, region_groups
    blocked=blocked_fragments(conn);row=dict(row)
    row["industries"]=canonical(row.get("industries"),"industry")
    row["service_areas"]=canonical(row.get("service_areas"),"region")
    profile={k:safe_text(row.get(k),blocked) for k in ('capabilities','industries','service_areas','ai_profile')}
    profile['region_groups']=region_groups(profile['service_areas'])
    profile['profile_updated_at']=row.get('updated_at')
    # No health score is treated as a real service level.
    if row.get('service_level'):profile['service_level']=safe_text(row['service_level'],blocked)
    profile['case_count']=conn.execute('SELECT count(*) FROM cases WHERE partner_id=?',(row['id'],)).fetchone()[0]
    profile['deliverable_count']=conn.execute('SELECT count(*) FROM deliverables d JOIN cases c ON c.id=d.case_id WHERE c.partner_id=?',(row['id'],)).fetchone()[0]
    profile['shared_evidence']=[]
    for case in conn.execute("SELECT id,1 FROM cases WHERE partner_id=? AND visible=1",(row['id'],)):
        try:
            data=resources.resolve_reference(conn,'case',case[0],case[1],'model')
            guard(data,blocked);profile['shared_evidence'].append(data)
        except (HTTPException,InvalidOutput):continue
    profile['basis_limited']=not bool(profile['ai_profile'] or profile['shared_evidence'])
    return profile


def terms(text):
    # Lexical search supplements formal tags; no new capability taxonomy or embeddings.
    tokens=re.findall(r'[a-zA-Z0-9_+.-]{2,}|[\u4e00-\u9fff]{2,}',text.lower())
    return set(tokens)|{t[i:i+2] for t in tokens if re.search('[\u4e00-\u9fff]',t) for i in range(len(t)-1)}


def candidates(conn,request,analysis):
    conn.begin_read()
    if isinstance(analysis,list):
        analysis={'priorities':[{'name':d.get('target_requirement',''),'capability_tag_id':d.get('capability_tag_id'),'search_terms':[]} for d in analysis]}
    focuses=analysis.get('priorities',[])
    tag_ids={f.get('capability_tag_id') for f in focuses if f.get('capability_tag_id')}
    query=terms(' '.join([request.get('development_direction') or request.get('development_goal',''),request.get('known_baseline','')]+[f.get('name','')+' '+' '.join(f.get('search_terms',[])) for f in focuses]))
    keywords={token for f in focuses for word in f.get('search_terms',[]) for token in terms(word)}
    allowed_types=set(analysis.get('resource_types',[]));excluded=set(analysis.get('excluded_levels',[]))
    if 'excluded_levels' not in analysis: excluded={ {'beginner':'basic','intermediate':'advanced'}.get(v,v) for v in analysis.get('excluded_difficulties',[]) }
    found=[];blocked=blocked_fragments(conn)
    for data in resources.model_references(conn):
        try:
            guard(data,blocked)
        except (HTTPException,InvalidOutput):continue
        if allowed_types and data['source_type'] not in allowed_types:continue
        if data.get('level') in excluded:continue
        haystack=' '.join(str(data.get(k,'')) for k in ('title','summary','methods','roles','zones','level','course_goals','outline','lab_goals','audience')).lower()
        lexical=sum(1 for word in query if word in haystack)
        mapped=tag_ids.intersection(data['capability_tag_ids'])
        # A generic audience word such as delivery must not pull an unrelated direction
        # into the candidate pool. Model-derived topic keywords remain a second path.
        topical=sum(1 for word in keywords if word in haystack)
        if keywords and not mapped and not topical:continue
        score=5*len(mapped)+3*topical+lexical
        if not score:continue
        found.append((score,data))
    return [d for _,d in sorted(found,key=lambda v:-v[0])[:100]]


def assemble(output,request,analysis,pool,actor):
    if output['target_partner_id']!=request['target_partner_id']:raise InvalidOutput('Invented partner')
    strong_guard(output);output=copy.deepcopy(output);allowed={key(r):r for r in pool}
    for stage in output['stages']:
        for item in stage['items']:
            source=allowed.get(key(item))
            if not source:raise InvalidOutput('Illegal candidate')
            # New generated advice does not assign formal tags to resources.
            # Keep the historical field and validate explicit manual/legacy values.
            item.setdefault('capability_tag_id', '')
            item.setdefault('item_id', life.uid())
            if item['capability_tag_id'] and item['capability_tag_id'] not in source['capability_tag_ids']:
                raise InvalidOutput(f"Illegal formal tag: resource={key(item)}, tag={item['capability_tag_id']!r}, allowed={source['capability_tag_ids']!r}")
            item.update(title=source['title'],conditions={k:source.get(k) for k in ('duration_minutes','level','roles','zones','lab_requirements')})
    if analysis.get('intent')!='explore' and not any(s['items'] for s in output['stages']):output['resource_gaps'].append('当前资源库未找到匹配项。')
    if analysis.get('basis_limited') and not output['limitations']:output['limitations'].append('当前提供的信息有限，本次建议主要依据已有信息和发展方向，未说明的能力仍待核实，需通过真实项目验证。')
    # All derived context is refreshed together when a new immutable Version is saved.
    output.update(advice_context(request,analysis))
    output.update(assumptions={},partner_goal_allowed=request.get('partner_goal_allowed',False),effective_request={k:v for k,v in request.items() if k not in ('raw_demand','_conversation')})
    return output


def prepare(request,user,*,plan_id=None,base=None,instruction='',cached=None):
    from . import development_context as context
    from .model_resolver import configuration_stamp
    from .scope_gate import MESSAGES
    from .task_failures import PublicTaskError
    config=model.configuration();stamp=configuration_stamp(config)
    frame=context.load(request,user,plan_id=plan_id,base=base,message=instruction)
    if cached and cached.get('stamp')==frame['stamp'] and cached.get('model')==stamp:
        return cached
    bind_context(stage='understanding')
    try:
        result=call(config,'analyze',frame['input'],Understanding,frame['blocked'])
        # A planning decision is not a candidate-backed answer. Never carry an eager draft into generation.
        if result['action']!='answer':result['answer']=''
        if result['target_partner_id']!=request['target_partner_id']:raise InvalidOutput('Invented partner')
        if not result['in_scope']:
            return {'analysis':result,'stamp':frame['stamp'],'model':stamp,'scope_message':MESSAGES['partner_development']}
        validate_analysis(result,request,{t['id'] for t in frame['tags']})
        if not result['effective_direction'].strip():raise InvalidOutput('Effective direction is empty')
        current=frame['input']['current']
        if current:
            # Reject a contradictory mutation for an explicit discussion-only question.
            # This is a validation guard, never a synthetic answer or a second model call.
            discussion=re.search(r'为什么|为何|有什么区别|如何比较|比较.{0,20}(?:实验|课程)|哪个.{0,20}更难|有没有更进阶',instruction)
            edit=re.search(r'调整|修改|重新规划|重规划|替换|换成|换掉|删除|去掉|不要|添加|增加|减少|改为|改成|展开建议|多给|少给|缩短|优先|放后|先做',instruction)
            if discussion and not edit and result['action']!='answer':raise InvalidOutput('Discussion cannot modify current advice')
            if result['action']=='generate':raise InvalidOutput('Existing advice requires explicit answer, patch or regenerate')
            available={i['item_id'] for i in current['resources']}
            if not set(result['edit_item_ids'])<=available:raise InvalidOutput('Unknown edit item')
            if any(current['answer'].count(span)!=1 for span in result['edit_answer_spans']):raise InvalidOutput('Ambiguous answer edit')
            if not {key(r) for r in result['references']}<={key(r) for r in current['resources']}:raise InvalidOutput('Invented reference')
            if result['action']=='patch' and (current['content_unavailable'] or not (result['edit_item_ids'] or result['edit_answer_spans'])):raise InvalidOutput('Local edit has no authorized target')
        elif result['action'] in ('patch','regenerate'):raise InvalidOutput('No current version to modify')
        if result['action']=='answer' and not result['answer'].strip():raise InvalidOutput('Answer is empty')
        result['basis_limited']=frame['profile'].get('basis_limited',True)
        result['profile_basis']=frame['profile']
        return {'analysis':result,'stamp':frame['stamp'],'model':stamp}
    except HTTPException:raise
    except Exception as error:raise PublicTaskError(error) from error


def merge_patch(old,patch,analysis,request,pool,actor):
    if patch['target_partner_id']!=request['target_partner_id']:raise InvalidOutput('Invented partner')
    strong_guard(patch)
    allowed=set(analysis['edit_item_ids']);seen=set();result=copy.deepcopy(old)
    for change in patch['changes']:
        target=change['item_id']
        if target not in allowed or target in seen:raise InvalidOutput('Patch outside requested items')
        seen.add(target)
        if change['action']=='remove' and change['items']:raise InvalidOutput('Remove cannot insert resources')
        if change['action']!='remove' and not change['items']:raise InvalidOutput('Replacement is empty')
        output={'target_partner_id':request['target_partner_id'],'stages':[{'title':'change','items':change['items']}], 'answer':'','limitations':[],'resource_gaps':[],'next_steps':[]}
        inserted=assemble(output,request,analysis,pool,actor)['stages'][0]['items'] if change['items'] else []
        for stage in result['stages']:
            for index,item in enumerate(stage['items']):
                if item['item_id']==target:
                    old_focuses=list(dict.fromkeys(i.get('focus','') for i in stage['items'] if i.get('focus')))
                    if change['action']=='add_after':stage['items'][index+1:index+1]=inserted
                    else:
                        if len(inserted)==1:inserted[0]['item_id']=target
                        stage['items'][index:index+1]=inserted
                    focuses=list(dict.fromkeys(i.get('focus','') for i in stage['items'] if i.get('focus')))
                    if focuses and focuses!=old_focuses:
                        stage['title']='、'.join(focuses)[:200]
                    break
    replacements={c['before']:c['after'] for c in patch['answer_changes']}
    if len(replacements)!=len(patch['answer_changes']) or not set(replacements)<=set(analysis['edit_answer_spans']):raise InvalidOutput('Patch outside requested answer')
    original=result.get('answer','')
    positions=sorted((original.find(before),before,after) for before,after in replacements.items())
    end=0;parts=[]
    for start,before,after in positions:
        if original.count(before)!=1 or start<end:raise InvalidOutput('Ambiguous answer patch')
        parts.extend([original[end:start],after]);end=start+len(before)
    result['answer']=''.join(parts)+original[end:]
    if len(result['answer'])>10000:raise InvalidOutput('Answer too large')
    if not patch['changes'] and not patch['answer_changes']:raise InvalidOutput('Empty patch')
    result.update(advice_context(request,analysis))
    for field in ('limitations','resource_gaps','next_steps'):
        result[field]=copy.deepcopy(patch[field])
    if analysis.get('basis_limited') and not result['limitations']:
        result['limitations']=['当前提供的信息有限，未说明的能力仍待核实，需通过真实项目验证。']
    result['effective_request']={k:v for k,v in request.items() if k in DevelopmentRequest.model_fields and k!='raw_demand'}
    result['revision_answer']=patch['answer']
    return result


def execute(run_id):
    with diagnostic_scope(request_id=run_id,run_id=run_id,stage='execution'):
        try:
            run=life.claim(run_id)
            if not run:return
            bind_context(task_id=run['plan_id'],request_id=run['submission_id'])
            with agent_settings.execution_scope(json.loads(run['input_snapshot']).get('agent_execution')):
                _execute_claimed(run_id,run)
        except Exception as error:record_error(error)


def _execute_claimed(run_id,run):
    from . import development_context as context
    from .model_resolver import pinned_configuration
    def expire_run():
        try:life.finish_failure(run_id,run['execution_token'],'run_timeout','interrupted')
        except Exception as error:record_error(error,'persistence')
    watchdog=Timer(run_timeout(),copy_context().run,args=(expire_run,));watchdog.daemon=True;watchdog.start()
    stage='understanding'
    try:
        snapshot=json.loads(run['input_snapshot']);request=snapshot['request']
        with get_db() as conn:actor=dict(conn.execute('SELECT id,role FROM users WHERE id=?',(run['owner_user_id'],)).fetchone())
        life.run_stage(run_id,run['execution_token'],'understanding','running')
        understanding=prepare(request,actor,plan_id=run['plan_id'],base=run['based_on_version_id'],instruction=snapshot['instruction'],cached=snapshot.get('understanding'))
        frame=context.load(request,actor,plan_id=run['plan_id'],base=run['based_on_version_id'],message=snapshot['instruction'])
        if frame['stamp']!=understanding['stamp']:raise InvalidOutput('Task context or permissions changed; retry required')
        pinned_configuration(understanding['model'])
        life.run_stage(run_id,run['execution_token'],'understanding','completed',understanding)
        if understanding.get('scope_message'):
            life.complete_scope(run_id,run['execution_token'],understanding['scope_message'])
            return
        if understanding['analysis']['action']=='answer' and run['based_on_version_id']:
            from .development_types import Revise
            life.save_answer(run['plan_id'],Revise(submission_id=run['submission_id'],based_on_version_id=run['based_on_version_id'],instruction=snapshot['instruction']),actor,request,understanding,run['request_hash'],run=run)
            return
        analysis=understanding['analysis']
        with get_db() as conn:
            conn.lock_writer()
            if analysis['action']!='answer':
                config=pinned_configuration(understanding['model'],conn)
                conn.execute('UPDATE development_runs SET model_config_id=? WHERE id=?',(config['id'],run_id))
            elif conn.execute('SELECT id FROM model_configs WHERE id=?',(understanding['model']['id'],)).fetchone():
                conn.execute('UPDATE development_runs SET model_config_id=? WHERE id=?',(understanding['model']['id'],run_id))
        request={**frame['request'],'development_direction':analysis['effective_direction'],'development_goal':analysis['effective_direction'],'constraints':analysis['effective_constraints'],'known_baseline':analysis.get('effective_baseline',frame['request'].get('known_baseline',''))}
        if snapshot['instruction']:request['partner_goal_allowed']=False
        stage='retrieval';bind_context(stage=stage)
        life.run_stage(run_id,run['execution_token'],'retrieval','running')
        with get_db() as conn:
            conn.begin_read()
            pool=[] if analysis['action']=='answer' else candidates(conn,request,analysis)
            deps=dependencies(conn,pool+frame['profile'].get('shared_evidence',[]))
        life.run_stage(run_id,run['execution_token'],'retrieval','completed')
        stage='generation';bind_context(stage=stage);life.ensure_execution(run_id,run['execution_token'])
        life.run_stage(run_id,run['execution_token'],'generation','running')
        if analysis['action']=='answer':
            output={'target_partner_id':request['target_partner_id'],'stages':[],'answer':analysis['answer'],'limitations':[],'resource_gaps':[],'next_steps':[]}
            payload=assemble(output,request,analysis,pool,run['owner_user_id'])
        else:
            config=pinned_configuration(understanding['model'])
            inputs={**frame['input'],'request':request_projection(request),'constraints':request['constraints'],'analysis':analysis,'understanding':analysis,'candidates':pool}
            if analysis['action']=='patch':
                patch=call(config,'patch',inputs,AdvicePatch,frame['blocked'])
                payload=merge_patch(frame['payload'],patch,analysis,request,pool,run['owner_user_id'])
                with get_db() as conn:deps=dependencies(conn,[i for s in payload['stages'] for i in s['items']]+frame['profile'].get('shared_evidence',[]))
            else:
                output=call(config,'plan',inputs,AdviceOutput,frame['blocked'])
                if not output['answer'].strip():raise InvalidOutput('Final answer is empty')
                payload=assemble(output,request,analysis,pool,run['owner_user_id'])
        stage='persistence';bind_context(stage=stage)
        fresh=context.load(snapshot['request'],actor,plan_id=run['plan_id'],base=run['based_on_version_id'],message=snapshot['instruction'])
        if fresh['stamp']!=understanding['stamp']:raise InvalidOutput('Task context or permissions changed during generation')
        def validate(conn,result,refs):
            frame_now=context.load(snapshot['request'],actor,plan_id=run['plan_id'],base=run['based_on_version_id'],message=snapshot['instruction'],connection=conn)
            if frame_now['stamp']!=understanding['stamp']:raise InvalidOutput('Context changed before persistence')
            validate_dependencies(conn,result,refs)
        life.complete(run_id,run['execution_token'],payload,deps,validate)
    except Exception as error:life.finish_failure(run_id,run['execution_token'],stage,error=error)
    finally:watchdog.cancel()
