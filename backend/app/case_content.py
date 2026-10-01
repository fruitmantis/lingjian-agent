"""A case has a partner, category and one live visibility switch. No publication copies."""
from fastapi import HTTPException
from .material_contract import category_names

def visible_case(conn,case_id,admin=False):
    row=conn.execute('SELECT c.*,p.name partner_name,p.status partner_status FROM cases c JOIN partners p ON p.id=c.partner_id WHERE c.id=?',(case_id,)).fetchone()
    if not row or (not admin and (not row['visible'] or row['partner_status']!='active')): raise HTTPException(404,'案例不存在或未展示')
    return dict(row)

def projection(conn,case_id,purpose='system'):
    c=visible_case(conn,case_id)
    result=case_projection(c,purpose)
    if purpose!='model':
        from .material_files import public_file
        result['files']=[public_file(r,False) for r in conn.execute('SELECT * FROM deliverables WHERE case_id=? ORDER BY created_at,id',(case_id,))]
    return result

def case_projection(c,purpose='model'):
    if not c['visible'] or c['partner_status']!='active':raise HTTPException(404,'案例不存在或未展示')
    case_id=c['id']
    names=category_names(c['category_id'])
    result={'source_type':'case','source_id':case_id,'source_version':1,
            'title':c['title'],'summary':c['description'] or '',
            'contributor_id':c['partner_id'],'contributor_name':c['partner_name'],
            'category_id':c['category_id'],'category':names['category_group'],'subcategory':names['category_name'],
            'capability_tag_ids':[]}
    # source_version=1 is only a compatibility sentinel for stored Plan item contracts.
    # No case snapshot or version is created, selected or authorized through this number.
    return result
