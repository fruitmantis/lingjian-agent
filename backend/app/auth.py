"""Authentication utilities: password hashing, JWT, and FastAPI dependency."""

import os
import uuid
from datetime import datetime, timezone, timedelta

import jwt
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


SECRET_KEY = os.getenv("JWT_SECRET_KEY", "lingjian-mvp-secret-key-change-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24
security = HTTPBearer()


def hash_password(password: str) -> str:
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_token(user_id: str, username: str, role: str) -> str:
    payload = {"sub": user_id, "username": username, "role": role, "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS), "iat": datetime.now(timezone.utc)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        return None


def get_default_admin():
    return {"id": str(uuid.uuid4()), "username": "admin", "hashed_password": hash_password("admin123"), "display_name": "管理员", "role": "admin", "created_at": datetime.now(timezone.utc).isoformat()}


def require_auth(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="未登录或 token 已过期", headers={"WWW-Authenticate": "Bearer"})
    return payload
