"""Small editable catalog taxonomy stored in the existing app_metadata configuration."""
import json
import uuid
from typing import Literal
from pydantic import Field
from .database import get_db
from .enablement import StrictModel, fail

KEY = 'enablement_resource_categories'


def initialize(conn):
    # Explicit initialization only. Never reset or overwrite administrator edits.
    if conn.execute('SELECT value FROM app_metadata WHERE key=?', (KEY,)).fetchone():
        return
    groups = {
        'role': ['迁移工程师', '大数据工程师', '云原生工程师', '数据库工程师', '运维工程师', 'AI平台工程师', 'AI应用工程师'],
        'zone': ['CodeArts', 'ModelArts', 'DataArts', 'AgentArts'],
    }
    rows = [{'id': f'{kind}-{i+1}', 'kind': kind, 'name': name, 'sort_order': i}
            for kind, names in groups.items() for i, name in enumerate(names)]
    conn.execute('INSERT INTO app_metadata (key,value) VALUES (?,?)', (KEY, json.dumps(rows, ensure_ascii=False)))


def read(conn):
    row = conn.execute('SELECT value FROM app_metadata WHERE key=?', (KEY,)).fetchone()
    return sorted(json.loads(row[0]) if row else [], key=lambda r: (r['kind'], r['sort_order'], r['id']))


def listing():
    with get_db() as conn:
        return read(conn)


class CategoryCreate(StrictModel):
    kind: Literal['role', 'zone']
    name: str = Field(min_length=1, max_length=80)
    sort_order: int = Field(default=0, ge=0, le=100000)


class CategoryEdit(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    sort_order: int = Field(ge=0, le=100000)


def save(payload, category_id=None):
    with get_db() as conn:
        conn.lock_writer()
        rows = read(conn)
        current = next((r for r in rows if r['id'] == category_id), None)
        if category_id and not current:
            fail(404, '分类不存在')
        kind = current['kind'] if current else payload.kind
        if any(r['kind'] == kind and r['name'].casefold() == payload.name.casefold() and r['id'] != category_id for r in rows):
            fail(409, '该分类名称已存在')
        if current:
            current.update(payload.model_dump())
        else:
            if len(rows) >= 500: fail(409, '分类数量已达上限')
            current = {'id': str(uuid.uuid4()), **payload.model_dump()}
            rows.append(current)
        if conn.execute('SELECT 1 FROM app_metadata WHERE key=?', (KEY,)).fetchone():
            conn.execute('UPDATE app_metadata SET value=? WHERE key=?', (json.dumps(rows, ensure_ascii=False), KEY))
        else:
            conn.execute('INSERT INTO app_metadata (key,value) VALUES (?,?)', (KEY, json.dumps(rows, ensure_ascii=False)))
        return current


def validate(conn, data):
    categories = {r['id']: r for r in read(conn)}
    for field, kind in [('role_ids', 'role'), ('zone_ids', 'zone')]:
        ids = data[field]
        if len(ids) != len(set(ids)) or any(id not in categories or categories[id]['kind'] != kind for id in ids):
            fail(422, '岗位或专区分类无效，请刷新后重新选择')


def labels(conn, data):
    rows = read(conn)
    return {key: [{'id': r['id'], 'name': r['name']} for r in rows if r['kind'] == kind and r['id'] in data.get(field, [])]
            for key, field, kind in [('roles', 'role_ids', 'role'), ('zones', 'zone_ids', 'zone')]}
