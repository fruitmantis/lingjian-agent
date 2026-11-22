"""Capability tags CRUD router."""

from typing import Literal
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth import require_admin
from ..capability_hierarchy import (
    ensure_parent_capabilities,
    load_capability_tree,
    read_sub_capabilities,
    split_capability_tokens,
    stored_sub_capabilities,
    validate_tag_name,
)
from ..database import get_db


router = APIRouter(prefix="/admin/capability-tags", tags=["capability-tags"], dependencies=[Depends(require_admin)])


class CapabilityTagOut(BaseModel):
    id: str
    name: str
    category: str
    level: int = 1
    parentId: str | None = None
    parentName: str | None = None
    description: str | None
    enabled: bool
    sortOrder: int
    isPreset: bool
    createdAt: str
    updatedAt: str


class CapabilityTagCreate(BaseModel):
    name: str
    category: str | None = None
    level: Literal[1, 2] = 1
    parentId: str | None = None
    description: str | None = None
    sortOrder: int = 0


class CapabilityTagUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    parentId: str | None = None
    description: str | None = None
    sortOrder: int | None = None


class EnableUpdate(BaseModel):
    enabled: bool


_SELECT = (
    "SELECT t.id, t.name, t.category, t.level, t.parent_id, p.name AS parent_name, "
    "t.description, t.enabled, t.sort_order, t.is_preset, t.created_at, t.updated_at "
    "FROM capability_tags t LEFT JOIN capability_tags p ON p.id = t.parent_id"
)


def _to_out(r) -> CapabilityTagOut:
    return CapabilityTagOut(
        id=r["id"], name=r["name"], category=r["category"],
        level=r["level"], parentId=r["parent_id"], parentName=r["parent_name"],
        description=r["description"], enabled=bool(r["enabled"]),
        sortOrder=r["sort_order"], isPreset=bool(r["is_preset"]),
        createdAt=r["created_at"], updatedAt=r["updated_at"],
    )


def _sync_partner_l1_rename(conn, old_name: str, new_name: str) -> None:
    if old_name == new_name:
        return
    for partner in conn.execute("SELECT id, capabilities, sub_capabilities FROM partners").fetchall():
        caps_tokens = split_capability_tokens(partner["capabilities"])
        new_caps = partner["capabilities"]
        caps_changed = False
        if old_name in caps_tokens:
            updated_tokens = list(dict.fromkeys(new_name if t == old_name else t for t in caps_tokens))
            sep = "、" if (partner["capabilities"] and "、" in partner["capabilities"] and "," not in partner["capabilities"] and "，" not in partner["capabilities"]) else ","
            new_caps = sep.join(updated_tokens) if updated_tokens else None
            caps_changed = True
        subs = read_sub_capabilities(partner["sub_capabilities"])
        subs_changed = False
        new_subs: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in subs:
            parent = new_name if item["parent"] == old_name else item["parent"]
            if parent != item["parent"]:
                subs_changed = True
            key = (parent, item["name"])
            if key not in seen:
                seen.add(key)
                new_subs.append({"parent": parent, "name": item["name"]})
        if caps_changed or subs_changed:
            conn.execute(
                "UPDATE partners SET capabilities = ?, sub_capabilities = ? WHERE id = ?",
                (new_caps, stored_sub_capabilities(new_subs), partner["id"]),
            )


def _sync_partner_l2_change(conn, old_parent_name: str, old_name: str, new_parent_name: str, new_name: str) -> None:
    if old_parent_name == new_parent_name and old_name == new_name:
        return
    for partner in conn.execute(
        "SELECT id, capabilities, sub_capabilities FROM partners WHERE sub_capabilities IS NOT NULL AND sub_capabilities != ''"
    ).fetchall():
        subs = read_sub_capabilities(partner["sub_capabilities"])
        changed = False
        new_subs: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for item in subs:
            if item["parent"] == old_parent_name and item["name"] == old_name:
                pair = {"parent": new_parent_name, "name": new_name}
                changed = True
            else:
                pair = item
            key = (pair["parent"], pair["name"])
            if key not in seen:
                seen.add(key)
                new_subs.append(pair)
        if changed:
            new_caps = (
                ensure_parent_capabilities(partner["capabilities"], new_subs)
                if new_parent_name != old_parent_name
                else partner["capabilities"]
            )
            conn.execute(
                "UPDATE partners SET capabilities = ?, sub_capabilities = ? WHERE id = ?",
                (new_caps, stored_sub_capabilities(new_subs), partner["id"]),
            )


