"""Automatic ordinary identity, long-lived Key login, independent browser sessions."""
import json
import secrets
import re
import threading
import time
import uuid
import os
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from ..auth import create_token, decode_token, record_audit, require_user
from ..database import get_db
from ..identity_keys import create_identity_key, reveal_identity_key, digest
from ..models import TokenResponse, UserOut

router = APIRouter(prefix='/auth/identity', tags=['local-identity'])
# A new cookie deliberately does not adopt old browser/Passkey identities.
BROWSER_COOKIE = 'banfei_identity_session'
COOKIE_PATH = '/'
KEY_LOGIN_MAX_BODY_BYTES = 4 * 1024
_ATTEMPTS = defaultdict(deque)
_LOCK = threading.Lock()


def now():
    return datetime.now(timezone.utc)


def settings():
    origin = os.getenv('BANFEI_IDENTITY_ORIGIN', 'http://localhost:3000').rstrip('/')
    parsed = urlsplit(origin)
    if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or not parsed.hostname:
        raise RuntimeError('Invalid identity origin')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname == 'localhost'):
        raise RuntimeError('Identity requires HTTPS or localhost')
    return origin, parsed.hostname, parsed.scheme == 'https'


def incoming(request, response):
    origin, rp, secure = settings()
    if request.headers.get('origin') != origin:
        raise HTTPException(403, '请求来源无效，请从伴飞页面重新进入')
    response.headers['Cache-Control'] = 'no-store'
    key = request.client.host if request.client else 'unknown'
    stamp = time.monotonic()
    with _LOCK:
        # Bound both the work and the number of retained client buckets.
        for old in list(_ATTEMPTS):
            if not _ATTEMPTS[old] or _ATTEMPTS[old][-1] < stamp - 60:
                del _ATTEMPTS[old]
        if key not in _ATTEMPTS and len(_ATTEMPTS) >= 2048:
            raise HTTPException(429, '操作频繁，请稍后重试')
        attempts = _ATTEMPTS[key]
        while attempts and attempts[0] < stamp - 60:
            attempts.popleft()
        if len(attempts) >= 60:
            raise HTTPException(429, '操作频繁，请稍后重试')
        attempts.append(stamp)
    return origin, rp, secure


def cookie(response, name, value, secure, age):
    response.set_cookie(name, value, max_age=age, httponly=True, secure=secure,
                        samesite='strict', path=COOKIE_PATH)



def make_user(conn, user_id):
    stamp = now().isoformat()
    conn.execute("""INSERT INTO users(id,username,hashed_password,display_name,role,status,
                 must_change_password,token_version,created_at,updated_at)
                 VALUES (?,?,NULL,?,'user','active',0,0,?,?)""",
                 (user_id, 'local_' + uuid.UUID(user_id).hex, '伴飞用户', stamp, stamp))
    create_identity_key(conn, user_id)
    record_audit(conn, 'identity.created', actor_user_id=user_id, target_user_id=user_id)


def identity_error(code, message, **context):
    return HTTPException(401, detail={'code': code, 'message': message, **context},
                         headers={'Cache-Control': 'no-store', 'Pragma': 'no-cache'})


def session(conn, user_id, session_id):
    row = conn.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    if row is not None and row['role'] == 'user' and row['status'] == 'disabled':
        raise identity_error('identity_disabled', '该身份已停用，需要管理员重新启用后才能继续使用。')
    if row is None or row['role'] != 'user' or row['status'] != 'active':
        raise HTTPException(401, '当前身份不可用，请使用有效的身份 Key 登录')
    user = dict(row)
    user['last_login_at'] = now().isoformat()
    conn.execute('UPDATE users SET last_login_at=?,last_active_at=? WHERE id=?',
                 (user['last_login_at'], user['last_login_at'], user_id))
    record_audit(conn, 'identity.login', actor_user_id=user_id, summary={'method': 'key'})
    return TokenResponse(access_token=create_token(user_id, user['username'], 'user',
        int(user['token_version']), auth_method='key', session_id=session_id), user=UserOut(**user, identity_method='key'))


def add_browser_session(conn, user_id):
    session_id, secret = str(uuid.uuid4()), secrets.token_urlsafe(32)
    conn.execute("""INSERT INTO identity_credentials(id,user_id,kind,secret_hash,created_at)
                 VALUES (?,?,'browser',?,?)""", (session_id, user_id, digest(secret), now().isoformat()))
    return session_id, secret


def current_browser(conn, request):
    secret = request.cookies.get(BROWSER_COOKIE, '')
    if not secret:
        return None
    return conn.execute("""SELECT c.id,c.user_id FROM identity_credentials c
        JOIN user_identity_keys k ON k.user_id=c.user_id
        WHERE c.kind='browser' AND c.secret_hash=? AND c.created_at>?""",
        (digest(secret), (now() - timedelta(days=365)).isoformat())).fetchone()


def browser_identity_available(conn, request):
    row = current_browser(conn, request)
    return bool(row and conn.execute("SELECT 1 FROM users WHERE id=? AND role='user' AND status='active'", (row['user_id'],)).fetchone())


class BrowserSession(BaseModel):
    create: bool = False
    replace: bool = False


class IdentitySession(TokenResponse):
    created: bool = False


