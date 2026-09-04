"""Authentication and internal user lifecycle management."""

import secrets
import string
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from ..auth import create_token, hash_password, record_audit, require_admin, require_user, verify_password
from ..database import get_db
from ..models import LoginRequest, TokenResponse, UserCreate, UserOut


router = APIRouter(tags=["auth"])
_USER_COLS = "id, username, display_name, department, role, status, must_change_password, created_at, updated_at, last_login_at, locked_until"
_PASSWORD_MIN_LENGTH = 8
_MAX_LOGIN_FAILURES = 5
_LOCK_MINUTES = 15
_APPLICATION_RATE_LOCK = threading.Lock()
_APPLICATION_ATTEMPTS: dict[str, deque[float]] = defaultdict(deque)


class UserListResponse(BaseModel):
    items: list[UserOut]
    total: int
    page: int
    pageSize: int


class UserCreateResponse(BaseModel):
    user: UserOut
    temporaryPassword: str


class UserApplicationCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str = Field(..., min_length=1, max_length=100)
    department: str = Field(..., min_length=1, max_length=100)
    contact: str = Field(..., min_length=2, max_length=100)
    reason: str | None = Field(None, max_length=500)
    password: str = Field(..., min_length=_PASSWORD_MIN_LENGTH, max_length=64)


class UserApplicationSubmitResponse(BaseModel):
    id: str
    status: Literal["pending"] = "pending"
    message: str = "申请已提交，请等待管理员审批"


class UserApplicationOut(BaseModel):
    id: str
    username: str
    display_name: str
    department: str | None
    contact: str | None
    reason: str | None
    status: Literal["pending", "approved", "rejected"]
    review_note: str | None
    reviewed_by_name: str | None
    reviewed_at: str | None
    user_id: str | None
    created_at: str


class UserApplicationListResponse(BaseModel):
    items: list[UserApplicationOut]
    total: int
    page: int
    pageSize: int


class UserApplicationReview(BaseModel):
    note: str | None = Field(None, max_length=500)


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


def _positive_int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _enforce_application_rate_limit(client_ip: str | None) -> None:
    """Bound bcrypt work per client for the current single-process MVP."""
    limit = _positive_int_env("USER_APPLICATION_RATE_LIMIT", 5)
    window_seconds = _positive_int_env("USER_APPLICATION_RATE_WINDOW_SECONDS", 600)
    key = client_ip or "unknown"
    now = time.monotonic()
    with _APPLICATION_RATE_LOCK:
        attempts = _APPLICATION_ATTEMPTS[key]
        while attempts and attempts[0] <= now - window_seconds:
            attempts.popleft()
        if len(attempts) >= limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail="账号申请过于频繁，请稍后再试",
                headers={"Retry-After": str(window_seconds)},
            )
        attempts.append(now)


