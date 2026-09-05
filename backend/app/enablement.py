"""Resource and case-sharing lifecycle with explicit, fail-closed projections."""
from datetime import datetime, timezone
import ipaddress
import json
import uuid
from typing import Literal
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from .database import get_db

Kind = Literal['resource', 'case']
TABLES = {
    'resource': ('enablement_resources', 'enablement_resource_versions', 'id'),
    'case': ('case_share_configs', 'case_share_versions', 'case_id'),
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class ResourceMetadata(StrictModel):
    resource_type: Literal['course', 'lab']
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=4000)
    target_capability: str = Field(min_length=1, max_length=1000)
    audience: str = Field(default='未知', min_length=1, max_length=500)
    product_direction: str = Field(default='未知', min_length=1, max_length=200)
    difficulty: Literal['unknown','beginner','intermediate','advanced'] = 'unknown'
    language: str = Field(default='未知', min_length=1, max_length=100)
    site: str = Field(default='未知', min_length=1, max_length=200)
    prerequisites: str = Field(default='未知', min_length=1, max_length=1000)
    duration_minutes: int | None = Field(default=None, gt=0, le=100000)
    cost: Literal['unknown','free','paid'] = 'unknown'
    account_requirement: str = Field(default='未知', min_length=1, max_length=1000)
    environment_requirement: str = Field(default='未知', min_length=1, max_length=1000)
    source_platform: str = Field(min_length=1, max_length=200)
    source_url: str = Field(min_length=1, max_length=2000)
    capability_tag_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator('source_url')
    @classmethod
    def check_url(cls, value):
        try:
            # Normalize browser-style numeric host forms before rejecting local addresses.
            normalized = HttpUrl(value)
            p = urlsplit(str(normalized))
            host = p.hostname
            if p.scheme not in ('http', 'https') or not host or p.username or p.password:
                raise ValueError()
            if any(c.isspace() or ord(c) < 32 for c in value) or '\\' in value:
                raise ValueError()
            if host == 'localhost' or host.endswith(('.localhost','.local','.internal')) or '.' not in host:
                raise ValueError()
            try:
                if not ipaddress.ip_address(host).is_global: raise ValueError('private address')
            except ValueError as e:
                if str(e) == 'private address': raise
            if p.port is not None and p.port not in (80,443): raise ValueError()
        except ValueError:
            raise ValueError('请填写不含凭据的外部 HTTP/HTTPS 来源链接') from None
        return value


class ShareMetadata(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=4000)
    methods: str = Field(min_length=1, max_length=4000)
    contributor_role: str = Field(min_length=1, max_length=1000)
    source_platform: str = Field(min_length=1, max_length=200)
    source_url: str = Field(min_length=1, max_length=2000)
    capability_tag_ids: list[str] = Field(default_factory=list, max_length=100)
    _url = field_validator('source_url')(ResourceMetadata.check_url.__func__)


class ResourceSave(StrictModel):
    base_revision: int = Field(ge=0)
    metadata: ResourceMetadata


class ShareSave(StrictModel):
    base_revision: int = Field(ge=0)
    metadata: ShareMetadata


class Revision(StrictModel):
    base_revision: int = Field(ge=1)


class Permissions(Revision):
    system_visible: bool = False
    model_allowed: bool = False
    partner_allowed: bool = False
    reason: str = Field(min_length=1, max_length=500)


class Review(Revision):
    link_status: Literal['available','unavailable','unknown']
    content_checked: bool
    authorization_checked: bool
    note: str = Field(default='', max_length=500)


class Unpublish(Revision):
    reason: str = Field(min_length=1, max_length=500)
    sensitive: bool = False


def now():
    return datetime.now(timezone.utc).isoformat()


def fail(status, message):
    raise HTTPException(status, message)


def row_for(conn, kind, source_id):
    table, _, key = TABLES[kind]
    row = conn.execute(f'SELECT * FROM {table} WHERE {key}=?', (source_id,)).fetchone()
    if row is None: fail(404, '资源或共享配置不存在')
    return dict(row)


def check_base(row, revision):
    if row['revision'] != revision: fail(409, '内容已更新，请刷新后重新操作')


def check_case(conn, case_id):
    row = conn.execute('SELECT p.id,p.name FROM cases c JOIN partners p ON p.id=c.partner_id WHERE c.id=? AND p.status=?', (case_id,'active')).fetchone()
    if row is None: fail(409, '案例必须关联有效且启用的伙伴，孤儿案例不能共享')
    return dict(row)


def check_tags(conn, ids, required=False):
    if required and not ids: fail(409, '发布前至少关联一个正式能力标签')
    if len(ids) != len(set(ids)): fail(422, '能力标签不能重复')
    for tag in ids:
        if not conn.execute('SELECT id FROM capability_tags WHERE id=? AND enabled=1',(tag,)).fetchone():
            fail(422, '能力标签不存在或已停用')


