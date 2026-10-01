"""Authenticated workspace catalog; published snapshots are the only resource source."""
import json
import uuid
from fastapi import HTTPException
from . import enablement as service
from .business_taxonomy import project_partner
from .database import get_db

# Mirror the reference gate when selecting/counting candidates; resolve_reference remains
# the final projection/authorization gate in the same read transaction.
POOL = """WITH candidates AS (
 SELECT 'resource' kind,(v.payload_json::jsonb #>> '{resource_type}') source_type,
 r.id source_id,r.published_version source_version,v.payload_json,v.published_at,
 (v.payload_json::jsonb #>> '{title}') title,(v.payload_json::jsonb #>> '{summary}') summary,
 NULL contributor_id,NULL category_id
 FROM enablement_resources r JOIN enablement_resource_versions v ON v.source_id=r.id AND v.version=r.published_version
 WHERE r.status='published' AND r.system_visible=1 AND r.authorization_epoch=v.authorization_epoch
 AND CAST((v.payload_json::jsonb #>> '{_permissions,system_visible}') AS TEXT) IN ('1','true')
 UNION ALL
 SELECT 'case','case',c.id,1,NULL,c.updated_at,c.title,c.description,c.partner_id,c.category_id
 FROM cases c JOIN partners p ON p.id=c.partner_id WHERE c.visible=1 AND p.status='active'
), visible AS (SELECT * FROM candidates) """


def public_detail(conn, source_type, source_id, version=None):
    if source_type=='case':
        from .case_content import projection
        return projection(conn,source_id)
    try:
        head=service.row_for(conn,'resource',source_id)
        current=head['published_version']
        data=service.resolve_reference(conn,source_type,source_id,version if version is not None else current,'system')
    except HTTPException as error:
        raise HTTPException(404,'资源不存在或当前不可用，请重新选择') from error
    snapshot=conn.execute('SELECT published_at FROM enablement_resource_versions WHERE source_id=? AND version=?',(source_id,current)).fetchone()
    data.update(status='published',published_at=snapshot['published_at'])
    data['capabilities']=[dict(conn.execute('SELECT id,name FROM capability_tags WHERE id=?',(tag,)).fetchone()) for tag in data['capability_tag_ids']]
    return data


def catalog(source_type=None, q=None, capability_tag_id=None, contributor_id=None, status='published', page=1, page_size=12, **filters):
    conditions=[]; params=[]
    if status != 'published': conditions.append('1=0')
    if source_type: conditions.append('source_type=?');params.append(source_type)
    if q:
        fields=('course_goals','outline','lab_goals','audience')
        conditions.append("(strpos(lower(COALESCE(title,'')),lower(?))>0 OR strpos(lower(COALESCE(summary,'')),lower(?))>0 OR "+' OR '.join("strpos(lower(COALESCE((payload_json::jsonb #>> '{"+field+"}'),'')),lower(?))>0" for field in fields)+')')
        params.extend([q.strip()]*(len(fields)+2))
    if capability_tag_id:
        conditions.append("EXISTS (SELECT 1 FROM jsonb_array_elements_text(payload_json::jsonb #> '{capability_tag_ids}') WHERE value=?)");params.append(capability_tag_id)
    if contributor_id: conditions.append("contributor_id=?");params.append(contributor_id)
    if filters.get('category_id'):
        conditions.append('category_id=?');params.append(filters['category_id'])
    if filters.get('category_group'):
        from .material_contract import CONTRACT
        ids=[c['id'] for g in CONTRACT['categories'] if g['id']==filters['category_group'] for c in g['children']]
        if ids:
            conditions.append('category_id IN ('+','.join('?' for _ in ids)+')');params.extend(ids)
        else: conditions.append('1=0')
    for field in ('role_ids', 'zone_ids'):
        value = filters.get(field[:-1])
        if value:
            conditions.append("EXISTS (SELECT 1 FROM jsonb_array_elements_text(payload_json::jsonb #> '{"+field+"}') WHERE value=?)")
            params.append(value)
    if filters.get('level'):
        conditions.append("COALESCE((payload_json::jsonb #>> '{level}'), CASE (payload_json::jsonb #>> '{difficulty}') WHEN 'beginner' THEN 'basic' WHEN 'intermediate' THEN 'advanced' WHEN 'advanced' THEN 'advanced' END)=?")
        params.append(filters['level'])
    where=' WHERE '+' AND '.join(conditions) if conditions else ''
    with get_db() as conn:
        conn.begin_read()
        total=conn.execute(POOL+'SELECT count(*) FROM visible'+where,params).fetchone()[0]
        rows=conn.execute(POOL+'SELECT source_type,source_id,source_version FROM visible'+where+
                          ' ORDER BY published_at DESC,source_type,source_id LIMIT ? OFFSET ?',[*params,page_size,(page-1)*page_size]).fetchall()
        items=[public_detail(conn,r['source_type'],r['source_id'],r['source_version']) for r in rows]
        return {'items':items,'total':total,'page':page,'page_size':page_size}