@router.get("/tree")
def get_tag_tree():
    with get_db() as conn:
        return load_capability_tree(conn, include_disabled=True)


@router.get("", response_model=list[CapabilityTagOut])
def list_tags(
    search: str | None = None,
    category: str | None = None,
    level: int | None = None,
    parentId: str | None = None,
    enabled: bool | None = None,
):
    with get_db() as conn:
        query = _SELECT
        conditions = []
        params = []
        if search:
            conditions.append("t.name ILIKE ?")
            params.append(f"%{search}%")
        if category:
            conditions.append("t.category = ?")
            params.append(category)
        if level is not None:
            conditions.append("t.level = ?")
            params.append(level)
        if parentId:
            conditions.append("t.parent_id = ?")
            params.append(parentId)
        if enabled is not None:
            conditions.append("t.enabled = ?")
            params.append(1 if enabled else 0)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY t.level ASC, t.sort_order ASC, t.created_at ASC"
        rows = conn.execute(query, params).fetchall()
    return [_to_out(r) for r in rows]


@router.post("", response_model=CapabilityTagOut, status_code=status.HTTP_201_CREATED)
def create_tag(payload: CapabilityTagCreate) -> CapabilityTagOut:
    try:
        name = validate_tag_name(payload.name, payload.level)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    now = datetime.now(timezone.utc).isoformat()
    tag_id = str(uuid.uuid4())
    try:
        with get_db() as conn:
            conn.lock_writer()
            if payload.level == 1:
                if payload.parentId is not None:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="一级标签不能指定父标签")
                cat = (payload.category or "").strip()
                if not cat:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="一级标签必须指定所属分类")
                if not conn.execute("SELECT id FROM capability_tag_categories WHERE name = ?", (cat,)).fetchone():
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="所属分类不存在")
                if conn.execute("SELECT id FROM capability_tags WHERE level = 1 AND name = ?", (name,)).fetchone():
                    raise HTTPException(status.HTTP_409_CONFLICT, detail="一级标签名称已存在")
                parent_id = None
            else:
                if not payload.parentId:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="二级标签必须指定所属一级标签")
                parent = conn.execute(
                    "SELECT id, category, level FROM capability_tags WHERE id = ?", (payload.parentId,)
                ).fetchone()
                if not parent or parent["level"] != 1:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="所属一级标签不存在")
                if conn.execute(
                    "SELECT id FROM capability_tags WHERE level = 2 AND parent_id = ? AND name = ?",
                    (payload.parentId, name),
                ).fetchone():
                    raise HTTPException(status.HTTP_409_CONFLICT, detail="该一级标签下已存在同名二级标签")
                cat = parent["category"]
                parent_id = payload.parentId

            conn.execute(
                "INSERT INTO capability_tags (id, name, category, level, parent_id, description, enabled, sort_order, is_preset, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?, 0, ?, ?)",
                (tag_id, name, cat, payload.level, parent_id, payload.description, payload.sortOrder, now, now),
            )
            row = conn.execute(f"{_SELECT} WHERE t.id = ?", (tag_id,)).fetchone()
        return _to_out(row)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="同级下标签名称已存在")


