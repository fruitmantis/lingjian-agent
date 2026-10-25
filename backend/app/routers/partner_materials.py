"""One admin catalogue over existing cases and unclassified partner documents."""
from typing import Literal
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from ..auth import require_admin, record_audit
from ..database import get_db
from ..material_contract import CONTRACT, check_category
from ..models import CaseCreate, CaseOut
from ..case_content import visible_case
from .. import material_files as files
from .cases import _process_profile

router = APIRouter(prefix='/admin/partner-materials', tags=['partner-materials'], dependencies=[Depends(require_admin)])

# Keep the canonical JSON bytes identical to profile_sources.stamp. PostgreSQL's
# built-in SHA256 checks current contributions before the catalogue is counted/paged.
_SOURCE_FINGERPRINT_SQL = """
encode(sha256(convert_to(
    '{"created_at": ' || COALESCE(to_json(n.created_at)::text, 'null') ||
    ', "file_path": ' || COALESCE(to_json(n.file_path)::text, 'null') ||
    ', "id": ' || to_json(n.id)::text ||
    ', "kind": ' || to_json(n.kind)::text ||
    ', "partner_id": ' || to_json(n.partner_id)::text ||
    ', "processing_status": ' || to_json(n.processing_status)::text ||
    ', "text": ' || to_json(n.native_text)::text || '}', 'UTF8')), 'hex')
"""

CATALOGUE = f"""
WITH native_files AS (
    SELECT 'attachment' AS kind, d.id, c.partner_id, d.case_id, d.file_path,
        d.processing_status, d.preview_error, d.created_at, d.processed_at,
        COALESCE(d.extracted_text,'') AS native_text
    FROM deliverables d JOIN cases c ON c.id=d.case_id
    UNION ALL
    SELECT 'document', d.id, d.partner_id, NULL, d.file_path,
        d.processing_status, d.preview_error, d.created_at, d.processed_at,
        COALESCE(d.extracted_text,'')
    FROM partner_documents d WHERE COALESCE(d.doc_category,'')!='profile_import'
), file_states AS (
    SELECT n.*,
        CASE WHEN n.processing_status='processing'
                  OR (n.processing_status='ready' AND COALESCE(s.state,'pending') IN ('pending','processing'))
             THEN 'processing'
             WHEN n.processing_status='failed' OR COALESCE(n.preview_error,'') <> ''
                  OR (n.processing_status='ready' AND s.state='failed') THEN 'failed'
             WHEN n.processing_status='empty'
                  OR (n.processing_status='ready' AND s.state='empty') THEN 'empty'
             ELSE n.processing_status END AS effective_status
    FROM native_files n LEFT JOIN partner_profile_sources s
        ON n.processing_status='ready' AND s.partner_id=n.partner_id
        AND s.source_kind=n.kind AND s.source_id=n.id
        AND s.source_fingerprint={_SOURCE_FINGERPRINT_SQL}
), attachment_stats AS (
    SELECT case_id, COUNT(*) AS file_count,
        MAX(COALESCE(processed_at, created_at)) AS file_updated_at,
        MAX(CASE WHEN effective_status='processing' THEN 1 ELSE 0 END) AS processing,
        MAX(CASE WHEN effective_status='failed' THEN 1 ELSE 0 END) AS failed,
        MAX(CASE WHEN effective_status='empty' THEN 1 ELSE 0 END) AS empty
    FROM file_states WHERE kind='attachment' GROUP BY case_id
), entries AS (
    SELECT 'case' AS kind, c.id, c.partner_id, c.title, c.description, c.category_id,
        c.visible, COALESCE(s.file_count,0) AS file_count,
        CASE WHEN s.processing=1 THEN 'processing' WHEN s.failed=1 THEN 'failed'
             WHEN s.empty=1 THEN 'empty' WHEN s.file_count>0 THEN 'ready' ELSE 'no_files' END AS processing_status,
        CASE WHEN s.file_updated_at>COALESCE(c.updated_at,c.created_at) THEN s.file_updated_at
             ELSE COALESCE(c.updated_at,c.created_at) END AS updated_at
    FROM cases c LEFT JOIN attachment_stats s ON s.case_id=c.id
    UNION ALL
    SELECT 'document', n.id, n.partner_id, d.filename, NULL, NULL, 0, 1,
        n.effective_status, COALESCE(n.processed_at,n.created_at)
    FROM file_states n JOIN partner_documents d ON d.id=n.id WHERE n.kind='document'
), materials AS (
    SELECT e.*,p.name AS partner_name,
        CASE WHEN p.materials_revision!=p.profile_materials_revision THEN 1 ELSE 0 END AS profile_needs_update
    FROM entries e JOIN partners p ON p.id=e.partner_id
)
"""