def filter_options():
    from .material_contract import CONTRACT
    from .resource_categories import read
    with get_db() as conn:
        categories=read(conn)
        return {'roles':[r for r in categories if r['kind']=='role'], 'zones':[r for r in categories if r['kind']=='zone'], 'case_categories':CONTRACT['categories']}


def redirect(source_type,source_id,version,actor):
    with get_db() as conn:
        conn.lock_writer()
        resource=public_detail(conn,source_type,source_id,version)
        if source_type=='case': return {'url':f'/resources/case/{source_id}'}
        # Check again under the current URL validator, including legacy published snapshots.
        try:
            url=service.ResourceMetadata.check_url(resource['source_url'])
        except ValueError as error:
            raise HTTPException(409,'来源链接需管理员重新核验') from error
        event_id=str(uuid.uuid4())
        conn.execute('INSERT INTO resource_redirect_events VALUES (?,?,?,?,?,?,?)',
                     (event_id,actor,source_type,source_id,version,'redirect_initiated',service.now()))
        return {'event_id':event_id,'event_type':'redirect_initiated','event_label':'发起跳转','url':url}


def context(user,partner_id=None,task_id=None,case_id=None,case_version=None):
    with get_db() as conn:
        conn.begin_read()
        result={'partner':None,'evidence':[],'project':None,'shared_case':None}
        if task_id:
            task=conn.execute('SELECT id,owner_user_id,requirement,recommendations_json FROM match_records WHERE id=?',(task_id,)).fetchone()
            if not task or (user['role']!='admin' and task['owner_user_id']!=user['id']):
                raise HTTPException(404,'来源任务不存在或无权访问')
            recommendation=next((r for r in json.loads(task['recommendations_json']) if r.get('partnerId')==partner_id),None)
            if not partner_id or recommendation is None: raise HTTPException(404,'来源任务中无此推荐伙伴')
            result['project']={'task_id':task_id,'requirement':task['requirement'],'risk_notes':recommendation.get('riskNotes',''),
                               'risk_status':'待能力发展流程复核'}
        if case_id:
            result['shared_case']=public_detail(conn,'case',case_id,case_version)
        elif case_version is not None:
            raise HTTPException(422,'案例版本需要案例标识')
        if partner_id:
            partner=conn.execute("SELECT id,name,intro,capabilities,industries,service_areas,ai_profile FROM partners WHERE id=? AND status='active'",(partner_id,)).fetchone()
            if not partner: raise HTTPException(404,'伙伴不存在或当前不可用')
            result['partner']=project_partner(dict(partner))
            if user['role']!='admin': result['partner']['ai_profile']=None
            # Internal evidence references only: no upload paths, extracted content or shared-case fallback.
            result['evidence']=[{'source_type':'internal_case','source_id':r['id'],'title':r['title']} for r in conn.execute('SELECT id,title FROM cases WHERE partner_id=? AND visible=1',(partner_id,))]
            result['evidence'] += [{'source_type':'internal_deliverable','source_id':r['id'],'title':r['filename']} for r in conn.execute('SELECT d.id,d.filename FROM deliverables d JOIN cases c ON c.id=d.case_id WHERE c.partner_id=? AND c.visible=1',(partner_id,))]
        return result
