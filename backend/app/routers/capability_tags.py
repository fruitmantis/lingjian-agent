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
    description: str | None = None
    sortOrder: int = 0


_SUG_COLS = "id, suggested_name, suggested_category_id, suggested_category_name, description, evidence_text, source_requirement, source_match_record_id, confidence, occurrence_count, status, created_at, updated_at, adopted_at"


def _sug_to_out(r) -> SuggestionOut:
    return SuggestionOut(
        id=r["id"], suggestedName=r["suggested_name"], suggestedCategoryId=r["suggested_category_id"],
        suggestedCategoryName=r["suggested_category_name"], description=r["description"],
        evidenceText=r["evidence_text"], sourceRequirement=r["source_requirement"],
        sourceMatchRecordId=r["source_match_record_id"], confidence=r["confidence"],
        occurrenceCount=r["occurrence_count"], status=r["status"],
        createdAt=r["created_at"], updatedAt=r["updated_at"], adoptedAt=r["adopted_at"]
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
            conditions.append("suggested_name LIKE ?")
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
    """Manually scan match records for new tag suggestions."""
    from ..ai_client import chat_completion
    import json as _json
    with get_db() as conn:
        records = conn.execute("SELECT id, requirement, recommendations_json FROM match_records ORDER BY created_at DESC LIMIT 10").fetchall()
        std_tags = [r["name"] for r in conn.execute("SELECT name FROM capability_tags WHERE enabled = 1").fetchall()]
        existing_sugs = {r["suggested_name"] for r in conn.execute("SELECT suggested_name FROM capability_tag_suggestions WHERE status = 'pending'").fetchall()}
    std_tags_str = ", ".join(std_tags) if std_tags else "无标准标签"
    created = 0
    for rec in records:
        try:
            raw = chat_completion([
                {"role": "system", "content": f"分析项目需求，找出标准能力标签无法覆盖的新能力诉求。当前标准标签：[{std_tags_str}]。如果存在未覆盖的能力诉求，返回JSON数组，每项含suggestedName(标签名),suggestedCategoryName(分类名,从以下选择:AI与智能体,云平台与迁移,数据与数据库,应用开发与现代化,运维与安全,咨询与项目管理,其他),description(说明),evidenceText(来源片段),confidence(0-1)。不要把行业/区域/资质误判为能力标签。如果没有新诉求返回空数组[]。只返回JSON。"},
                {"role": "user", "content": f"项目需求: {rec['requirement']}"}
            ], timeout=30)
            clean = raw.strip()
            if clean.startswith("```"): clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"): clean = clean[:-3]
            clean = clean.strip()
            if clean.startswith("json"): clean = clean[4:].strip()
            items = _json.loads(clean)
            now = datetime.now(timezone.utc).isoformat()
            for item in items:
                name = item.get("suggestedName", "").strip()
                if not name or name in std_tags or name in existing_sugs:
                    continue
                sug_id = str(uuid.uuid4())
                conn_exec = None
                with get_db() as c:
                    c.execute(
                        "INSERT INTO capability_tag_suggestions (id, suggested_name, suggested_category_id, suggested_category_name, description, evidence_text, source_requirement, source_match_record_id, confidence, occurrence_count, status, created_at, updated_at, adopted_at) VALUES (?,?,?,?,?,?,?,?,?,1,'pending',?,?,NULL)",
                        (sug_id, name, None, item.get("suggestedCategoryName", "其他"), item.get("description", ""), item.get("evidenceText", ""), rec["requirement"], rec["id"], float(item.get("confidence", 0.5)), now, now)
                    )
                existing_sugs.add(name)
                created += 1
        except Exception:
            pass
    return {"status": "ok", "created": created}


@router.post("/suggestions/{sug_id}/adopt", response_model=CapabilityTagOut)
def adopt_suggestion(sug_id: str, payload: AdoptRequest) -> CapabilityTagOut:
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        sug = conn.execute(f"SELECT {_SUG_COLS} FROM capability_tag_suggestions WHERE id = ?", (sug_id,)).fetchone()
        if sug is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="建议不存在")
        if sug["status"] == "adopted":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="该建议已被采纳")
        existing = conn.execute("SELECT id FROM capability_tags WHERE name = ?", (payload.name,)).fetchone()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, detail=f"正式能力标签中已存在同名标签: {payload.name}")
        cat_name = None
        if payload.categoryId:
            cat = conn.execute("SELECT name FROM capability_tag_categories WHERE id = ?", (payload.categoryId,)).fetchone()
            cat_name = cat["name"] if cat else "其他"
        else:
            cat_name = sug["suggested_category_name"] or "其他"
        tag_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO capability_tags (id, name, category, description, enabled, sort_order, is_preset, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, 0, ?, ?)",
            (tag_id, payload.name, cat_name, payload.description or sug["description"] or "", payload.sortOrder, now, now)
        )
        conn.execute("UPDATE capability_tag_suggestions SET status = 'adopted', adopted_at = ?, updated_at = ? WHERE id = ?", (now, now, sug_id))
        row = conn.execute(f"SELECT {_COLS} FROM capability_tags WHERE id = ?", (tag_id,)).fetchone()
    return _to_out(row)