def audit(conn, kind, source_id, action, actor, row, reason=''):
    conn.execute('INSERT INTO enablement_audit_events VALUES (?,?,?,?,?,?,?,?,?)',
        (str(uuid.uuid4()),kind,source_id,action,actor,row['revision'],row['authorization_epoch'],reason,now()))


def detail_in(conn, kind, source_id):
    row = row_for(conn,kind,source_id)
    row['source_id'] = source_id
    row['metadata'] = json.loads(row.pop('draft_json'))
    _, versions, _ = TABLES[kind]
    row['versions'] = [dict(v) for v in conn.execute(f'SELECT version,reviewed_revision,authorization_epoch,published_at,published_by FROM {versions} WHERE source_id=? ORDER BY version DESC',(source_id,))]
    row['reviews'] = [dict(v) for v in conn.execute('SELECT r.*, COALESCE(u.display_name,u.username) AS reviewer_name FROM enablement_reviews r JOIN users u ON u.id=r.reviewer_id WHERE source_kind=? AND source_id=? ORDER BY reviewed_at DESC',(kind,source_id))]
    row['audit'] = [dict(v) for v in conn.execute('SELECT action,actor_id,revision,authorization_epoch,reason,created_at FROM enablement_audit_events WHERE source_kind=? AND source_id=? ORDER BY created_at DESC',(kind,source_id))]
    if row['published_version']:
        v=conn.execute(f'SELECT payload_json FROM {versions} WHERE source_id=? AND version=?',(source_id,row['published_version'])).fetchone()
        row['published_metadata']=json.loads(v[0])
    return row


def detail(kind, source_id):
    with get_db() as conn: return detail_in(conn,kind,source_id)


def listing():
    with get_db() as conn:
        return [detail_in(conn,'resource',r[0]) for r in conn.execute('SELECT id FROM enablement_resources ORDER BY updated_at DESC')]


def save(kind, source_id, payload, actor):
    table, _, key = TABLES[kind]
    metadata=payload.metadata.model_dump()
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if kind=='case': check_case(conn,source_id)
        check_tags(conn,metadata['capability_tag_ids'])
        existing=conn.execute(f'SELECT * FROM {table} WHERE {key}=?',(source_id,)).fetchone()
        if existing:
            row=dict(existing); check_base(row,payload.base_revision)
            if kind=='resource' and json.loads(row['draft_json'])['resource_type'] != metadata['resource_type']:
                fail(409,'已建立资源的类型不能更改')
            conn.execute(f'UPDATE {table} SET draft_json=?,revision=revision+1,updated_at=? WHERE {key}=?',
                (json.dumps(metadata,ensure_ascii=False),now(),source_id))
        else:
            if payload.base_revision != 0: fail(409,'资源尚未建立，请刷新')
            conn.execute(f'INSERT INTO {table} ({key},draft_json,created_by,created_at,updated_at) VALUES (?,?,?,?,?)',
                (source_id,json.dumps(metadata,ensure_ascii=False),actor,now(),now()))
        if kind=='resource':
            conn.execute('DELETE FROM resource_capability_map WHERE resource_id=?',(source_id,))
            conn.executemany('INSERT INTO resource_capability_map VALUES (?,?)',[(source_id,t) for t in metadata['capability_tag_ids']])
        row=row_for(conn,kind,source_id)
        audit(conn,kind,source_id,'edit' if existing else 'create',actor,row)
        return detail_in(conn,kind,source_id)


def permissions(kind, source_id, payload, actor):
    table, _, key = TABLES[kind]
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row=row_for(conn,kind,source_id); check_base(row,payload.base_revision)
        fields=('system_visible','model_allowed','partner_allowed')
        reduced=any(row[f] and not getattr(payload,f) for f in fields)
        conn.execute(f'''UPDATE {table} SET system_visible=?,model_allowed=?,partner_allowed=?,
            authorization_epoch=authorization_epoch+?,revision=revision+1,updated_at=? WHERE {key}=?''',
            (*(int(getattr(payload,f)) for f in fields),int(reduced),now(),source_id))
        audit(conn,kind,source_id,'permissions',actor,row_for(conn,kind,source_id),payload.reason)
        return detail_in(conn,kind,source_id)


def review(kind, source_id, payload, actor):
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row=row_for(conn,kind,source_id); check_base(row,payload.base_revision)
        if kind=='case': check_case(conn,source_id)
        conn.execute('INSERT INTO enablement_reviews VALUES (?,?,?,?,?,?,?,?,?,?)',
            (str(uuid.uuid4()),kind,source_id,row['revision'],actor,now(),payload.link_status,int(payload.content_checked),int(payload.authorization_checked),payload.note))
        audit(conn,kind,source_id,'review',actor,row)
        return detail_in(conn,kind,source_id)