@router.put("/{tag_id}", response_model=CapabilityTagOut)
def update_tag(tag_id: str, payload: CapabilityTagUpdate) -> CapabilityTagOut:
    now = datetime.now(timezone.utc).isoformat()
    try:
        with get_db() as conn:
            conn.lock_writer()
            row = conn.execute(f"{_SELECT} WHERE t.id = ?", (tag_id,)).fetchone()
            if row is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="标签不存在")

            if payload.name is not None:
                try:
                    new_name = validate_tag_name(payload.name, row["level"])
                except ValueError as exc:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
            else:
                new_name = row["name"]

            updates = []
            params = []
            if row["level"] == 1:
                if payload.parentId is not None:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="一级标签不能设置父标签")
                if new_name != row["name"]:
                    if conn.execute(
                        "SELECT id FROM capability_tags WHERE level = 1 AND name = ? AND id != ?", (new_name, tag_id)
                    ).fetchone():
                        raise HTTPException(status.HTTP_409_CONFLICT, detail="一级标签名称已存在")
                    updates.append("name = ?")
                    params.append(new_name)
                if payload.category is not None:
                    new_cat = payload.category.strip()
                    if not new_cat or not conn.execute(
                        "SELECT id FROM capability_tag_categories WHERE name = ?", (new_cat,)
                    ).fetchone():
                        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="所属分类不存在")
                    if new_cat != row["category"]:
                        updates.append("category = ?")
                        params.append(new_cat)
                        conn.execute(
                            "UPDATE capability_tags SET category = ?, updated_at = ? WHERE parent_id = ? AND level = 2",
                            (new_cat, now, tag_id),
                        )
            else:
                target_parent_id = payload.parentId if payload.parentId is not None else row["parent_id"]
                parent = conn.execute(
                    "SELECT id, name, category, level FROM capability_tags WHERE id = ?", (target_parent_id,)
                ).fetchone()
                if not parent or parent["level"] != 1:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="所属一级标签不存在")
                if new_name != row["name"] or target_parent_id != row["parent_id"]:
                    if conn.execute(
                        "SELECT id FROM capability_tags WHERE level = 2 AND parent_id = ? AND name = ? AND id != ?",
                        (target_parent_id, new_name, tag_id),
                    ).fetchone():
                        raise HTTPException(status.HTTP_409_CONFLICT, detail="该一级标签下已存在同名二级标签")
                if new_name != row["name"]:
                    updates.append("name = ?")
                    params.append(new_name)
                if target_parent_id != row["parent_id"]:
                    updates.append("parent_id = ?")
                    params.append(target_parent_id)
                if parent["category"] != row["category"]:
                    updates.append("category = ?")
                    params.append(parent["category"])

            if payload.description is not None:
                updates.append("description = ?")
                params.append(payload.description)
            if payload.sortOrder is not None:
                updates.append("sort_order = ?")
                params.append(payload.sortOrder)

            if updates:
                updates.append("updated_at = ?")
                params.append(now)
                params.append(tag_id)
                conn.execute(f"UPDATE capability_tags SET {', '.join(updates)} WHERE id = ?", params)

            if row["level"] == 1 and new_name != row["name"]:
                _sync_partner_l1_rename(conn, row["name"], new_name)
            elif row["level"] == 2:
                _sync_partner_l2_change(conn, row["parent_name"] or "", row["name"], parent["name"], new_name)

            row = conn.execute(f"{_SELECT} WHERE t.id = ?", (tag_id,)).fetchone()
        return _to_out(row)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="同级下标签名称已存在")


@router.patch("/{tag_id}/enable", response_model=CapabilityTagOut)
def toggle_enable(tag_id: str, payload: EnableUpdate) -> CapabilityTagOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute(f"{_SELECT} WHERE t.id = ?", (tag_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="标签不存在")
        conn.execute(
            "UPDATE capability_tags SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if payload.enabled else 0, now, tag_id),
        )
        row = conn.execute(f"{_SELECT} WHERE t.id = ?", (tag_id,)).fetchone()
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
        createdAt=r["created_at"], updatedAt=r["updated_at"],
    )


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(search: str | None = None, enabled: bool | None = None):
    with get_db() as conn:
        query = f"SELECT {_CAT_COLS} FROM capability_tag_categories"
        conditions = []
        params = []
        if search:
            conditions.append("name ILIKE ?")
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
                "INSERT INTO capability_tag_categories (id, name, code, description, enabled, sort_order, is_preset, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 1, ?, 0, ?, ?)",
                (cat_id, payload.name, payload.code, payload.description, payload.sortOrder, now, now),
            )
            row = conn.execute(f"SELECT {_CAT_COLS} FROM capability_tag_categories WHERE id = ?", (cat_id,)).fetchone()
        return _cat_to_out(row)
    except Exception:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="分类名称已存在")


