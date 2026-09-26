"""One admin catalogue over existing cases and unclassified partner documents."""
from fastapi import APIRouter, Depends, HTTPException, Query
from ..auth import require_admin, record_audit
from ..database import get_db
from ..material_contract import CONTRACT, check_category
from ..models import CaseCreate, CaseOut
from ..case_content import visible_case
from .. import material_files as files

router = APIRouter(prefix='/admin/partner-materials', tags=['partner-materials'], dependencies=[Depends(require_admin)])

CATALOGUE = """
WITH attachment_stats AS (
    SELECT case_id, COUNT(*) AS file_count,
        MAX(COALESCE(processed_at, created_at)) AS file_updated_at,
        MAX(CASE WHEN processing_status='processing' THEN 1 ELSE 0 END) AS processing,
        MAX(CASE WHEN processing_status='failed' OR preview_error IS NOT NULL THEN 1 ELSE 0 END) AS failed,
        MAX(CASE WHEN processing_status='empty' THEN 1 ELSE 0 END) AS empty
    FROM deliverables GROUP BY case_id
), entries AS (
    SELECT 'case' AS kind, c.id, c.partner_id, c.title, c.description, c.category_id,
        c.visible, COALESCE(s.file_count,0) AS file_count,
        CASE WHEN s.processing=1 THEN 'processing' WHEN s.failed=1 THEN 'failed'
             WHEN s.empty=1 THEN 'empty' WHEN s.file_count>0 THEN 'ready' ELSE 'no_files' END AS processing_status,
        CASE WHEN s.file_updated_at>COALESCE(c.updated_at,c.created_at) THEN s.file_updated_at
             ELSE COALESCE(c.updated_at,c.created_at) END AS updated_at
    FROM cases c LEFT JOIN attachment_stats s ON s.case_id=c.id
    UNION ALL
    SELECT 'document', d.id, d.partner_id, d.filename, NULL, NULL, 0, 1,
        CASE WHEN d.preview_error IS NOT NULL AND d.processing_status!='processing' THEN 'failed' ELSE d.processing_status END,
        COALESCE(d.processed_at,d.created_at)
    FROM partner_documents d WHERE COALESCE(d.doc_category,'')!='profile_import'
), materials AS (
    SELECT e.*,p.name AS partner_name,
        CASE WHEN p.materials_revision!=p.profile_materials_revision THEN 1 ELSE 0 END AS profile_needs_update
    FROM entries e JOIN partners p ON p.id=e.partner_id
)
"""

@router.get('')
def catalogue(partner_id: str | None = None, category_group: str | None = None,
              category_id: str | None = None, q: str = Query('', max_length=200),
              page: int = Query(1, ge=1), page_size: int = Query(12, ge=1, le=60)):
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
        where.append("LOWER(title) LIKE ? ESCAPE '\\'"); args.append('%'+needle+'%')
    clause=' WHERE '+' AND '.join(where) if where else ''
    with get_db() as conn:
        partners=[dict(r) for r in conn.execute('SELECT id,name FROM partners ORDER BY name,id')]
        if partner_id and not any(p['id']==partner_id for p in partners): raise HTTPException(404,'伙伴不存在')
        total=conn.execute(CATALOGUE+'SELECT COUNT(*) FROM materials'+clause, args).fetchone()[0]
        rows=conn.execute(CATALOGUE+'SELECT * FROM materials'+clause+" ORDER BY CASE WHEN category_id LIKE 'marketing-%' THEN 0 WHEN category_id LIKE 'delivery-%' THEN 1 WHEN category_id LIKE 'technical-%' THEN 2 ELSE 3 END, updated_at DESC,id LIMIT ? OFFSET ?", [*args,page_size,(page-1)*page_size]).fetchall()
    return {'items':[{**dict(r),'visible':bool(r['visible']),'profile_needs_update':bool(r['profile_needs_update'])} for r in rows], 'total':total,'partners':partners}

@router.put('/documents/{document_id}/classify', response_model=CaseOut)
def classify_document(document_id: str, payload: CaseCreate, actor=Depends(require_admin)):
    """Admin explicitly categorizes a legacy file; keep its ID, bytes and cached output."""
    check_category(payload.category_id)
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        old=conn.execute('SELECT * FROM partner_documents WHERE id=?',(document_id,)).fetchone()
        if not old: raise HTTPException(404,'资料不存在')
        if old['doc_category']=='profile_import': raise HTTPException(409,'画像原件不属于案例资料')
        if old['processing_status']=='processing': raise HTTPException(409,'文件正在处理中，请稍后归类')
        if not conn.execute('SELECT id FROM partners WHERE id=?',(payload.partner_id,)).fetchone(): raise HTTPException(404,'伙伴不存在')
        row=conn.execute("DELETE FROM partner_documents WHERE id=? AND processing_status!='processing' RETURNING *",(document_id,)).fetchone()
        if not row: raise HTTPException(409,'资料已变化，请刷新后重试')
        stamp=files.now()
        conn.execute('INSERT INTO cases (id,partner_id,title,description,category_id,visible,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
                     (document_id,payload.partner_id,payload.title,payload.description,payload.category_id,int(payload.visible),row['created_at'],stamp))
        columns=('id','filename','file_path','file_type','created_at','extracted_text','processing_status','processing_error','preview_path','preview_error','processed_at')
        conn.execute('INSERT INTO deliverables (case_id,'+','.join(columns)+') VALUES ('+','.join('?' for _ in range(len(columns)+1))+')',
                     (document_id,*(row[c] for c in columns)))
        for pid in {old['partner_id'],payload.partner_id}: files.changed(conn,pid)
        record_audit(conn,'partner_document_classified',actor_user_id=actor['id'],summary={'document_id':document_id,'case_id':document_id})
        return visible_case(conn,document_id,True)