def publish(kind, source_id, payload, actor):
    table, versions, key = TABLES[kind]
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row=row_for(conn,kind,source_id); check_base(row,payload.base_revision)
        metadata=json.loads(row['draft_json'])
        check_tags(conn,metadata['capability_tag_ids'],required=True)
        if kind=='case':
            partner=check_case(conn,source_id)
            metadata['contributor_name']=partner['name']
            metadata['contributor_id']=partner['id']
        latest=conn.execute('SELECT * FROM enablement_reviews WHERE source_kind=? AND source_id=? AND revision=? ORDER BY reviewed_at DESC LIMIT 1',
            (kind,source_id,row['revision'])).fetchone()
        if not latest or latest['link_status']!='available' or not latest['content_checked'] or not latest['authorization_checked']:
            fail(409,'请先完成当前内容与授权的人工核验，并确认来源链接可用')
        version=conn.execute(f'SELECT COALESCE(MAX(version),0)+1 FROM {versions} WHERE source_id=?',(source_id,)).fetchone()[0]
        # Freeze authorization with the content: granting flags later must not expose old content.
        metadata['_permissions']={f:bool(row[f]) for f in ('system_visible','model_allowed','partner_allowed')}
        conn.execute(f'INSERT INTO {versions} VALUES (?,?,?,?,?,?,?)',
            (source_id,version,json.dumps(metadata,ensure_ascii=False),row['authorization_epoch'],row['revision'],actor,now()))
        conn.execute(f"UPDATE {table} SET status='published',published_version=?,revision=revision+1,updated_at=? WHERE {key}=?",(version,now(),source_id))
        audit(conn,kind,source_id,'publish',actor,row_for(conn,kind,source_id))
        return detail_in(conn,kind,source_id)


def unpublish(kind, source_id, payload, actor):
    table, _, key=TABLES[kind]
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row=row_for(conn,kind,source_id); check_base(row,payload.base_revision)
        conn.execute(f'UPDATE {table} SET status=?,authorization_epoch=authorization_epoch+?,revision=revision+1,updated_at=? WHERE {key}=?',
            ('revoked' if payload.sensitive else 'unpublished',int(payload.sensitive),now(),source_id))
        audit(conn,kind,source_id,'revoke' if payload.sensitive else 'unpublish',actor,row_for(conn,kind,source_id),payload.reason)
        return detail_in(conn,kind,source_id)


# These are internal service contracts for Phase B/C, not unauthenticated/public endpoints.
# Callers must perform current user and Plan owner/admin checks first.
def resolve_reference(conn, source_type, source_id, source_version, purpose='system'):
    if source_type not in ('course','lab','case') or purpose not in ('system','model','partner'):
        fail(422,'引用或使用目的无效')
    kind='case' if source_type=='case' else 'resource'
    row=row_for(conn,kind,source_id)
    if row['status']!='published' or row['published_version']!=source_version:
        fail(409,'引用已不可用，请重新选择资源或生成方案')
    _, versions, _=TABLES[kind]
    version=conn.execute(f'SELECT * FROM {versions} WHERE source_id=? AND version=?',(source_id,source_version)).fetchone()
    if not version or version['authorization_epoch']!=row['authorization_epoch']:
        fail(409,'授权已变化，请重新核验发布并生成方案')
    data=json.loads(version['payload_json'])
    if kind=='case':
        partner=check_case(conn,source_id)
        if partner['id']!=data['contributor_id']: fail(409,'案例归属已变化，需重新核验')
    elif data['resource_type']!=source_type: fail(422,'引用类型与资源不符')
    check_tags(conn,data['capability_tag_ids'],required=True)
    flags=['system_visible'] + ({'model':['model_allowed'],'partner':['partner_allowed']}.get(purpose,[]))
    if any(not row[f] or not data['_permissions'].get(f,False) for f in flags):
        fail(403,'当前内容未获得此用途的明确授权')
    shared=('title','summary','methods','contributor_role','contributor_name','source_platform')
    resource=('title','summary','target_capability','audience','product_direction','difficulty','language','site','prerequisites','duration_minutes','cost','account_requirement','environment_requirement','source_platform')
    result={f:data[f] for f in (shared if kind=='case' else resource)}
    if purpose!='model': result['source_url']=data['source_url']
    if purpose!='partner': result.update(source_type=source_type,source_id=source_id,source_version=source_version,capability_tag_ids=data['capability_tag_ids'])
    return result
