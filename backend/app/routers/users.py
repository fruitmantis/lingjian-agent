"""User authentication and management router."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, status

from ..auth import hash_password, verify_password, create_token, require_auth
from ..database import get_db
from ..models import UserCreate, UserOut, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])
_USER_COLS = "id, username, display_name, role, created_at"


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest) -> TokenResponse:
    with get_db() as conn:
        row = conn.execute("SELECT id, username, hashed_password, display_name, role, created_at FROM users WHERE username = ?", (req.username,)).fetchone()
    if row is None or not verify_password(req.password, row["hashed_password"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    token = create_token(row["id"], row["username"], row["role"])
    user = UserOut(id=row["id"], username=row["username"], display_name=row["display_name"], role=row["role"], created_at=row["created_at"])
    return TokenResponse(access_token=token, user=user)


@router.get("/me", response_model=UserOut)
def get_current_user(payload: dict = Depends(require_auth)) -> UserOut:
    with get_db() as conn:
        row = conn.execute(f"SELECT {_USER_COLS} FROM users WHERE id = ?", (payload["sub"],)).fetchone()
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return UserOut(**dict(row))


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_auth)])
def list_users() -> list[UserOut]:
    with get_db() as conn:
        rows = conn.execute(f"SELECT {_USER_COLS} FROM users ORDER BY created_at DESC").fetchall()
    return [UserOut(**dict(r)) for r in rows]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_auth)])
def create_user(payload: UserCreate) -> UserOut:
    user = UserOut(id=str(uuid.uuid4()), username=payload.username, display_name=payload.display_name, role=payload.role, created_at=datetime.now(timezone.utc).isoformat())
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (payload.username,)).fetchone()
        if existing is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="用户名已存在")
        conn.execute("INSERT INTO users (id, username, hashed_password, display_name, role, created_at) VALUES (?, ?, ?, ?, ?, ?)", (user.id, user.username, hash_password(payload.password), user.display_name, user.role, user.created_at))
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_auth)])
def delete_user(user_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="用户不存在")
        if row["role"] == "admin":
            admin_count = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE role = 'admin'").fetchone()
            if admin_count["cnt"] <= 1:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="不能删除最后一个管理员")
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return None