@router.get('')
def catalogue(partner_id: str | None = None, category_group: str | None = None,
              category_id: str | None = None, q: str = Query('', max_length=200),
              status: Literal['failed'] | None = None,
              page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=60)):
    where, args = [], []
    if partner_id:
        where.append('partner_id=?'); args.append(partner_id)
    if category_id:
        check_category(category_id)
        where.append('category_id=?'); args.append(category_id)
    if category_group:
        if category_group == 'unclassified':
            where.append('category_id IS NULL')
        else:
            group = next((g for g in CONTRACT['categories'] if g['id']==category_group), None)
            if not group: raise HTTPException(422, '请选择有效的一级分类')
            ids = [c['id'] for c in group['children']]
            where.append('category_id IN ('+','.join('?' for _ in ids)+')'); args.extend(ids)
    if q.strip():
        # Search is a literal substring, including user-entered SQL wildcard characters.
        needle=q.strip().lower().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        where.append("LOWER(title) ILIKE ? ESCAPE '\\'"); args.append('%'+needle+'%')
    if status:
        where.append('processing_status=?'); args.append(status)
    clause=' WHERE '+' AND '.join(where) if where else ''
    with get_db() as conn:
        partners=[dict(r) for r in conn.execute('SELECT id,name FROM partners ORDER BY name,id')]
        if partner_id and not any(p['id']==partner_id for p in partners): raise HTTPException(404,'伙伴不存在')
        total=conn.execute(CATALOGUE+'SELECT COUNT(*) FROM materials'+clause, args).fetchone()[0]
        rows=conn.execute(CATALOGUE+'SELECT * FROM materials'+clause+" ORDER BY CASE WHEN category_id ILIKE 'marketing-%' THEN 0 WHEN category_id ILIKE 'delivery-%' THEN 1 WHEN category_id ILIKE 'technical-%' THEN 2 ELSE 3 END, updated_at DESC,id LIMIT ? OFFSET ?", [*args,page_size,(page-1)*page_size]).fetchall()
        items=[{**dict(r),'visible':bool(r['visible']),'profile_needs_update':bool(r['profile_needs_update'])} for r in rows]
    return {'items':items,'total':total,'partners':partners}

@router.put('/documents/{document_id}/classify', response_model=CaseOut)
def classify_document(document_id: str, payload: CaseCreate, background_tasks: BackgroundTasks, actor=Depends(require_admin)):
    """Admin explicitly categorizes a legacy file; keep its ID, bytes and cached output."""
    check_category(payload.category_id)
    with get_db() as conn:
        conn.lock_writer()
        old=conn.execute('SELECT * FROM partner_documents WHERE id=?',(document_id,)).fetchone()
        if not old: raise HTTPException(404,'资料不存在')
        if old['doc_category']=='profile_import': raise HTTPException(409,'画像原件不属于案例资料')
        if old['processing_status']=='processing': raise HTTPException(409,'文件正在处理中，请稍后归类')
        if not conn.execute('SELECT id FROM partners WHERE id=?',(payload.partner_id,)).fetchone(): raise HTTPException(404,'伙伴不存在')
        contribution=conn.execute("SELECT * FROM partner_profile_sources WHERE partner_id=? AND source_kind='document' AND source_id=?",(old['partner_id'],document_id)).fetchone()
        if contribution and contribution['state']=='processing':
            raise HTTPException(409,'资料画像正在处理中，请稍后归类')
        row=conn.execute("DELETE FROM partner_documents WHERE id=? AND processing_status!='processing' RETURNING *",(document_id,)).fetchone()
        if not row: raise HTTPException(409,'资料已变化，请刷新后重试')
        stamp=files.now()
        conn.execute('INSERT INTO cases (id,partner_id,title,description,category_id,visible,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                     (document_id,payload.partner_id,payload.title,payload.description,payload.category_id,int(payload.visible),row['created_at'],stamp))
        columns=('id','filename','file_path','file_type','created_at','extracted_text','processing_status','processing_error','preview_path','preview_error','processed_at')
        conn.execute('INSERT INTO deliverables (case_id,'+','.join(columns)+') VALUES ('+','.join('?' for _ in range(len(columns)+1))+')',
                     (document_id,*(row[c] for c in columns)))
        for pid in {old['partner_id'],payload.partner_id}: files.changed(conn,pid)
        from ..profile_sources import source as get_source,put,rebuild,stamp as source_stamp
        original_source={**dict(old),'kind':'document','text':old['extracted_text'] or ''}
        transferred=(contribution and contribution['state']=='ready'
                     and contribution['source_fingerprint']==source_stamp(original_source))
        if transferred:
            import json
            source=get_source(conn,payload.partner_id,'attachment',document_id)
            put(conn,source,'ready',json.loads(contribution['sections_json']),contribution['error'])
            rebuild(conn,payload.partner_id)
        needs_processing=not transferred and row['processing_status']=='ready'
        fingerprint=source_stamp(get_source(conn,payload.partner_id,'attachment',document_id))
        record_audit(conn,'partner_document_classified',actor_user_id=actor['id'],summary={'document_id':document_id,'case_id':document_id})
        result=visible_case(conn,document_id,True)
    # No callback is registered until the conversion transaction has committed.
    # Existing processing claims/fingerprints deduplicate overlapping callbacks.
    if needs_processing:
        background_tasks.add_task(_process_profile,payload.partner_id,'attachment',document_id,fingerprint)
    return result
