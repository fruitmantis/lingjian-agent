"""Authentication and internal user lifecycle management."""

import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from ..auth import create_token, hash_password, record_audit, require_admin, require_user, verify_password
from ..database import get_db
from ..identity_keys import masked_identity_key
from ..models import LoginRequest, TokenResponse, UserCreate, UserOut


router = APIRouter(tags=["auth"])
_USER_COLS = "id, username, display_name, department, role, status, must_change_password, created_at, updated_at, last_login_at, locked_until"
# Derived read-only projection; only expose methods accepted for the user's role.
_ADMIN_USER_FROM = "users LEFT JOIN user_identity_keys identity_key ON identity_key.user_id = users.id AND users.role = 'user'"
_ADMIN_USER_COLS = ", ".join("users." + column for column in _USER_COLS.split(", ")) + """, last_active_at,
    CASE WHEN users.role = 'admin' AND hashed_password IS NOT NULL AND hashed_password <> ''
        THEN 1 ELSE 0 END AS auth_password,
    CASE WHEN users.role = 'user' AND EXISTS (
        SELECT 1 FROM identity_credentials c WHERE c.user_id = users.id AND c.kind = 'passkey'
    ) THEN 1 ELSE 0 END AS auth_passkey,
    CASE WHEN users.role = 'user' AND EXISTS (
        SELECT 1 FROM identity_credentials c WHERE c.user_id = users.id AND c.kind = 'browser'
    ) THEN 1 ELSE 0 END AS auth_browser,
    CASE WHEN identity_key.user_id IS NOT NULL THEN 1 ELSE 0 END AS auth_key,
    identity_key.key_hash AS identity_key_hash,
    identity_key.encrypted_key AS identity_key_encrypted"""
_PASSWORD_MIN_LENGTH = 8
_MAX_LOGIN_FAILURES = 5
_LOCK_MINUTES = 15


class AdminUserOut(UserOut):
    auth_methods: list[Literal["password", "passkey", "browser", "key"]]
    last_active_at: str | None = None
    identity_key_hint: str | None = None


class UserListResponse(BaseModel):
    items: list[AdminUserOut]
    total: int
    page: int
    pageSize: int


class UserCreateResponse(BaseModel):
    user: UserOut
    temporaryPassword: str


class UserUpdate(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=100)
    department: str | None = Field(None, max_length=100)
    role: Literal["admin", "user"] | None = None


class UserStatusUpdate(BaseModel):
    status: Literal["active", "disabled"]


class SelfUpdate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=100)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=_PASSWORD_MIN_LENGTH, max_length=64)


class TemporaryPasswordResponse(BaseModel):
    temporaryPassword: str


class AuditLogOut(BaseModel):
    id: str
    action: str
    actorName: str | None
    targetName: str | None
    summary: str | None
    ipAddress: str | None
    createdAt: str


class AuditLogListResponse(BaseModel):
    items: list[AuditLogOut]
    total: int
    page: int
    pageSize: int


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _user_out(row) -> UserOut:
    return UserOut(**{column: row[column] for column in _USER_COLS.split(", ")})


def _admin_user_out(row) -> AdminUserOut:
    methods = [method for method in ("password", "passkey", "browser") if row["auth_" + method]]
    if row["auth_key"]:
        methods = ["key"]
    hint = masked_identity_key({'user_id': row['id'], 'key_hash': row['identity_key_hash'],
                                'encrypted_key': row['identity_key_encrypted']}) if row['auth_key'] else None
    return AdminUserOut(**_user_out(row).model_dump(), auth_methods=methods,
                        last_active_at=row["last_active_at"], identity_key_hint=hint)


def _validate_password(password: str) -> None:
    if len(password) < _PASSWORD_MIN_LENGTH or len(password) > 64:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="密码长度必须为 8 到 64 位")
    if not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="密码必须同时包含字母和数字")


def _temporary_password() -> str:
    chars = list("ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789")
    password = [secrets.choice(string.ascii_uppercase), secrets.choice(string.ascii_lowercase), secrets.choice(string.digits)]
    password.extend(secrets.choice(chars) for _ in range(9))
    secrets.SystemRandom().shuffle(password)
    return "".join(password)


def _active_admin_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin' AND status = 'active'").fetchone()[0]


