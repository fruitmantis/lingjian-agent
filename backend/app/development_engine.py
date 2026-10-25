"""Minimal-context diagnosis and candidate-constrained plan assembly."""
import copy,json,re
from backend.business import development
from backend.business.development import (
    InvalidOutput, key, guard, parse, request_projection, validate_analysis, advice_context,
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
        resources.resolve_reference(conn,*key(ref),'model')
        kind='case' if ref['source_type']=='case' else 'resource'
        if kind=='case':
            from .case_content import visible_case
            stamp={'case_updated_at':visible_case(conn,ref['source_id'])['updated_at']}
        else:stamp={'authorization_epoch':resources.row_for(conn,kind,ref['source_id'])['authorization_epoch']}
        result.append({**{k:ref[k] for k in ('source_type','source_id','source_version')},**stamp})
    return result

def adopted_dependencies(output,sent,profile):
    selected={key(ref) for ref in output.get('used_refs',[])}
    selected.update(key(item) for stage in output.get('stages',[]) for item in stage['items'])
    lookup={key(ref):ref for ref in sent if ref.get('dependency_kind')!='profile_source'}
    if not selected<=lookup.keys():raise InvalidOutput('Illegal adopted resource')
    result=[copy.deepcopy(lookup[identity]) for identity in sorted(selected)]
    for chapter in output.get('used_profile_chapters',[]):
        if chapter not in profile.get('_chapter_sources',{}):raise InvalidOutput('Illegal adopted profile chapter')
        result.extend(copy.deepcopy(profile['_chapter_sources'][chapter]))
    return unique_dependencies(result)

def unique_dependencies(refs):
    return list({life.dump(ref):ref for ref in refs}.values())

def inherited_dependencies(old,payload,deps):
    if old.get('format_version')!=2 or old.get('legacy_dependencies'):return copy.deepcopy(deps)
    retained={key(item) for stage in payload['stages'] for item in stage['items']}
    retained.update(key(ref) for ref in old.get('used_refs',[]))
    return [copy.deepcopy(ref) for ref in deps if ref.get('dependency_kind')=='profile_source' or key(ref) in retained]


def validate_dependencies(conn,payload,deps):
    if payload['target_partner_id'] is not None:
        partner=conn.execute('SELECT status FROM partners WHERE id=?',(payload['target_partner_id'],)).fetchone()
        if not partner or partner[0]!='active':raise InvalidOutput('Target partner unavailable')
    tags={r[0] for r in conn.execute('SELECT id FROM capability_tags WHERE enabled=1')}
    if not {d['capability_tag_id'] for d in payload.get('diagnoses',[])}<=tags:raise InvalidOutput('Target capability unavailable')
    for ref in deps:
        if ref.get('dependency_kind')=='profile_source':
            from .profile_sources import profile_dependency_valid
            if not profile_dependency_valid(conn,ref):raise InvalidOutput('Profile source changed')
            continue
        resources.resolve_reference(conn,ref['source_type'],ref['source_id'],ref['source_version'],'model')
        kind='case' if ref['source_type']=='case' else 'resource'
        if kind=='case':
            from .case_content import visible_case
            if ref.get('case_updated_at')!=visible_case(conn,ref['source_id'])['updated_at']:raise InvalidOutput('Case changed')
        elif resources.row_for(conn,kind,ref['source_id'])['authorization_epoch']!=ref['authorization_epoch']:raise InvalidOutput('Permission changed')
    guard(payload,blocked_fragments(conn))
    for focus in payload.get('understanding',payload.get('analysis',{})).get('priorities',[]):
        if focus.get('capability_tag_id') and focus['capability_tag_id'] not in tags:focus['capability_tag_id']=None


def call(config,stage,payload,contract,blocked):
    from .ai_client import prepared_completion
    from .task_failures import MatchInputBudgetError
    for secret in blocked:register_secret(secret)
    guard(payload,blocked)
    selected={**config,'_input_char_limit':60000}
    def measure():
        messages,schema=development.request(stage,payload,contract)
        prepared_completion(selected,messages,schema)
        return messages,schema
    try:messages,schema=measure()
    except MatchInputBudgetError:
        original_chapters=copy.deepcopy(payload.get('profile',{}).get('chapters',[]))
        original_candidates=payload.get('candidates',[])
        payload.setdefault('profile',{})['chapters']=[]
        if 'candidates' in payload:payload['candidates']=[]
        measure()  # Required demand, current answer and complete exchanges must fit intact.
        try:
            payload['profile']['chapters']=original_chapters;measure()
        except MatchInputBudgetError:
            payload['profile']['chapters']=[]
            direction=payload.get('request',{}).get('development_direction','')
            query=terms(direction)
            paragraphs=[(sum(term in body.lower() for term in query),chapter['chapter'],index,body) for chapter in original_chapters for index,body in enumerate(re.split(r'\n\s*\n',chapter['body'])) if body.strip()]
            kept={}
            for _,number,index,body in sorted(paragraphs,key=lambda row:(-row[0],row[1],row[2])):
                trial={**kept,number:sorted(kept.get(number,[])+[(index,body)])}
                payload['profile']['chapters']=[{'chapter':n,'body':'\n\n'.join(text for _,text in blocks)} for n,blocks in sorted(trial.items())]
                try:measure()
                except MatchInputBudgetError:payload['profile']['chapters']=[{'chapter':n,'body':'\n\n'.join(text for _,text in blocks)} for n,blocks in sorted(kept.items())]
                else:kept=trial
        for candidate in original_candidates:
            payload['candidates'].append(candidate)
            try:measure()
            except MatchInputBudgetError:payload['candidates'].pop()
        messages,schema=measure()
    try:result=parse(model.completion(selected,messages,schema),contract,blocked)
    except Exception as error:
        error.model_call_failure=True
        raise
    chapters={entry['chapter'] for entry in payload.get('profile',{}).get('chapters',[])}
    refs=payload.get('candidates',[])+payload.get('profile',{}).get('shared_evidence',[])+(payload.get('current') or {}).get('resources',[])
    if not set(result.get('used_profile_chapters',[]))<=chapters:raise InvalidOutput('Unsent profile chapter')
    if not {key(ref) for ref in result.get('used_refs',[])}<={key(ref) for ref in refs}:raise InvalidOutput('Unsent resource reference')
    return result


def safe_text(value,blocked,limit=1600):
    if not value:return ''
    text=str(value)
    try:guard(text,blocked)
    except InvalidOutput:return ''
    return text if limit is None else text[:limit]


def profile_context(conn,request):
    """Current authorized business chapters; source identities stay private."""
    if request['target_partner_id'] is None or not request.get('model_input_allowed'):return {'chapters':[],'shared_evidence':[],'_chapter_sources':{}}
    row=conn.execute("SELECT * FROM partners WHERE id=? AND status='active'",(request['target_partner_id'],)).fetchone()
    if not row:raise InvalidOutput('Partner unavailable')
    from . import profile_sources,profile_report
    from .business_taxonomy import canonical,region_groups
    row=dict(row);blocked=blocked_fragments(conn)
    profile={k:safe_text(row.get(k),blocked,limit=None) for k in ('capabilities','industries','service_areas')}
    profile['industries']=canonical(profile['industries'],'industry');profile['service_areas']=canonical(profile['service_areas'],'region')
    profile['region_groups']=region_groups(profile['service_areas']);profile['chapters']=[];profile['_chapter_sources']={}
    report=profile_report.parse(profile_sources.assembled(conn,row['id'],analysis=True))
    meta=profile_sources.chapter_meta(row)
    for n,chapter in enumerate(report.chapters[:9],1):
        body=chapter.split('\n',1)[1].strip()
        if not body or body in (profile_report.MISSING,profile_sources.CHANGED):continue
        refs=[{'dependency_kind':'profile_source','partner_id':row['id'],**ref} for ref in meta.get(str(n),{}).get('used_sources',[])]
        if not refs or not all(profile_sources.profile_dependency_valid(conn,ref) for ref in refs):continue
        try:guard(body,blocked)
        except InvalidOutput:continue
        profile['chapters'].append({'chapter':n,'body':body});profile['_chapter_sources'][n]=refs
    profile['shared_evidence']=[]
    for case in conn.execute("SELECT id FROM cases WHERE partner_id=? AND visible=1",(row['id'],)):
        try:
            data=resources.resolve_reference(conn,'case',case[0],1,'model');guard(data,blocked);profile['shared_evidence'].append(data)
        except (HTTPException,InvalidOutput):continue
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
    output=copy.deepcopy(output);output['limitations']=[];allowed={key(r):r for r in pool}
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
    output.update(advice_context(request,analysis))
    output.update(format_version=2,partner_goal_allowed=request.get('partner_goal_allowed',False),effective_request={k:v for k,v in request.items() if k in DevelopmentRequest.model_fields and k!='raw_demand'})
    return output


def prepare(request,user,*,plan_id=None,base=None,instruction='',cached=None):
    from . import development_context as context
    from .model_resolver import configuration_stamp
    from .scope_gate import MESSAGES
    from .task_failures import PublicTaskError
    config=model.configuration();stamp=configuration_stamp(config)
    frame=context.load(request,user,plan_id=plan_id,base=base,message=instruction)
    if cached and cached.get('format_version')==2 and cached.get('stamp')==frame['stamp'] and cached.get('model')==stamp:
        return cached
    bind_context(stage='understanding')
    try:
        sent_refs=frame['input']['profile'].get('shared_evidence',[])+(frame['input']['current'] or {}).get('resources',[])
        with get_db() as conn:sent_dependencies=dependencies(conn,sent_refs)
        result=call(config,'analyze',frame['input'],Understanding,frame['blocked'])
        adopted=adopted_dependencies(result,sent_dependencies,frame['profile'])
        # A planning decision is not a candidate-backed answer. Never carry an eager draft into generation.
        if result['action']!='answer':result['answer']=''
        if result['target_partner_id']!=request['target_partner_id']:raise InvalidOutput('Invented partner')
        if not result['in_scope']:
            return {'format_version':2,'analysis':result,'stamp':frame['stamp'],'request_stamp':frame['request_stamp'],'model':stamp,'scope_message':MESSAGES['partner_development']}
        validate_analysis(result,request,{t['id'] for t in frame['tags']})
        if not result['effective_direction'].strip():raise InvalidOutput('Effective direction is empty')
        current=frame['input']['current']
        if current:
            if result['action']=='generate':raise InvalidOutput('Existing advice requires explicit answer, patch or regenerate')
            available={i['item_id'] for i in current['resources']}
            if not set(result['edit_item_ids'])<=available:raise InvalidOutput('Unknown edit item')
            if any(current['answer'].count(span)!=1 for span in result['edit_answer_spans']):raise InvalidOutput('Ambiguous answer edit')
            if result['action']=='patch' and (current['content_unavailable'] or not (result['edit_item_ids'] or result['edit_answer_spans'])):raise InvalidOutput('Local edit has no authorized target')
        elif result['action'] in ('patch','regenerate'):raise InvalidOutput('No current version to modify')
        if result['action']=='answer' and not result['answer'].strip():raise InvalidOutput('Answer is empty')
        return {'format_version':2,'analysis':result,'stamp':frame['stamp'],'request_stamp':frame['request_stamp'],'dependencies':adopted,'model':stamp}
    except HTTPException:raise
    except Exception as error:raise PublicTaskError(error) from error


def merge_patch(old,patch,analysis,request,pool,actor):
    if patch['target_partner_id']!=request['target_partner_id']:raise InvalidOutput('Invented partner')
    allowed=set(analysis['edit_item_ids']);groups={};result=copy.deepcopy(old)
    anchors={item['item_id'] for stage in old['stages'] for item in stage['items']}
    for change in patch['changes']:
        target=change['item_id'];action=change['action']
        if target not in allowed or target not in anchors:raise InvalidOutput('Patch outside requested items')
        group=groups.setdefault(target,{})
        if action in group or (group and (action=='remove' or 'remove' in group)):
            raise InvalidOutput('Conflicting changes for original item')
        if action=='remove' and change['items']:raise InvalidOutput('Remove cannot insert resources')
        if action!='remove' and not change['items']:raise InvalidOutput('Replacement is empty')
        group[action]=change
    for target,group in groups.items():
        # Both actions address the original anchor, independent of wire order.
        inserted={}
        for action,change in group.items():
            output={'target_partner_id':request['target_partner_id'],'stages':[{'title':'change','items':change['items']}], 'answer':'','limitations':[],'resource_gaps':[],'next_steps':[]}
            inserted[action]=assemble(output,request,analysis,pool,actor)['stages'][0]['items'] if change['items'] else []
        for stage in result['stages']:
            for index,item in enumerate(stage['items']):
                if item['item_id']==target:
                    old_focuses=list(dict.fromkeys(i.get('focus','') for i in stage['items'] if i.get('focus')))
                    if 'replace' in group:
                        replacement=inserted['replace']
                        if len(replacement)==1 or 'add_after' in group:replacement[0]['item_id']=target
                        stage['items'][index:index+1]=replacement+inserted.get('add_after',[])
                    elif 'remove' in group:stage['items'][index:index+1]=[]
                    else:stage['items'][index+1:index+1]=inserted['add_after']
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
    for field in ('resource_gaps','next_steps'):
        if field in patch:result[field]=copy.deepcopy(patch[field])
    result['effective_request']={k:v for k,v in request.items() if k in DevelopmentRequest.model_fields and k!='raw_demand'}
    result['partner_goal_allowed']=request.get('partner_goal_allowed',False)
    result['revision_answer']=patch['answer']
    result['format_version']=2
    if old.get('format_version')!=2 or old.get('legacy_dependencies'):result['legacy_dependencies']=True
    result['used_refs']=list({key(ref):ref for ref in old.get('used_refs',[])+patch['used_refs']}.values())
    result['used_profile_chapters']=list(dict.fromkeys(old.get('used_profile_chapters',[])+patch['used_profile_chapters']))
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
        if frame['request_stamp']!=understanding['request_stamp']:raise InvalidOutput('Task context or permissions changed; retry required')
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
        request={**frame['request'],'constraints':analysis['effective_constraints'],'known_baseline':analysis.get('effective_baseline',frame['request'].get('known_baseline',''))}
        if snapshot['instruction']:request['partner_goal_allowed']=False
        stage='retrieval';bind_context(stage=stage)
        life.run_stage(run_id,run['execution_token'],'retrieval','running')
        with get_db() as conn:
            conn.begin_read()
            pool=[] if analysis['action']=='answer' else candidates(conn,{**request,'development_direction':analysis['effective_direction']},analysis)
            sent_dependencies=dependencies(conn,pool+frame['profile'].get('shared_evidence',[])+(frame['input']['current'] or {}).get('resources',[]))
        life.run_stage(run_id,run['execution_token'],'retrieval','completed')
        stage='generation';bind_context(stage=stage);life.ensure_execution(run_id,run['execution_token'])
        life.run_stage(run_id,run['execution_token'],'generation','running')
        if analysis['action']=='answer':
            output={'target_partner_id':request['target_partner_id'],'stages':[],'answer':analysis['answer'],'limitations':[],'resource_gaps':[],'next_steps':[],'used_refs':analysis['used_refs'],'used_profile_chapters':analysis['used_profile_chapters']}
            payload=assemble(output,request,analysis,pool,run['owner_user_id'])
            deps=understanding['dependencies']
        else:
            config=pinned_configuration(understanding['model'])
            inputs={**frame['input'],'request':request_projection(request),'constraints':request['constraints'],'understanding':{k:v for k,v in analysis.items() if not k.startswith('_') and k not in ('profile_basis','basis_limited','effective_baseline','effective_constraints','target_partner_id','answer','used_refs','used_profile_chapters')},'candidates':pool}
            if analysis['action']=='patch':
                # Current items already carry their complete authorized catalog data.
                current_keys={key(ref) for ref in (inputs.get('current') or {}).get('resources',[])}
                inputs['candidates']=[ref for ref in pool if key(ref) not in current_keys]
                patch=call(config,'patch',inputs,AdvicePatch,frame['blocked'])
                actual_pool=inputs['candidates']+(inputs.get('current') or {}).get('resources',[])
                payload=merge_patch(frame['payload'],patch,analysis,request,actual_pool,run['owner_user_id'])
                changes={'stages':[{'items':change['items']} for change in patch['changes']], 'used_refs':patch['used_refs'],'used_profile_chapters':patch['used_profile_chapters']}
                deps=unique_dependencies(inherited_dependencies(frame['payload'],payload,frame['dependencies'])+understanding['dependencies']+adopted_dependencies(changes,sent_dependencies,frame['profile']))
            else:
                output=call(config,'plan',inputs,AdviceOutput,frame['blocked'])
                if not output['answer'].strip():raise InvalidOutput('Final answer is empty')
                payload=assemble(output,request,analysis,inputs['candidates'],run['owner_user_id'])
                deps=unique_dependencies(understanding['dependencies']+adopted_dependencies(payload,sent_dependencies,frame['profile']))
        stage='persistence';bind_context(stage=stage)
        fresh=context.load(snapshot['request'],actor,plan_id=run['plan_id'],base=run['based_on_version_id'],message=snapshot['instruction'])
        if fresh['request_stamp']!=understanding['request_stamp']:raise InvalidOutput('Task context or permissions changed during generation')
        def validate(conn,result,refs):
            frame_now=context.load(snapshot['request'],actor,plan_id=run['plan_id'],base=run['based_on_version_id'],message=snapshot['instruction'],connection=conn)
            if frame_now['request_stamp']!=understanding['request_stamp']:raise InvalidOutput('Context changed before persistence')
            validate_dependencies(conn,result,refs)
        life.complete(run_id,run['execution_token'],payload,deps,validate)
    except Exception as error:life.finish_failure(run_id,run['execution_token'],stage,error=error)
    finally:watchdog.cancel()
