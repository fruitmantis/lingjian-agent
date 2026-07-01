"""Authentication utilities: password hashing and JWT."""

import os
import uuid
from datetime import datetime, timezone, timedelta

import jwt
import bcrypt


SECRET_KEY = os.getenv("JWT_SECRET_KEY", "lingjian-mvp-secret-key-change-in-production")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24


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