@router.post("/auth/admin/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request) -> TokenResponse:
    username = req.username.strip().lower()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute(
            f"SELECT {_USER_COLS}, hashed_password, token_version, failed_login_count FROM users WHERE lower(username) = ?",
            (username,),
        ).fetchone()
        if row is None or row["role"] != "admin":
            record_audit(conn, "auth.login_failed", summary={"username": username}, ip_address=_client_ip(request))
            conn.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
        if row["status"] != "active":
            record_audit(conn, "auth.login_failed", target_user_id=row["id"], summary="账号已删除" if row["status"] == "deleted" else "账号已停用", ip_address=_client_ip(request))
            conn.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="账号已删除，无法登录" if row["status"] == "deleted" else "账号已停用，请联系管理员")
        if row["locked_until"]:
            try:
                if datetime.fromisoformat(row["locked_until"]) > now:
                    raise HTTPException(status.HTTP_423_LOCKED, detail="账号已临时锁定，请稍后再试或联系管理员")
            except ValueError:
                pass
        if not verify_password(req.password, row["hashed_password"]):
            failures = int(row["failed_login_count"] or 0) + 1
            locked_until = (now + timedelta(minutes=_LOCK_MINUTES)).isoformat() if failures >= _MAX_LOGIN_FAILURES else None
            conn.execute(
                "UPDATE users SET failed_login_count = ?, locked_until = ?, updated_at = ? WHERE id = ?",
                (failures, locked_until, now_iso, row["id"]),
            )
            record_audit(conn, "auth.login_failed", target_user_id=row["id"], summary={"locked": bool(locked_until)}, ip_address=_client_ip(request))
            conn.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
        conn.execute(
            "UPDATE users SET failed_login_count = 0, locked_until = NULL, last_login_at = ?, updated_at = ? WHERE id = ?",
            (now_iso, now_iso, row["id"]),
        )
        record_audit(conn, "auth.login_success", actor_user_id=row["id"], target_user_id=row["id"], ip_address=_client_ip(request))
        fresh = conn.execute(f"SELECT {_USER_COLS} FROM users WHERE id = ?", (row["id"],)).fetchone()
    token = create_token(row["id"], row["username"], row["role"], int(row["token_version"] or 0))
    return TokenResponse(access_token=token, user=_user_out(fresh))


@router.get("/auth/me", response_model=UserOut)
def get_current_user(user: dict = Depends(require_user)) -> UserOut:
    return UserOut(**{key: user.get(key) for key in UserOut.model_fields})


@router.patch("/auth/me", response_model=UserOut)
def update_current_user(payload: SelfUpdate, request: Request, user: dict = Depends(require_user)) -> UserOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("UPDATE users SET display_name = ?, updated_at = ? WHERE id = ?", (payload.display_name.strip(), now, user["id"]))
        record_audit(conn, "user.self_update", actor_user_id=user["id"], target_user_id=user["id"], ip_address=_client_ip(request))
        row = conn.execute(f"SELECT {_USER_COLS} FROM users WHERE id = ?", (user["id"],)).fetchone()
    return _user_out(row)


@router.post("/auth/change-password", response_model=TokenResponse)
def change_password(payload: ChangePasswordRequest, request: Request, user: dict = Depends(require_user)) -> TokenResponse:
    if user["role"] != "admin":
        raise HTTPException(403, "本机身份不使用密码")
    _validate_password(payload.new_password)
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute("SELECT hashed_password, token_version FROM users WHERE id = ?", (user["id"],)).fetchone()
        if row is None or not verify_password(payload.current_password, row["hashed_password"]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="当前密码不正确")
        if verify_password(payload.new_password, row["hashed_password"]):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="新密码不能与当前密码相同")
        version = int(row["token_version"] or 0) + 1
        conn.execute(
            "UPDATE users SET hashed_password = ?, must_change_password = 0, token_version = ?, password_changed_at = ?, updated_at = ? WHERE id = ?",
            (hash_password(payload.new_password), version, now, now, user["id"]),
        )
        record_audit(conn, "auth.password_changed", actor_user_id=user["id"], target_user_id=user["id"], ip_address=_client_ip(request))
        fresh = conn.execute(f"SELECT {_USER_COLS} FROM users WHERE id = ?", (user["id"],)).fetchone()
    token = create_token(user["id"], user["username"], user["role"], version)
    return TokenResponse(access_token=token, user=_user_out(fresh))


