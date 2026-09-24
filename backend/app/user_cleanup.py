"""Manual ordinary identity deletion: preview, recheck, then one transaction."""
import hashlib
import json
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .auth import ALGORITHM, record_audit, require_admin
from .config import browser_identity_retention_days, get_jwt_secret_key
from .database import get_db

router = APIRouter(prefix='/admin/users', tags=['auth'])
MATCHES = 'SELECT id FROM match_records WHERE owner_user_id=?'
PLANS = 'SELECT id FROM development_plans WHERE owner_user_id=?'
VERSIONS = f'SELECT id FROM development_versions WHERE plan_id IN ({PLANS})'
PRIVATE = [
    ('match_records', '匹配任务', 'owner_user_id=?'),
    ('development_plans', '发展方案', 'owner_user_id=?'),
    ('development_requests', '发展需求', 'owner_user_id=?'),
    ('development_runs', '运行记录', f'plan_id IN ({PLANS})'),
    ('development_versions', '方案版本', f'plan_id IN ({PLANS})'),
    ('development_version_items', '版本内容', f'version_id IN ({VERSIONS})'),
    ('development_diagnoses', '方案诊断', f'version_id IN ({VERSIONS})'),
    ('development_audit_events', '方案操作记录', f'plan_id IN ({PLANS})'),
    ('resource_redirect_events', '个人资源跳转记录', 'actor_user_id=?'),
]
PUBLIC = [
    ('demand_profiles', '公共需求画像', f'match_record_id IN ({MATCHES})'),
    ('project_opportunities', '项目机会', f'match_record_id IN ({MATCHES})'),
    ('capability_tag_suggestions', '公共标签建议', f'source_match_record_id IN ({MATCHES})'),
    ('feedback_issue', '问题反馈', 'submitter_id=?'),
    ('feedback_attachment', '反馈附件', 'issue_id IN (SELECT id FROM feedback_issue WHERE submitter_id=?)'),
    ('user_applications', '历史注册审批', 'user_id=? OR reviewed_by=?'),
    ('users', '创建的其他账号', 'created_by=?'),
    ('case_share_configs', '案例共享配置', 'created_by=?'),
    ('case_share_versions', '案例发布版本', 'published_by=?'),
    ('enablement_resources', '公共资源', 'created_by=?'),
    ('enablement_resource_versions', '资源发布版本', 'published_by=?'),
    ('enablement_reviews', '发布核验', 'reviewer_id=?'),
    ('enablement_audit_events', '公共资源操作记录', 'actor_id=?'),
    ('development_audit_events', '已对外传递的方案', f"plan_id IN ({PLANS}) AND action='transfer_copy'"),
    ('development_audit_events', '其他用户参与的方案记录', f'(actor_user_id=? AND plan_id NOT IN ({PLANS})) OR (actor_user_id<>? AND plan_id IN ({PLANS}))'),
    ('development_requests', '其他用户参与的发展需求', '(created_by=? AND owner_user_id<>?) OR (created_by<>? AND owner_user_id=?)'),
    ('development_runs', '跨用户运行引用', f'(owner_user_id=? AND plan_id NOT IN ({PLANS})) OR (owner_user_id<>? AND plan_id IN ({PLANS}))'),
    ('development_versions', '跨用户版本引用', f'(created_by=? AND plan_id NOT IN ({PLANS})) OR (created_by<>? AND plan_id IN ({PLANS})) OR (plan_id NOT IN ({PLANS}) AND based_on_version_id IN ({VERSIONS}))'),
    ('development_plans', '跨用户方案引用', f'owner_user_id<>? AND (request_id IN (SELECT id FROM development_requests WHERE owner_user_id=?) OR current_version_id IN ({VERSIONS}) OR confirmed_version_id IN ({VERSIONS}))'),
    ('development_audit_events', '其他方案引用的版本记录', f'plan_id NOT IN ({PLANS}) AND version_id IN ({VERSIONS})'),
    ('development_runs', '其他方案引用的版本', f'plan_id NOT IN ({PLANS}) AND based_on_version_id IN ({VERSIONS})'),
]


