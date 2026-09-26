"""Resource publication lifecycle with explicit, fail-closed projections."""
from datetime import datetime, timezone
from contextlib import contextmanager
import ipaddress
import json
import uuid
from typing import Literal
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator, ValidationError

from .database import get_db

Kind = Literal['resource']
TABLES = {
    'resource': ('enablement_resources', 'enablement_resource_versions', 'id'),
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class ResourceMetadata(StrictModel):
    resource_type: Literal['course', 'lab']
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=4000)
    role_ids: list[str] = Field(default_factory=list, max_length=100)
    zone_ids: list[str] = Field(default_factory=list, max_length=100)
    level: Literal['basic', 'advanced'] | None = None
    duration_minutes: int | None = Field(default=None, gt=0, le=100000)
    source_url: str = Field(min_length=1, max_length=2000)
    course_goals: str = Field(default='', max_length=4000)
    audience: str = Field(default='', max_length=2000)
    outline: str = Field(default='', max_length=12000)
    cover_url: str = Field(default='', max_length=2000)
    lab_goals: str = Field(default='', max_length=4000)
    lab_requirements: str = Field(default='', max_length=4000)

    @model_validator(mode='after')
    def type_fields(self):
        invalid = ('lab_goals', 'lab_requirements') if self.resource_type == 'course' else ('course_goals', 'audience', 'outline', 'cover_url')
        if any(getattr(self, field) for field in invalid):
            raise ValueError('课程和实验的补充字段不能混用')
        if self.cover_url:
            self.check_url(self.cover_url)
        return self

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


def resource_metadata(data):
    """Read-only adapter for historical immutable snapshots, never an old editing API."""
    fields = ResourceMetadata.model_fields
    result = {k: v for k, v in data.items() if k in fields}
    if 'level' not in data:
        result['level'] = {'beginner': 'basic', 'intermediate': 'advanced', 'advanced': 'advanced'}.get(data.get('difficulty'))
        if data.get('resource_type') == 'course':
            result['course_goals'] = data.get('target_capability', '')
        else:
            result.pop('audience', None)
            result['lab_goals'] = data.get('target_capability', '')
            result['lab_requirements'] = '' if data.get('prerequisites') in (None, '未知', 'unknown') else data['prerequisites']
    # Defaults also cover optional fields absent from old published versions.
    defaults = {'role_ids': [], 'zone_ids': [], 'level': None, 'duration_minutes': None,
                'course_goals': '', 'audience': '', 'outline': '', 'cover_url': '', 'lab_goals': '', 'lab_requirements': ''}
    return {**defaults, **result}


class ResourceSave(StrictModel):
    base_revision: int = Field(ge=0)
    metadata: ResourceMetadata


class Revision(StrictModel):
    base_revision: int = Field(ge=1)


class Permissions(Revision):
    system_visible: bool = False
    model_allowed: bool = False
    partner_allowed: bool = False
    reason: str = Field(min_length=1, max_length=500)


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
    if row is None: fail(404, '资源不存在')
    return dict(row)


def check_base(row, revision):
    if row['revision'] != revision: fail(409, '内容已更新，请刷新后重新操作')


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
    if kind == 'resource': row['metadata'] = resource_metadata(row['metadata'])
    _, versions, _ = TABLES[kind]
    row['versions'] = [dict(v) for v in conn.execute(f'SELECT version,reviewed_revision,authorization_epoch,published_at,published_by FROM {versions} WHERE source_id=? ORDER BY version DESC',(source_id,))]
    row['audit'] = [dict(v) for v in conn.execute('SELECT action,actor_id,revision,authorization_epoch,reason,created_at FROM enablement_audit_events WHERE source_kind=? AND source_id=? ORDER BY created_at DESC',(kind,source_id))]
    if row['published_version']:
        v=conn.execute(f'SELECT payload_json FROM {versions} WHERE source_id=? AND version=?',(source_id,row['published_version'])).fetchone()
        row['published_metadata']=resource_metadata(json.loads(v[0])) if kind == 'resource' else json.loads(v[0])
    return row


def detail(kind, source_id):
    with get_db() as conn: return detail_in(conn,kind,source_id)


def listing():
    with get_db() as conn:
        return [detail_in(conn,'resource',r[0]) for r in conn.execute('SELECT id FROM enablement_resources ORDER BY updated_at DESC')]


@contextmanager
def write_transaction(connection=None):
    """Reuse validation and audit in a maintenance import's outer transaction."""
    if connection is not None:
        yield connection
    else:
        with get_db() as conn:
            conn.execute('BEGIN IMMEDIATE')
            yield conn