@router.post("/auth/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(request: Request, user: dict = Depends(require_user)) -> Response:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("UPDATE users SET token_version = token_version + 1, updated_at = ? WHERE id = ?", (now, user["id"]))
        record_audit(conn, "auth.logout_all", actor_user_id=user["id"], target_user_id=user["id"], ip_address=_client_ip(request))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/admin/users", response_model=UserListResponse)
def list_users(
    response: Response,
    keyword: str | None = None,
    role: Literal["admin", "user"] | None = None,
    user_status: Literal["active", "disabled"] | None = Query(None, alias="status"),
    department: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    _: dict = Depends(require_admin),
) -> UserListResponse:
    response.headers["Cache-Control"] = "no-store"
    conditions: list[str] = ["users.status <> 'deleted'"]
    params: list[object] = []
    if keyword:
        conditions.append("(username LIKE ? OR display_name LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    if role:
        conditions.append("role = ?"); params.append(role)
    if user_status:
        conditions.append("status = ?"); params.append(user_status)
    if department:
        conditions.append("department = ?"); params.append(department)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    with get_db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM users{where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT {_ADMIN_USER_COLS} FROM {_ADMIN_USER_FROM}{where} ORDER BY users.created_at DESC LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    return UserListResponse(items=[_admin_user_out(row) for row in rows], total=total, page=page, pageSize=page_size)


@router.post("/admin/users", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, request: Request, admin: dict = Depends(require_admin)) -> UserCreateResponse:
    if payload.role != "admin":
        raise HTTPException(400, "普通身份由本机自动建立")
    username = payload.username.strip().lower()
    temporary_password = _temporary_password()
    now = datetime.now(timezone.utc).isoformat()
    user_id = str(uuid.uuid4())
    with get_db() as conn:
        if conn.execute("SELECT id FROM users WHERE lower(username) = ?", (username,)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, detail="用户名已存在")
        conn.execute(
            "INSERT INTO users (id, username, hashed_password, display_name, department, role, status, must_change_password, token_version, failed_login_count, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'active', 1, 0, 0, ?, ?, ?)",
            (user_id, username, hash_password(temporary_password), payload.display_name.strip(), payload.department.strip() if payload.department else None, payload.role, admin["id"], now, now),
        )
        record_audit(conn, "admin.user_created", actor_user_id=admin["id"], target_user_id=user_id, summary={"role": payload.role}, ip_address=_client_ip(request))
        row = conn.execute(f"SELECT {_USER_COLS} FROM users WHERE id = ?", (user_id,)).fetchone()
    return UserCreateResponse(user=_user_out(row), temporaryPassword=temporary_password)


@router.get("/admin/users/{user_id}", response_model=AdminUserOut)
def get_user(user_id: str, response: Response, _: dict = Depends(require_admin)) -> AdminUserOut:
    response.headers["Cache-Control"] = "no-store"
    with get_db() as conn:
        row = conn.execute(f"SELECT {_ADMIN_USER_COLS} FROM {_ADMIN_USER_FROM} WHERE users.id = ? AND users.status <> 'deleted'", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return _admin_user_out(row)


@router.patch("/admin/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, payload: UserUpdate, request: Request, admin: dict = Depends(require_admin)) -> UserOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute("SELECT id, role, status FROM users WHERE id = ? AND status <> 'deleted'", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="用户不存在")
        if payload.role is not None and payload.role != row["role"]:
            raise HTTPException(400, "管理员账号与本机身份不能互相转换")
        if user_id == admin["id"] and payload.role is not None and payload.role != admin["role"]:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不能修改自己的管理员角色")
        if row["role"] == "admin" and payload.role == "user" and row["status"] == "active" and _active_admin_count(conn) <= 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不能降级最后一个有效管理员")
        updates: list[str] = []
        params: list[object] = []
        if payload.display_name is not None:
            updates.append("display_name = ?"); params.append(payload.display_name.strip())
        if payload.department is not None:
            updates.append("department = ?"); params.append(payload.department.strip() or None)
        if payload.role is not None and payload.role != row["role"]:
            updates.extend(["role = ?", "token_version = token_version + 1"]); params.append(payload.role)
        if updates:
            updates.append("updated_at = ?"); params.append(now); params.append(user_id)
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
        record_audit(conn, "admin.user_updated", actor_user_id=admin["id"], target_user_id=user_id, summary=payload.model_dump(exclude_none=True), ip_address=_client_ip(request))
        fresh = conn.execute(f"SELECT {_USER_COLS} FROM users WHERE id = ?", (user_id,)).fetchone()
    return _user_out(fresh)


@router.patch("/admin/users/{user_id}/status", response_model=UserOut)
def update_user_status(user_id: str, payload: UserStatusUpdate, request: Request, admin: dict = Depends(require_admin)) -> UserOut:
    if user_id == admin["id"] and payload.status == "disabled":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不能停用自己的账号")
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute("SELECT id, role, status FROM users WHERE id = ? AND status <> 'deleted'", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="用户不存在")
        if row["role"] == "admin" and row["status"] == "active" and payload.status == "disabled" and _active_admin_count(conn) <= 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不能停用最后一个有效管理员")
        conn.execute(
            "UPDATE users SET status = ?, token_version = token_version + 1, failed_login_count = 0, locked_until = NULL, updated_at = ? WHERE id = ?",
            (payload.status, now, user_id),
        )
        record_audit(conn, f"admin.user_{payload.status}", actor_user_id=admin["id"], target_user_id=user_id, ip_address=_client_ip(request))
        fresh = conn.execute(f"SELECT {_USER_COLS} FROM users WHERE id = ?", (user_id,)).fetchone()
    return _user_out(fresh)


@router.post("/admin/users/{user_id}/reset-password", response_model=TemporaryPasswordResponse)
def reset_password(user_id: str, request: Request, admin: dict = Depends(require_admin)) -> TemporaryPasswordResponse:
    temporary_password = _temporary_password()
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute("SELECT id FROM users WHERE id = ? AND role = 'admin' AND status <> 'deleted'", (user_id,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="用户不存在")
        conn.execute(
            "UPDATE users SET hashed_password = ?, must_change_password = 1, token_version = token_version + 1, failed_login_count = 0, locked_until = NULL, password_changed_at = ?, updated_at = ? WHERE id = ?",
            (hash_password(temporary_password), now, now, user_id),
        )
        record_audit(conn, "admin.password_reset", actor_user_id=admin["id"], target_user_id=user_id, ip_address=_client_ip(request))
    return TemporaryPasswordResponse(temporaryPassword=temporary_password)


@router.post("/admin/users/{user_id}/unlock", response_model=UserOut)
def unlock_user(user_id: str, request: Request, admin: dict = Depends(require_admin)) -> UserOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute("SELECT id FROM users WHERE id = ? AND role = 'admin' AND status <> 'deleted'", (user_id,)).fetchone() is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="用户不存在")
        conn.execute("UPDATE users SET failed_login_count = 0, locked_until = NULL, updated_at = ? WHERE id = ?", (now, user_id))
        record_audit(conn, "admin.user_unlocked", actor_user_id=admin["id"], target_user_id=user_id, ip_address=_client_ip(request))
        row = conn.execute(f"SELECT {_USER_COLS} FROM users WHERE id = ?", (user_id,)).fetchone()
    return _user_out(row)


@router.get("/admin/user-audit-logs", response_model=AuditLogListResponse)
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    _: dict = Depends(require_admin),
) -> AuditLogListResponse:
    with get_db() as conn:
        total = conn.execute("SELECT COUNT(*) FROM user_audit_logs").fetchone()[0]
        rows = conn.execute(
            """SELECT l.id, l.action, l.summary, l.ip_address, l.created_at,
                      CASE WHEN a.status='deleted' THEN '已删除用户' ELSE COALESCE(a.display_name, a.username, CASE WHEN l.actor_user_id IS NOT NULL THEN '已删除用户' END) END AS actor_name,
                      CASE WHEN t.status='deleted' THEN '已删除用户' ELSE COALESCE(t.display_name, t.username, CASE WHEN l.target_user_id IS NOT NULL THEN '已删除用户' END) END AS target_name
               FROM user_audit_logs l
               LEFT JOIN users a ON a.id = l.actor_user_id
               LEFT JOIN users t ON t.id = l.target_user_id
               ORDER BY l.created_at DESC LIMIT ? OFFSET ?""",
            (page_size, (page - 1) * page_size),
        ).fetchall()
    return AuditLogListResponse(
        items=[AuditLogOut(id=row["id"], action=row["action"], actorName=row["actor_name"], targetName=row["target_name"], summary=row["summary"], ipAddress=row["ip_address"], createdAt=row["created_at"]) for row in rows],
        total=total,
        page=page,
        pageSize=page_size,
    )
