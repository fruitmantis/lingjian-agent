"""Capability tags CRUD router."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ..database import get_db


router = APIRouter(prefix="/capability-tags", tags=["capability-tags"])


class CapabilityTagOut(BaseModel):
    id: str
    name: str
    category: str
    description: str | None
    enabled: bool
    sortOrder: int
    isPreset: bool
    createdAt: str
    updatedAt: str


class CapabilityTagCreate(BaseModel):
    name: str
    category: str
    description: str | None = None
    sortOrder: int = 0


class CapabilityTagUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    description: str | None = None
    sortOrder: int | None = None


class EnableUpdate(BaseModel):
    enabled: bool


_COLS = "id, name, category, description, enabled, sort_order, is_preset, created_at, updated_at"


def _to_out(r) -> CapabilityTagOut:
    return CapabilityTagOut(
        id=r["id"], name=r["name"], category=r["category"], description=r["description"],
        enabled=bool(r["enabled"]), sortOrder=r["sort_order"], isPreset=bool(r["is_preset"]),
        createdAt=r["created_at"], updatedAt=r["updated_at"]
    )


@router.get("", response_model=list[CapabilityTagOut])
def list_tags(search: str | None = None, category: str | None = None):
    with get_db() as conn:
        query = f"SELECT {_COLS} FROM capability_tags"
        conditions = []
        params = []
        if search:
            conditions.append("name LIKE ?")
            params.append(f"%{search}%")
        if category:
            conditions.append("category = ?")
            params.append(category)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY sort_order ASC, created_at ASC"
        rows = conn.execute(query, params).fetchall()
    return [_to_out(r) for r in rows]


@router.post("", response_model=CapabilityTagOut, status_code=status.HTTP_201_CREATED)
def create_tag(payload: CapabilityTagCreate) -> CapabilityTagOut:
    now = datetime.now(timezone.utc).isoformat()
    tag_id = str(uuid.uuid4())
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO capability_tags (id, name, category, description, enabled, sort_order, is_preset, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, 0, ?, ?)",
                (tag_id, payload.name, payload.category, payload.description, payload.sortOrder, now, now)
            )
            row = conn.execute(f"SELECT {_COLS} FROM capability_tags WHERE id = ?", (tag_id,)).fetchone()
        return _to_out(row)
    except Exception:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="标签名称已存在")


@router.put("/{tag_id}", response_model=CapabilityTagOut)
def update_tag(tag_id: str, payload: CapabilityTagUpdate) -> CapabilityTagOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute(f"SELECT {_COLS} FROM capability_tags WHERE id = ?", (tag_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="标签不存在")
        updates = []
        params = []
        if payload.name is not None:
            updates.append("name = ?")
            params.append(payload.name)
        if payload.category is not None:
            updates.append("category = ?")
            params.append(payload.category)
        if payload.description is not None:
            updates.append("description = ?")
            params.append(payload.description)
        if payload.sortOrder is not None:
            updates.append("sort_order = ?")
            params.append(payload.sortOrder)
        updates.append("updated_at = ?")
        params.append(now)
        params.append(tag_id)
        if len(updates) > 1:
            conn.execute(f"UPDATE capability_tags SET {', '.join(updates)} WHERE id = ?", params)
        row = conn.execute(f"SELECT {_COLS} FROM capability_tags WHERE id = ?", (tag_id,)).fetchone()
    return _to_out(row)


@router.patch("/{tag_id}/enable", response_model=CapabilityTagOut)
def toggle_enable(tag_id: str, payload: EnableUpdate) -> CapabilityTagOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute(f"SELECT {_COLS} FROM capability_tags WHERE id = ?", (tag_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="标签不存在")
        conn.execute("UPDATE capability_tags SET enabled = ?, updated_at = ? WHERE id = ?", (1 if payload.enabled else 0, now, tag_id))
        row = conn.execute(f"SELECT {_COLS} FROM capability_tags WHERE id = ?", (tag_id,)).fetchone()
    return _to_out(row)


@router.post("/seed", response_model=dict)
def seed_tags() -> dict:
    """Re-run preset tag seeding."""
    from ..database import initialize_storage
    initialize_storage()
    return {"status": "ok", "message": "预置标签已初始化"}

# ============ Category CRUD ============

class CategoryOut(BaseModel):
    id: str
    name: str
    code: str | None
    description: str | None
    enabled: bool
    sortOrder: int
    isPreset: bool
    createdAt: str
    updatedAt: str


class CategoryCreate(BaseModel):
    name: str
    code: str | None = None
    description: str | None = None
    sortOrder: int = 0


class CategoryUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    description: str | None = None
    sortOrder: int | None = None


_CAT_COLS = "id, name, code, description, enabled, sort_order, is_preset, created_at, updated_at"


def _cat_to_out(r) -> CategoryOut:
    return CategoryOut(
        id=r["id"], name=r["name"], code=r["code"], description=r["description"],
        enabled=bool(r["enabled"]), sortOrder=r["sort_order"], isPreset=bool(r["is_preset"]),
        createdAt=r["created_at"], updatedAt=r["updated_at"]
    )


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(search: str | None = None, enabled: bool | None = None):
    with get_db() as conn:
        query = f"SELECT {_CAT_COLS} FROM capability_tag_categories"
        conditions = []
        params = []
        if search:
            conditions.append("name LIKE ?")
            params.append(f"%{search}%")
        if enabled is not None:
            conditions.append("enabled = ?")
            params.append(1 if enabled else 0)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY sort_order ASC, created_at ASC"
        rows = conn.execute(query, params).fetchall()
    return [_cat_to_out(r) for r in rows]


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate) -> CategoryOut:
    now = datetime.now(timezone.utc).isoformat()
    cat_id = str(uuid.uuid4())
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO capability_tag_categories (id, name, code, description, enabled, sort_order, is_preset, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, 0, ?, ?)",
                (cat_id, payload.name, payload.code, payload.description, payload.sortOrder, now, now)
            )
            row = conn.execute(f"SELECT {_CAT_COLS} FROM capability_tag_categories WHERE id = ?", (cat_id,)).fetchone()
        return _cat_to_out(row)
    except Exception:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="分类名称已存在")


@router.put("/categories/{cat_id}", response_model=CategoryOut)
def update_category(cat_id: str, payload: CategoryUpdate) -> CategoryOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute(f"SELECT {_CAT_COLS} FROM capability_tag_categories WHERE id = ?", (cat_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="分类不存在")
        updates = []
        params = []
        if payload.name is not None:
            updates.append("name = ?")
            params.append(payload.name)
        if payload.code is not None:
            updates.append("code = ?")
            params.append(payload.code)
        if payload.description is not None:
            updates.append("description = ?")
            params.append(payload.description)
        if payload.sortOrder is not None:
            updates.append("sort_order = ?")
            params.append(payload.sortOrder)
        updates.append("updated_at = ?")
        params.append(now)
        params.append(cat_id)
        if len(updates) > 1:
            conn.execute(f"UPDATE capability_tag_categories SET {', '.join(updates)} WHERE id = ?", params)
        row = conn.execute(f"SELECT {_CAT_COLS} FROM capability_tag_categories WHERE id = ?", (cat_id,)).fetchone()
    return _cat_to_out(row)


@router.patch("/categories/{cat_id}/enable", response_model=CategoryOut)
def toggle_category_enable(cat_id: str, payload: EnableUpdate) -> CategoryOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute(f"SELECT {_CAT_COLS} FROM capability_tag_categories WHERE id = ?", (cat_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="分类不存在")
        conn.execute("UPDATE capability_tag_categories SET enabled = ?, updated_at = ? WHERE id = ?", (1 if payload.enabled else 0, now, cat_id))
        row = conn.execute(f"SELECT {_CAT_COLS} FROM capability_tag_categories WHERE id = ?", (cat_id,)).fetchone()
    return _cat_to_out(row)