def save(kind, source_id, payload, actor, *, connection=None):
    table, _, key = TABLES[kind]
    metadata=payload.metadata.model_dump()
    with write_transaction(connection) as conn:
        from .resource_categories import validate
        validate(conn, metadata)
        existing=conn.execute(f'SELECT * FROM {table} WHERE {key}=?',(source_id,)).fetchone()
        if kind == 'resource':
            metadata['capability_tag_ids'] = json.loads(existing['draft_json']).get('capability_tag_ids', []) if existing else []
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
        row=row_for(conn,kind,source_id)
        audit(conn,kind,source_id,'edit' if existing else 'create',actor,row)
        return detail_in(conn,kind,source_id)


def permissions(kind, source_id, payload, actor, *, connection=None):
    table, _, key = TABLES[kind]
    with write_transaction(connection) as conn:
        row=row_for(conn,kind,source_id); check_base(row,payload.base_revision)
        fields=('system_visible','model_allowed','partner_allowed')
        reduced=any(row[f] and not getattr(payload,f) for f in fields)
        conn.execute(f'''UPDATE {table} SET system_visible=?,model_allowed=?,partner_allowed=?,
            authorization_epoch=authorization_epoch+?,revision=revision+1,updated_at=? WHERE {key}=?''',
            (*(int(getattr(payload,f)) for f in fields),int(reduced),now(),source_id))
        audit(conn,kind,source_id,'permissions',actor,row_for(conn,kind,source_id),payload.reason)
        return detail_in(conn,kind,source_id)


def publish(kind, source_id, payload, actor, *, connection=None):
    table, versions, key = TABLES[kind]
    with write_transaction(connection) as conn:
        row=row_for(conn,kind,source_id); check_base(row,payload.base_revision)
        metadata=json.loads(row['draft_json'])
        from .resource_categories import validate
        try: clean = ResourceMetadata.model_validate(resource_metadata(metadata)).model_dump()
        except ValidationError: fail(422, '资源内容或跳转链接无效，请编辑草稿后重新发布')
        validate(conn, clean)
        if not clean['level']: fail(409, '发布前请选择基础或进阶')
        metadata = {**clean, 'capability_tag_ids': metadata.get('capability_tag_ids', [])}
        version=conn.execute(f'SELECT COALESCE(MAX(version),0)+1 FROM {versions} WHERE source_id=?',(source_id,)).fetchone()[0]
        # Freeze authorization with the content: granting flags later must not expose old content.
        metadata['_permissions']={f:bool(row[f]) for f in ('system_visible','model_allowed','partner_allowed')}
        conn.execute(f'INSERT INTO {versions} VALUES (?,?,?,?,?,?,?)',
            (source_id,version,json.dumps(metadata,ensure_ascii=False),row['authorization_epoch'],row['revision'],actor,now()))
        conn.execute(f"UPDATE {table} SET status='published',published_version=?,revision=revision+1,updated_at=? WHERE {key}=?",(version,now(),source_id))
        audit(conn,kind,source_id,'publish',actor,row_for(conn,kind,source_id))
        return detail_in(conn,kind,source_id)


def unpublish(kind, source_id, payload, actor, *, connection=None):
    table, _, key=TABLES[kind]
    with write_transaction(connection) as conn:
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
    if source_type=='case':
        from .case_content import projection
        return projection(conn,source_id,purpose)
    row=row_for(conn,'resource',source_id)
    if row['status']!='published' or row['published_version']!=source_version:
        fail(409,'引用已不可用，请重新选择资源或生成方案')
    version=conn.execute('SELECT * FROM enablement_resource_versions WHERE source_id=? AND version=?',(source_id,source_version)).fetchone()
    if not version or version['authorization_epoch']!=row['authorization_epoch']:
        fail(409,'授权已变化，请重新核验发布并生成方案')
    data=json.loads(version['payload_json'])
    if data['resource_type']!=source_type: fail(422,'引用类型与资源不符')
    flags=['system_visible'] + ({'model':['model_allowed'],'partner':['partner_allowed']}.get(purpose,[]))
    if any(not row[f] or not data['_permissions'].get(f,False) for f in flags):
        fail(403,'当前内容未获得此用途的明确授权')
    from .resource_categories import labels
    data={**data,**resource_metadata(data)}
    tags=[tag for tag in data.get('capability_tag_ids',[]) if conn.execute('SELECT 1 FROM capability_tags WHERE id=? AND enabled=1',(tag,)).fetchone()]
    fields=('title','summary','role_ids','zone_ids','level','duration_minutes','course_goals','audience','outline','lab_goals','lab_requirements')
    result={k:data.get(k) for k in fields}
    result.update(labels(conn,data))
    if purpose!='model': result.update(source_url=data['source_url'],cover_url=data.get('cover_url',''))
    if purpose!='partner': result.update(source_type=source_type,source_id=source_id,source_version=source_version,capability_tag_ids=tags)
    return result
