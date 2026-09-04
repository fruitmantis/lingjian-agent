"""Authentication utilities: password hashing, JWT, and FastAPI dependency."""

import os
import uuid
import json
from datetime import datetime, timezone, timedelta

import jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .config import get_jwt_secret_key


ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: str, username: str, role: str, token_version: int = 0) -> str:
    payload = {"sub": user_id, "username": username, "role": role, "ver": token_version, "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS), "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, get_jwt_secret_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_jwt_secret_key(), algorithms=[ALGORITHM])
    except Exception:
        return None


def get_bootstrap_admin():
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip().lower()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
    if not username:
        raise RuntimeError("BOOTSTRAP_ADMIN_USERNAME is required when initializing an empty database")
    if len(password) < 12 or not any(ch.isalpha() for ch in password) or not any(ch.isdigit() for ch in password):
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must be at least 12 characters and contain letters and digits")
    now = datetime.now(timezone.utc).isoformat()
    return {
        "id": str(uuid.uuid4()), "username": username, "hashed_password": hash_password(password),
        "display_name": "系统管理员", "role": "admin", "status": "active",
        "must_change_password": 1, "token_version": 0, "created_at": now, "updated_at": now,
    }


def require_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="请先登录", headers={"WWW-Authenticate": "Bearer"})
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="未登录或 token 已过期", headers={"WWW-Authenticate": "Bearer"})
    from .database import get_db
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, display_name, department, role, status, must_change_password, token_version, created_at, updated_at, last_login_at, locked_until FROM users WHERE id = ?",
            (payload.get("sub"),),
        ).fetchone()
    if row is None or row["status"] != "active":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="账号不存在或已停用")
    if int(payload.get("ver", 0)) != int(row["token_version"] or 0):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="登录状态已失效，请重新登录")
    return dict(row)


def require_active_user(user: dict = Depends(require_user)) -> dict:
    if user.get("must_change_password"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="请先修改临时密码")
    return user


def require_admin(user: dict = Depends(require_active_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def record_audit(conn, action: str, actor_user_id: str | None = None, target_user_id: str | None = None, summary: dict | str | None = None, ip_address: str | None = None) -> None:
    value = json.dumps(summary, ensure_ascii=False) if isinstance(summary, dict) else summary
    conn.execute(
        "INSERT INTO user_audit_logs (id, actor_user_id, action, target_user_id, summary, ip_address, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), actor_user_id, action, target_user_id, value, ip_address, datetime.now(timezone.utc).isoformat()),
    )


# Backward-compatible internal alias while routers move to explicit dependencies.
require_auth = require_active_user
