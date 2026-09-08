"""Authenticated workspace catalog; published snapshots are the only resource source."""
import json
import uuid
from fastapi import HTTPException
from . import enablement as service
from .business_taxonomy import project_partner
from .database import get_db

# Mirror the reference gate when selecting/counting candidates; resolve_reference remains
# the final projection/authorization gate in the same read transaction.
POOL = '''WITH candidates AS (
 SELECT 'resource' kind, json_extract(v.payload_json,'$.resource_type') source_type,
 r.id source_id,r.published_version source_version,v.payload_json,v.published_at
 FROM enablement_resources r JOIN enablement_resource_versions v
 ON v.source_id=r.id AND v.version=r.published_version
 WHERE r.status='published' AND r.system_visible=1 AND r.authorization_epoch=v.authorization_epoch
 UNION ALL
 SELECT 'case','case',s.case_id,s.published_version,v.payload_json,v.published_at
 FROM case_share_configs s JOIN case_share_versions v ON v.source_id=s.case_id AND v.version=s.published_version
 JOIN cases c ON c.id=s.case_id JOIN partners p ON p.id=c.partner_id
 WHERE s.status='published' AND s.system_visible=1 AND s.authorization_epoch=v.authorization_epoch
 AND p.status='active' AND p.id=json_extract(v.payload_json,'$.contributor_id')
), visible AS (
 SELECT * FROM candidates WHERE json_extract(payload_json,'$._permissions.system_visible')=1
 AND json_array_length(payload_json,'$.capability_tag_ids')>0
 AND NOT EXISTS (SELECT 1 FROM json_each(payload_json,'$.capability_tag_ids') j
 LEFT JOIN capability_tags t ON t.id=j.value AND t.enabled=1 WHERE t.id IS NULL)
) '''
FILTER_FIELDS = ('audience','product_direction','difficulty','language','site','cost','account_requirement','environment_requirement','prerequisites')


def public_detail(conn, source_type, source_id, version=None):
    kind = 'case' if source_type == 'case' else 'resource'
    try:
        head = service.row_for(conn,kind,source_id)
        current = head['published_version']
        data = service.resolve_reference(conn,source_type,source_id,version if version is not None else current,'system')
    except HTTPException as error:
        raise HTTPException(404,'资源不存在或当前不可用，请重新选择') from error
    _, versions, _ = service.TABLES[kind]
    snapshot = conn.execute(f'SELECT * FROM {versions} WHERE source_id=? AND version=?',(source_id,current)).fetchone()
    review = conn.execute('''SELECT r.reviewed_at,r.link_status,r.content_checked,r.authorization_checked,
        COALESCE(NULLIF(u.display_name,''),'未记录') AS reviewer_name
        FROM enablement_reviews r JOIN users u ON u.id=r.reviewer_id
        WHERE r.source_kind=? AND r.source_id=? AND r.revision=?
        ORDER BY r.reviewed_at DESC,r.id DESC LIMIT 1''',(kind,source_id,snapshot['reviewed_revision'])).fetchone()
    data.update(status='published',availability='available' if review and review['link_status']=='available' else 'unknown',
                published_at=snapshot['published_at'],review=dict(review) if review else None)
    data['capabilities'] = [dict(conn.execute('SELECT id,name FROM capability_tags WHERE id=?',(tag,)).fetchone()) for tag in data['capability_tag_ids']]
    if kind == 'case':
        data['contributor_id'] = json.loads(snapshot['payload_json'])['contributor_id']
    return data


def catalog(source_type=None, q=None, capability_tag_id=None, contributor_id=None, status='published', page=1, page_size=12, **filters):
    conditions=[]; params=[]
    if status != 'published': conditions.append('0')
    if source_type: conditions.append('source_type=?');params.append(source_type)
    if q:
        fields=('title','summary','target_capability','methods','product_direction','audience')
        conditions.append('('+' OR '.join("instr(lower(COALESCE(json_extract(payload_json,'$."+field+"'),'')),lower(?))>0" for field in fields)+')')
        params.extend([q.strip()]*len(fields))
    if capability_tag_id:
        conditions.append("EXISTS (SELECT 1 FROM json_each(payload_json,'$.capability_tag_ids') WHERE value=?)");params.append(capability_tag_id)
    if contributor_id: conditions.append("json_extract(payload_json,'$.contributor_id')=?");params.append(contributor_id)
    for field in FILTER_FIELDS:
        value=filters.get(field)
        if value:
            unknown='unknown' if field in ('difficulty','cost') else '未知'
            conditions.append(f"COALESCE(NULLIF(json_extract(payload_json,'$.{field}'),''),?)=?")
            params.extend([unknown,value])
    where=' WHERE '+' AND '.join(conditions) if conditions else ''
    with get_db() as conn:
        conn.execute('BEGIN')
        total=conn.execute(POOL+'SELECT count(*) FROM visible'+where,params).fetchone()[0]
        rows=conn.execute(POOL+'SELECT source_type,source_id,source_version FROM visible'+where+
                          ' ORDER BY published_at DESC,source_type,source_id LIMIT ? OFFSET ?',[*params,page_size,(page-1)*page_size]).fetchall()
        items=[public_detail(conn,r['source_type'],r['source_id'],r['source_version']) for r in rows]
        return {'items':items,'total':total,'page':page,'page_size':page_size}


def filter_options():
    with get_db() as conn:
        conn.execute('BEGIN')
        data=[json.loads(r[0]) for r in conn.execute(POOL+'SELECT payload_json FROM visible')]
        tag_ids={tag for row in data for tag in row['capability_tag_ids']}
        tags=[dict(r) for r in conn.execute('SELECT id,name FROM capability_tags WHERE enabled=1 ORDER BY name') if r['id'] in tag_ids]
        return {'capabilities':tags, **{f:sorted({str(row.get(f) or ('unknown' if f in ('difficulty','cost') else '未知')) for row in data}) for f in FILTER_FIELDS}}


def redirect(source_type,source_id,version,actor):
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        resource=public_detail(conn,source_type,source_id,version)
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
        conn.execute('BEGIN')
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
            # Internal evidence references only: no upload paths, extracted content or shared-case fallback.
            result['evidence']=[{'source_type':'internal_case','source_id':r['id'],'title':r['title']} for r in conn.execute('SELECT id,title FROM cases WHERE partner_id=?',(partner_id,))]
            result['evidence'] += [{'source_type':'internal_deliverable','source_id':r['id'],'title':r['filename']} for r in conn.execute('SELECT d.id,d.filename FROM deliverables d JOIN cases c ON c.id=d.case_id WHERE c.partner_id=?',(partner_id,))]
        return result