def stamp(value):
    parsed = datetime.fromisoformat(value)
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def inspect_cleanup(conn, user_id):
    user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    if not user:
        raise HTTPException(404, '用户不存在')
    user = dict(user)
    private, public, state, timestamps = [], [], [], []
    for table, label, where in PRIVATE + PUBLIC:
        rows = [dict(r) for r in conn.execute(f'SELECT * FROM {table} WHERE {where}', (user_id,) * where.count('?'))]
        # Complete row hashes also detect edits/replacements between preview and confirmation.
        state.append([label, sorted(json.dumps(r, sort_keys=True, ensure_ascii=False) for r in rows)])
        entry = {'key': table, 'label': label, 'count': len(rows)}
        (private if (table, label, where) in PRIVATE else public).append(entry)
        if (table, label, where) in PRIVATE:
            for row in rows:
                timestamps.extend(row.get(key) for key in ('created_at', 'updated_at', 'ended_at') if row.get(key))
    # Task source references are stored in JSON rather than foreign keys.
    task_ids = {r[0] for r in conn.execute(MATCHES, (user_id,))} | {r[0] for r in conn.execute(PLANS, (user_id,))}
    def references(value):
        if isinstance(value, dict):
            return any((key == 'source_task_id' and isinstance(item, str) and item in task_ids) or references(item) for key, item in value.items())
        return isinstance(value, list) and any(references(item) for item in value)
    cross = []
    for table, column, where in ([
        ('development_requests', 'payload_json', 'owner_user_id<>?'),
        ('development_runs', 'input_snapshot', f'plan_id NOT IN ({PLANS})'),
        ('development_versions', 'payload_json', f'plan_id NOT IN ({PLANS})'),
    ] if task_ids else []):
        for row in conn.execute(f'SELECT id,{column} FROM {table} WHERE {where}', (user_id,)):
            try:
                if references(json.loads(row[column])):
                    cross.append([table, row['id']])
            except (ValueError, TypeError):
                # Unreadable context cannot be proven unrelated.
                cross.append([table, row['id']])
    public.append({'key': 'source_references', 'label': '其他用户任务的来源引用', 'count': len(cross)})
    state.append(cross)
    credentials = [dict(r) for r in conn.execute('SELECT * FROM identity_credentials WHERE user_id=? ORDER BY id', (user_id,))]
    keys = [dict(r) for r in conn.execute('SELECT * FROM user_identity_keys WHERE user_id=?', (user_id,))]
    methods = {'key'} if keys else {r['kind'] for r in credentials}
    public = [entry for entry in public if entry['count']]
    private = [entry for entry in private if entry['count']]
    audit_count = conn.execute('SELECT count(*) FROM user_audit_logs WHERE actor_user_id=? OR target_user_id=?', (user_id, user_id)).fetchone()[0]
    days = browser_identity_retention_days()
    timestamps.extend(user.get(key) for key in ('last_active_at', 'last_login_at', 'created_at') if user.get(key))
    try:
        last_active = max(map(stamp, timestamps)) if timestamps and user.get('last_active_at') else None
    except (TypeError, ValueError):
        last_active = None
    eligible_after = last_active + timedelta(days=days) if last_active and methods == {'browser'} else None
    running = conn.execute(f"SELECT count(*) FROM development_runs WHERE plan_id IN ({PLANS}) AND status IN ('pending','running')", (user_id,)).fetchone()[0]
    running += conn.execute("SELECT count(*) FROM match_records WHERE owner_user_id=? AND task_status IN ('matching','enriching')", (user_id,)).fetchone()[0]
    reason = ''
    if user['role'] != 'user':
        reason = '管理员账号不开放删除，请使用停用。'
    elif not methods or not methods <= {'browser', 'passkey', 'key'}:
        reason = '该用户未配置可识别的普通身份凭据，请使用停用。'
    elif public:
        reason = '存在公共、共享或其他用户业务引用，不能删除，请使用停用。'
    elif running:
        reason = '仍有任务运行中，暂时不能删除。'
    elif private and methods & {'passkey', 'key'}:
        reason = '长期身份存在业务历史，不支持连带删除，请使用停用。'
    elif private and (not eligible_after or datetime.now(timezone.utc) < eligible_after):
        reason = f'存在个人业务历史，须连续 {days} 天未使用后才能删除。'
    result = {
        'userId': user_id, 'displayName': user['display_name'] or user['username'],
        'allowed': not reason, 'reason': reason or ('将删除该身份及其个人私有历史。' if private else '该身份没有业务历史，可以删除。'),
        'retentionDays': days, 'lastActiveAt': last_active.isoformat() if last_active else None,
        'eligibleAfter': eligible_after.isoformat() if eligible_after and private else None,
        'privateData': private, 'publicReferences': public, 'credentialCount': len(credentials) + len(keys),
        'retainedAuditCount': audit_count,
    }
    digest = hashlib.sha256(json.dumps([user, credentials, keys, state, days], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return result, digest


@router.get('/{user_id}/deletion-preview')
def preview(user_id: str, response: Response, admin: dict = Depends(require_admin)):
    response.headers['Cache-Control'] = 'no-store'
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        result, digest = inspect_cleanup(conn, user_id)
    result['confirmationToken'] = jwt.encode({'purpose': 'user_cleanup', 'target': user_id, 'admin': admin['id'],
        'digest': digest, 'exp': datetime.now(timezone.utc) + timedelta(minutes=10)}, get_jwt_secret_key(), algorithm=ALGORITHM) if result['allowed'] else None
    return result


class DeleteUser(BaseModel):
    confirmationToken: str = Field(min_length=1, max_length=4096)


def delete_private_history(conn, user_id):
    # Circular Plan/Run/Version pointers are checked at commit, without updating immutable versions.
    if hasattr(conn, 'connection'):
        conn.execute('SET CONSTRAINTS ALL DEFERRED')
    else:
        conn.execute('PRAGMA defer_foreign_keys=ON')
    policies = {table: where for table, _, where in PRIVATE}
    for table in ('development_diagnoses', 'development_version_items', 'development_audit_events',
                  'development_versions', 'development_runs', 'development_plans', 'development_requests',
                  'resource_redirect_events', 'match_records'):
        conn.execute(f'DELETE FROM {table} WHERE {policies[table]}', (user_id,))


@router.delete('/{user_id}', status_code=204)
def delete_user(user_id: str, payload: DeleteUser, request: Request, admin: dict = Depends(require_admin)):
    try:
        confirmation = jwt.decode(payload.confirmationToken, get_jwt_secret_key(), algorithms=[ALGORITHM])
        if confirmation.get('purpose') != 'user_cleanup' or confirmation.get('target') != user_id or confirmation.get('admin') != admin['id']:
            raise ValueError('Wrong confirmation')
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(409, '删除确认已失效，请重新查看关联数据。') from None
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        result, digest = inspect_cleanup(conn, user_id)
        if not result['allowed']:
            raise HTTPException(409, result['reason'])
        if confirmation.get('digest') != digest:
            raise HTTPException(409, '用户活动或关联数据已变化，请重新查看后确认。')
        # Keep only the irreversible digest so a deleted Key is distinguishable
        # from a typo. This record commits or rolls back with the whole deletion.
        conn.execute('INSERT INTO revoked_identity_keys(key_hash,revoked_at) SELECT key_hash,? FROM user_identity_keys WHERE user_id=?',
                     (datetime.now(timezone.utc).isoformat(), user_id))
        delete_private_history(conn, user_id)
        conn.execute('DELETE FROM identity_credentials WHERE user_id=?', (user_id,))
        conn.execute('DELETE FROM identity_challenges WHERE user_id=?', (user_id,))
        conn.execute('DELETE FROM user_identity_keys WHERE user_id=?', (user_id,))
        conn.execute('DELETE FROM users WHERE id=?', (user_id,))
        record_audit(conn, 'admin.user_deleted', actor_user_id=admin['id'], target_user_id=user_id,
                     summary={'display_name': result['displayName'], 'deleted': result['privateData'],
                              'credentials': result['credentialCount'], 'retention_days': result['retentionDays']},
                     ip_address=request.client.host if request.client else None)
    return Response(status_code=204)
