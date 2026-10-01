"""Delete account access atomically; retain the user ID and all business history."""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .auth import ALGORITHM, record_audit, require_admin
from .config import get_jwt_secret_key
from .database import get_db

router = APIRouter(prefix='/admin/users', tags=['auth'])


def usable_admin(user):
    if user['role'] != 'admin' or user['status'] != 'active' or not user['hashed_password']:
        return False
    if user['locked_until']:
        try:
            until = datetime.fromisoformat(user['locked_until'])
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            return until <= datetime.now(timezone.utc)
        except ValueError:
            return False
    return True


def inspect_cleanup(conn, user_id, admin_id):
    user = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    if not user or user['status'] == 'deleted':
        raise HTTPException(404, '用户不存在')
    running = conn.execute("""SELECT count(*) FROM development_runs r
        JOIN development_plans p ON p.id=r.plan_id
        WHERE (p.owner_user_id=? OR r.owner_user_id=?) AND r.status IN ('pending','running')""",
        (user_id, user_id)).fetchone()[0]
    running += conn.execute("SELECT count(*) FROM match_records WHERE owner_user_id=? AND task_status IN ('matching','enriching')",
                            (user_id,)).fetchone()[0]
    reason = ''
    if user_id == admin_id:
        reason = '不能删除当前操作账号。'
    elif usable_admin(user) and not any(usable_admin(row) for row in conn.execute(
            "SELECT * FROM users WHERE role='admin' AND status='active' AND id<>?", (user_id,))):
        reason = '不能删除最后一个可用管理员。'
    elif running:
        reason = '该账号仍有任务运行中，请等任务结束后再删除。'
    return user, {'userId': user_id, 'allowed': not reason, 'reason': reason}


@router.get('/{user_id}/deletion-preview')
def preview(user_id: str, response: Response, admin: dict = Depends(require_admin)):
    response.headers['Cache-Control'] = 'no-store'
    with get_db() as conn:
        conn.lock_writer()
        user, result = inspect_cleanup(conn, user_id, admin['id'])
    result['confirmationToken'] = jwt.encode({
        'purpose': 'account_soft_delete', 'target': user_id, 'admin': admin['id'],
        'version': user['token_version'], 'exp': datetime.now(timezone.utc) + timedelta(minutes=10),
    }, get_jwt_secret_key(), algorithm=ALGORITHM) if result['allowed'] else None
    return result


class DeleteUser(BaseModel):
    confirmationToken: str = Field(min_length=1, max_length=4096)


@router.delete('/{user_id}', status_code=204)
def delete_user(user_id: str, payload: DeleteUser, request: Request, admin: dict = Depends(require_admin)):
    try:
        confirmation = jwt.decode(payload.confirmationToken, get_jwt_secret_key(), algorithms=[ALGORITHM])
        if confirmation.get('purpose') != 'account_soft_delete' or confirmation.get('target') != user_id or confirmation.get('admin') != admin['id']:
            raise ValueError('Wrong confirmation')
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(409, '删除确认已失效，请重新确认。') from None
    with get_db() as conn:
        conn.lock_writer()
        # Recheck the operator under the same writer lock as the target. Concurrent
        # deletes must not let an already-deleted administrator continue operating.
        operator = conn.execute("SELECT status,role,token_version FROM users WHERE id=?", (admin['id'],)).fetchone()
        if not operator or operator['status'] != 'active' or operator['role'] != 'admin' or operator['token_version'] != admin['token_version']:
            raise HTTPException(401, '登录状态已失效，请重新登录')
        user, result = inspect_cleanup(conn, user_id, admin['id'])
        if not result['allowed']:
            raise HTTPException(409, result['reason'])
        if confirmation.get('version') != user['token_version']:
            raise HTTPException(409, '账号状态已变化，请重新确认。')
        stamp = datetime.now(timezone.utc).isoformat()
        # Keep only the irreversible Key digest for the existing "identity deleted"
        # response. No Key ciphertext, browser secret or legacy credential survives.
        conn.execute('INSERT INTO revoked_identity_keys(key_hash,revoked_at) SELECT key_hash,? FROM user_identity_keys WHERE user_id=?',
                     (stamp, user_id))
        conn.execute('DELETE FROM identity_credentials WHERE user_id=?', (user_id,))
        conn.execute('DELETE FROM identity_challenges WHERE user_id=?', (user_id,))
        conn.execute('DELETE FROM user_identity_keys WHERE user_id=?', (user_id,))
        conn.execute("UPDATE users SET status='deleted',token_version=token_version+1,updated_at=? WHERE id=?", (stamp, user_id))
        record_audit(conn, 'admin.user_deleted', actor_user_id=admin['id'], target_user_id=user_id,
                     summary={'username': user['username'], 'display_name': user['display_name'],
                              'business_data_preserved': True},
                     ip_address=request.client.host if request.client else None)
    return Response(status_code=204)