@router.put("/categories/{cat_id}", response_model=CategoryOut)
def update_category(cat_id: str, payload: CategoryUpdate) -> CategoryOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.lock_writer()
        row = conn.execute(f"SELECT {_CAT_COLS} FROM capability_tag_categories WHERE id = ?", (cat_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="分类不存在")
        updates = []
        params = []
        new_cat_name = None
        if payload.name is not None:
            new_cat_name = payload.name.strip()
            if not new_cat_name:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="分类名称不能为空")
            updates.append("name = ?")
            params.append(new_cat_name)
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
        if new_cat_name is not None and new_cat_name != row["name"]:
            conn.execute(
                "UPDATE capability_tags SET category = ?, updated_at = ? WHERE category = ?",
                (new_cat_name, now, row["name"]),
            )
            conn.execute(
                "UPDATE capability_tag_suggestions SET suggested_category_name = ?, updated_at = ? "
                "WHERE suggested_category_name = ? OR suggested_category_id = ?",
                (new_cat_name, now, row["name"], cat_id),
            )
        row = conn.execute(f"SELECT {_CAT_COLS} FROM capability_tag_categories WHERE id = ?", (cat_id,)).fetchone()
    return _cat_to_out(row)


@router.patch("/categories/{cat_id}/enable", response_model=CategoryOut)
def toggle_category_enable(cat_id: str, payload: EnableUpdate) -> CategoryOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        row = conn.execute(f"SELECT {_CAT_COLS} FROM capability_tag_categories WHERE id = ?", (cat_id,)).fetchone()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="分类不存在")
        conn.execute(
            "UPDATE capability_tag_categories SET enabled = ?, updated_at = ? WHERE id = ?",
            (1 if payload.enabled else 0, now, cat_id),
        )
        row = conn.execute(f"SELECT {_CAT_COLS} FROM capability_tag_categories WHERE id = ?", (cat_id,)).fetchone()
    return _cat_to_out(row)


# ============ Tag Suggestions ============

class SuggestionOut(BaseModel):
    id: str
    suggestedName: str
    suggestedCategoryId: str | None
    suggestedCategoryName: str | None
    description: str | None
    evidenceText: str | None
    sourceRequirement: str | None
    sourceMatchRecordId: str | None
    confidence: float
    occurrenceCount: int
    status: str
    createdAt: str
    updatedAt: str
    adoptedAt: str | None


class AdoptRequest(BaseModel):
    name: str
    categoryId: str | None = None
    level: Literal[1, 2] = 1
    parentId: str | None = None
    description: str | None = None
    sortOrder: int = 0


_SUG_COLS = (
    "id, suggested_name, suggested_category_id, suggested_category_name, description, "
    "evidence_text, source_requirement, source_match_record_id, confidence, occurrence_count, "
    "status, created_at, updated_at, adopted_at"
)


def _sug_to_out(r) -> SuggestionOut:
    return SuggestionOut(
        id=r["id"], suggestedName=r["suggested_name"], suggestedCategoryId=r["suggested_category_id"],
        suggestedCategoryName=r["suggested_category_name"], description=r["description"],
        evidenceText=r["evidence_text"], sourceRequirement=r["source_requirement"],
        sourceMatchRecordId=r["source_match_record_id"], confidence=r["confidence"],
        occurrenceCount=r["occurrence_count"], status=r["status"],
        createdAt=r["created_at"], updatedAt=r["updated_at"], adoptedAt=r["adopted_at"],
    )