@router.post("/auth/user-applications", response_model=UserApplicationSubmitResponse, status_code=status.HTTP_201_CREATED)
def submit_user_application(payload: UserApplicationCreate, request: Request) -> UserApplicationSubmitResponse:
    _validate_password(payload.password)
    username = payload.username.strip().lower()
    contact = payload.contact.strip().lower()
    client_ip = _client_ip(request)
    _enforce_application_rate_limit(client_ip)
    now = datetime.now(timezone.utc).isoformat()
    application_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        pending_limit = _positive_int_env("USER_APPLICATION_PENDING_LIMIT", 200)
        pending_count = conn.execute("SELECT COUNT(*) FROM user_applications WHERE status = 'pending'").fetchone()[0]
        if pending_count >= pending_limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="待审批申请已达到上限，请联系管理员")
        if conn.execute("SELECT id FROM users WHERE lower(username) = ?", (username,)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, detail="该用户名已被使用，请直接登录或更换用户名")
        if conn.execute("SELECT id FROM user_applications WHERE lower(username) = ? AND status = 'pending'", (username,)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, detail="该用户名已有待审批申请，请勿重复提交")
        if conn.execute(
            "SELECT id FROM user_applications WHERE lower(contact) = ? AND status IN ('pending', 'approved')",
            (contact,),
        ).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, detail="该企业邮箱或工号已提交过账号申请")
        conn.execute(
            """INSERT INTO user_applications
               (id, username, display_name, department, contact, reason, password_hash, status,
                applicant_ip, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (
                application_id, username, payload.display_name.strip(), payload.department.strip(),
                contact, payload.reason.strip() if payload.reason else None,
                hash_password(payload.password), client_ip, now, now,
            ),
        )
        record_audit(
            conn, "user_application.submitted",
            summary={"applicationId": application_id, "username": username},
            ip_address=client_ip,
        )
    return UserApplicationSubmitResponse(id=application_id)


@router.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request) -> TokenResponse:
    username = req.username.strip().lower()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    with get_db() as conn:
        row = conn.execute(
            f"SELECT {_USER_COLS}, hashed_password, token_version, failed_login_count FROM users WHERE lower(username) = ?",
            (username,),
        ).fetchone()
        if row is None:
            record_audit(conn, "auth.login_failed", summary={"username": username}, ip_address=_client_ip(request))
            conn.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
        if row["status"] != "active":
            record_audit(conn, "auth.login_failed", target_user_id=row["id"], summary="账号已停用", ip_address=_client_ip(request))
            conn.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="账号已停用，请联系管理员")
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
    keyword: str | None = None,
    role: Literal["admin", "user"] | None = None,
    user_status: Literal["active", "disabled"] | None = Query(None, alias="status"),
    department: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    _: dict = Depends(require_admin),
) -> UserListResponse:
    conditions: list[str] = []
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
            f"SELECT {_USER_COLS} FROM users{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    return UserListResponse(items=[_user_out(row) for row in rows], total=total, page=page, pageSize=page_size)


@router.post("/admin/users", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, request: Request, admin: dict = Depends(require_admin)) -> UserCreateResponse:
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


@router.get("/admin/users/{user_id}", response_model=UserOut)
def get_user(user_id: str, _: dict = Depends(require_admin)) -> UserOut:
    with get_db() as conn:
        row = conn.execute(f"SELECT {_USER_COLS} FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="用户不存在")
    return _user_out(row)


@router.patch("/admin/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, payload: UserUpdate, request: Request, admin: dict = Depends(require_admin)) -> UserOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute("SELECT id, role, status FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="用户不存在")
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
        row = conn.execute("SELECT id, role, status FROM users WHERE id = ?", (user_id,)).fetchone()
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
        if conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone() is None:
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
        if conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone() is None:
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
                      a.display_name AS actor_name, t.display_name AS target_name
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


@router.get("/admin/user-applications", response_model=UserApplicationListResponse)
def list_user_applications(
    application_status: Literal["pending", "approved", "rejected"] | None = Query(None, alias="status"),
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    _: dict = Depends(require_admin),
) -> UserApplicationListResponse:
    conditions: list[str] = []
    params: list[object] = []
    if application_status:
        conditions.append("ua.status = ?"); params.append(application_status)
    if keyword:
        conditions.append("(ua.username LIKE ? OR ua.display_name LIKE ? OR ua.department LIKE ?)")
        params.extend([f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"])
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    with get_db() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM user_applications ua{where}", params).fetchone()[0]
        rows = conn.execute(
            f"""SELECT ua.id, ua.username, ua.display_name, ua.department, ua.contact, ua.reason,
                       ua.status, ua.review_note, reviewer.display_name AS reviewed_by_name,
                       ua.reviewed_at, ua.user_id, ua.created_at
                FROM user_applications ua
                LEFT JOIN users reviewer ON reviewer.id = ua.reviewed_by
                {where} ORDER BY CASE ua.status WHEN 'pending' THEN 0 ELSE 1 END, ua.created_at DESC
                LIMIT ? OFFSET ?""",
            [*params, page_size, (page - 1) * page_size],
        ).fetchall()
    return UserApplicationListResponse(
        items=[UserApplicationOut(**dict(row)) for row in rows],
        total=total,
        page=page,
        pageSize=page_size,
    )


@router.post("/admin/user-applications/{application_id}/approve", response_model=UserOut)
def approve_user_application(
    application_id: str,
    payload: UserApplicationReview,
    request: Request,
    admin: dict = Depends(require_admin),
) -> UserOut:
    now = datetime.now(timezone.utc).isoformat()
    user_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute("BEGIN IMMEDIATE")
        application = conn.execute(
            "SELECT * FROM user_applications WHERE id = ?", (application_id,)
        ).fetchone()
        if application is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="账号申请不存在")
        if application["status"] != "pending":
            raise HTTPException(status.HTTP_409_CONFLICT, detail="该申请已处理")
        if not application["password_hash"]:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="申请密码已失效，请驳回后让申请人重新提交")
        if conn.execute("SELECT id FROM users WHERE lower(username) = ?", (application["username"].lower(),)).fetchone():
            raise HTTPException(status.HTTP_409_CONFLICT, detail="用户名已被占用，请驳回该申请")
        conn.execute(
            """INSERT INTO users
               (id, username, hashed_password, display_name, department, role, status,
                must_change_password, token_version, failed_login_count, created_by, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, 'user', 'active', 1, 0, 0, ?, ?, ?)""",
            (
                user_id, application["username"], application["password_hash"],
                application["display_name"], application["department"], admin["id"], now, now,
            ),
        )
        conn.execute(
            """UPDATE user_applications
               SET status = 'approved', review_note = ?, reviewed_by = ?, reviewed_at = ?,
                   user_id = ?, password_hash = NULL, updated_at = ? WHERE id = ?""",
            (payload.note.strip() if payload.note else None, admin["id"], now, user_id, now, application_id),
        )
        record_audit(
            conn, "admin.user_application_approved", actor_user_id=admin["id"],
            target_user_id=user_id, summary={"applicationId": application_id},
            ip_address=_client_ip(request),
        )
        row = conn.execute(f"SELECT {_USER_COLS} FROM users WHERE id = ?", (user_id,)).fetchone()
    return _user_out(row)


@router.post("/admin/user-applications/{application_id}/reject", response_model=UserApplicationOut)
def reject_user_application(
    application_id: str,
    payload: UserApplicationReview,
    request: Request,
    admin: dict = Depends(require_admin),
) -> UserApplicationOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        application = conn.execute("SELECT status FROM user_applications WHERE id = ?", (application_id,)).fetchone()
        if application is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="账号申请不存在")
        if application["status"] != "pending":
            raise HTTPException(status.HTTP_409_CONFLICT, detail="该申请已处理")
        conn.execute(
            """UPDATE user_applications
               SET status = 'rejected', review_note = ?, reviewed_by = ?, reviewed_at = ?,
                   password_hash = NULL, updated_at = ? WHERE id = ?""",
            (payload.note.strip() if payload.note else None, admin["id"], now, now, application_id),
        )
        record_audit(
            conn, "admin.user_application_rejected", actor_user_id=admin["id"],
            summary={"applicationId": application_id}, ip_address=_client_ip(request),
        )
        row = conn.execute(
            """SELECT ua.id, ua.username, ua.display_name, ua.department, ua.contact, ua.reason,
                      ua.status, ua.review_note, reviewer.display_name AS reviewed_by_name,
                      ua.reviewed_at, ua.user_id, ua.created_at
               FROM user_applications ua LEFT JOIN users reviewer ON reviewer.id = ua.reviewed_by
               WHERE ua.id = ?""",
            (application_id,),
        ).fetchone()
    return UserApplicationOut(**dict(row))