@router.post('/session', response_model=IdentitySession)
def browser_session(payload: BrowserSession, request: Request, response: Response):
    _, _, secure = incoming(request, response)
    if payload.replace and not payload.create:
        raise HTTPException(400, '新身份必须由用户明确创建')
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = current_browser(conn, request)
        if row and not payload.replace:
            result = IdentitySession(**session(conn, row['user_id'], row['id']).model_dump())
            # Reuse a verified HTTP-era browser credential on the same host,
            # upgrading its transport flags without replacing its identity/session.
            if secure:
                cookie(response, BROWSER_COOKIE, request.cookies[BROWSER_COOKIE], True, 365 * 24 * 3600)
            return result
        if not payload.create:
            raise HTTPException(404, '当前浏览器尚未登录，请输入身份 Key 或开始使用')
        user_id = str(uuid.uuid4())
        make_user(conn, user_id)
        session_id, secret = add_browser_session(conn, user_id)
        result = IdentitySession(**session(conn, user_id, session_id).model_dump(), created=True)
        if row:
            conn.execute('DELETE FROM identity_credentials WHERE id=?', (row['id'],))
    cookie(response, BROWSER_COOKIE, secret, secure, 365 * 24 * 3600)
    return result


@router.post('/key/login', response_model=IdentitySession)
async def key_login(request: Request, response: Response):
    _, _, secure = incoming(request, response)
    # Bound actual bytes before JSON parsing, including chunked/misdeclared bodies.
    # Never echo the submitted credential in an error response.
    too_large = HTTPException(413,
        detail={'code': 'request_too_large', 'message': '登录内容过大，请仅提交身份 Key 后重试。'},
        headers={'Cache-Control': 'no-store', 'Pragma': 'no-cache'})
    try:
        declared_size = request.headers.get('content-length')
        if declared_size is not None and int(declared_size) > KEY_LOGIN_MAX_BODY_BYTES:
            raise too_large
        body = bytearray()
        async for chunk in request.stream():
            if len(body) + len(chunk) > KEY_LOGIN_MAX_BODY_BYTES:
                raise too_large
            body.extend(chunk)
        payload = json.loads(body)
        key = payload.get('key') if isinstance(payload, dict) else None
        if not isinstance(key, str) or len(key) > 256:
            raise ValueError()
        key = key.strip()
        if not re.fullmatch(r'bf_[A-Za-z0-9_-]{43}', key):
            raise ValueError()
    except (ValueError, TypeError, RecursionError):
        raise identity_error('invalid_key', '身份 Key 格式不正确，请检查后重试。') from None
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        key_hash = digest(key)
        if conn.execute('SELECT 1 FROM revoked_identity_keys WHERE key_hash=?', (key_hash,)).fetchone():
            raise identity_error('identity_deleted', '该身份已被管理员删除，原凭据已失效。请重新建立身份。',
                                 browser_identity_available=browser_identity_available(conn, request))
        row = conn.execute('SELECT user_id FROM user_identity_keys WHERE key_hash=?', (key_hash,)).fetchone()
        if not row:
            # Pre-v16 deletions left no digest; do not claim the user mistyped.
            raise identity_error('unknown_key', '凭据无效或已失效，请确认 Key 或凭据文件。',
                                 browser_identity_available=browser_identity_available(conn, request))
        # Revoke only this browser's previous session, never merge/delete identities.
        previous = current_browser(conn, request)
        if previous:
            conn.execute('DELETE FROM identity_credentials WHERE id=?', (previous['id'],))
        session_id, secret = add_browser_session(conn, row['user_id'])
        result = IdentitySession(**session(conn, row['user_id'], session_id).model_dump())
    cookie(response, BROWSER_COOKIE, secret, secure, 365 * 24 * 3600)
    return result


@router.get('/key')
def own_key(response: Response, user: dict = Depends(require_user)):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    if user['role'] != 'user':
        raise HTTPException(403, '管理员使用账号密码登录')
    with get_db() as conn:
        row = conn.execute('SELECT * FROM user_identity_keys WHERE user_id=?', (user['id'],)).fetchone()
        if not row:
            raise HTTPException(404, '当前身份没有身份 Key')
        try:
            return {'key': reveal_identity_key(row)}
        except RuntimeError:
            raise HTTPException(503, '身份凭据暂时无法读取，请稍后重试') from None


@router.post('/logout')
def logout(request: Request, response: Response):
    _, _, secure = incoming(request, response)
    token = decode_token(request.headers.get('authorization', '').removeprefix('Bearer '))
    remembered_secret = None
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = current_browser(conn, request)
        owner_id = row['user_id'] if row else None
        # A still-valid bearer can prove the identity even if its Cookie was
        # cleared. An old/revoked token must never create a remembered identity.
        bearer = None
        if token and token.get('amr') == 'key' and token.get('sid'):
            bearer = conn.execute("""SELECT c.id,c.user_id FROM identity_credentials c
                JOIN users u ON u.id=c.user_id JOIN user_identity_keys k ON k.user_id=u.id
                WHERE c.id=? AND c.user_id=? AND c.kind='browser' AND c.created_at>?
                  AND u.role='user' AND u.status='active' AND u.token_version=?""",
                (token['sid'], token.get('sub'), (now()-timedelta(days=365)).isoformat(), token.get('ver', 0))).fetchone()
        if bearer:
            owner_id = bearer['user_id']
        if row:
            conn.execute('DELETE FROM identity_credentials WHERE id=?', (row['id'],))
        if token and token.get('amr') == 'key' and token.get('sid'):
            conn.execute("DELETE FROM identity_credentials WHERE id=? AND user_id=? AND kind='browser'",
                         (token['sid'], token.get('sub')))
        if owner_id and conn.execute("SELECT id FROM users WHERE id=? AND role='user' AND status='active'", (owner_id,)).fetchone():
            # Replace the current binding, invalidating its JWT and old Cookie.
            # Return no login token: the logged-out browser must explicitly continue.
            _, remembered_secret = add_browser_session(conn, owner_id)
    cookie(response, BROWSER_COOKIE, remembered_secret or '', secure, 365 * 24 * 3600 if remembered_secret else 0)
    return {'remembered': bool(remembered_secret)}