@router.get("/suggestions", response_model=list[SuggestionOut])
def list_suggestions(status: str | None = None, keyword: str | None = None, categoryId: str | None = None):
    with get_db() as conn:
        query = f"SELECT {_SUG_COLS} FROM capability_tag_suggestions"
        conditions = []
        params = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        if keyword:
            conditions.append("suggested_name ILIKE ?")
            params.append(f"%{keyword}%")
        if categoryId:
            conditions.append("suggested_category_id = ?")
            params.append(categoryId)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY occurrence_count DESC, confidence DESC, created_at DESC"
        rows = conn.execute(query, params).fetchall()
    return [_sug_to_out(r) for r in rows]


@router.post("/suggestions/scan")
def scan_suggestions():
    raise HTTPException(status.HTTP_410_GONE, detail="标签建议随匹配任务生成，请查看已有建议")


@router.post("/suggestions/{sug_id}/adopt", response_model=CapabilityTagOut)
def adopt_suggestion(sug_id: str, payload: AdoptRequest) -> CapabilityTagOut:
    try:
        name = validate_tag_name(payload.name, payload.level)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from None
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.lock_writer()
        sug = conn.execute(f"SELECT {_SUG_COLS} FROM capability_tag_suggestions WHERE id = ?", (sug_id,)).fetchone()
        if sug is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="建议不存在")
        if sug["status"] == "adopted":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="该建议已被采纳")

        if payload.level == 2:
            if not payload.parentId:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="采纳为二级标签时必须指定所属一级标签")
            parent = conn.execute(
                "SELECT id, category, level FROM capability_tags WHERE id = ?", (payload.parentId,)
            ).fetchone()
            if not parent or parent["level"] != 1:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="所属一级标签不存在")
            if conn.execute(
                "SELECT id FROM capability_tags WHERE level = 2 AND parent_id = ? AND name = ?",
                (payload.parentId, name),
            ).fetchone():
                raise HTTPException(status.HTTP_409_CONFLICT, detail=f"该一级标签下已存在同名二级标签: {name}")
            cat_name = parent["category"]
            parent_id = payload.parentId
        else:
            if conn.execute("SELECT id FROM capability_tags WHERE level = 1 AND name = ?", (name,)).fetchone():
                raise HTTPException(status.HTTP_409_CONFLICT, detail=f"正式能力标签中已存在同名一级标签: {name}")
            cat_name = None
            if payload.categoryId is not None and payload.categoryId.strip():
                cat_key = payload.categoryId.strip()
                cat = conn.execute(
                    "SELECT name FROM capability_tag_categories WHERE id = ? OR name = ?",
                    (cat_key, cat_key),
                ).fetchone()
                if cat is None:
                    raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="所属分类不存在")
                cat_name = cat["name"]
            else:
                if sug["suggested_category_id"]:
                    cat = conn.execute(
                        "SELECT name FROM capability_tag_categories WHERE id = ?",
                        (sug["suggested_category_id"],),
                    ).fetchone()
                    cat_name = cat["name"] if cat else None
                if not cat_name and sug["suggested_category_name"]:
                    cat = conn.execute(
                        "SELECT name FROM capability_tag_categories WHERE name = ?",
                        (sug["suggested_category_name"],),
                    ).fetchone()
                    cat_name = cat["name"] if cat else None
                if not cat_name:
                    fallback = conn.execute(
                        "SELECT name FROM capability_tag_categories WHERE code = 'scenario'"
                    ).fetchone() or conn.execute(
                        "SELECT name FROM capability_tag_categories ORDER BY enabled DESC, sort_order ASC, created_at ASC LIMIT 1"
                    ).fetchone()
                    if fallback is None:
                        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="所属分类不存在")
                    cat_name = fallback["name"]
            parent_id = None

        tag_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO capability_tags (id, name, category, level, parent_id, description, enabled, sort_order, is_preset, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, 0, ?, ?)",
            (tag_id, name, cat_name, payload.level, parent_id, payload.description or sug["description"] or "", payload.sortOrder, now, now),
        )
        conn.execute(
            "UPDATE capability_tag_suggestions SET status = 'adopted', adopted_at = ?, updated_at = ? WHERE id = ?",
            (now, now, sug_id),
        )
        row = conn.execute(f"{_SELECT} WHERE t.id = ?", (tag_id,)).fetchone()
    return _to_out(row)
