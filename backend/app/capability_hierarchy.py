"""Two-tier capability tag dictionary, hierarchy tree and partner capability helpers."""
import json
import re
from pathlib import Path

CATALOG = json.loads((Path(__file__).resolve().parents[2] / 'shared/capability-tags.json').read_text(encoding='utf-8'))
TOP_CATEGORIES = CATALOG['categories']
LEGACY_ALIASES = CATALOG.get('legacy_aliases', {})

_SPLIT_RE = re.compile(r'[,，、;；\n]+')
_INVALID_NAME_RE = re.compile(r'[,，、;；\r\n]')
MAX_TAG_NAME_LENGTH = 100


def validate_tag_name(name: str, level: int) -> str:
    cleaned = (name or '').strip()
    if not cleaned:
        raise ValueError('标签名称不能为空')
    if len(cleaned) > MAX_TAG_NAME_LENGTH:
        raise ValueError(f'标签名称不能超过{MAX_TAG_NAME_LENGTH}个字符')
    if _INVALID_NAME_RE.search(cleaned):
        raise ValueError('标签名称不能包含逗号、顿号、分号或换行符')
    if level == 1 and '/' in cleaned:
        raise ValueError('一级标签名称不能包含斜杠“/”')
    return cleaned


def canonical_capability_name(name: str) -> str:
    cleaned = (name or '').strip()
    alias = LEGACY_ALIASES.get(cleaned)
    if isinstance(alias, dict) and alias.get('level') == 1 and alias.get('name'):
        return str(alias['name'])
    return cleaned


def aliases_for_canonical(name: str) -> list[str]:
    canon = canonical_capability_name(name)
    if not canon:
        return []
    aliases = [canon]
    for old_name, target in LEGACY_ALIASES.items():
        if isinstance(target, dict) and target.get('level') == 1 and target.get('name') == canon:
            if old_name not in aliases:
                aliases.append(old_name)
    return aliases


def split_capability_tokens(value: str | None) -> list[str]:
    if not value:
        return []
    return list(dict.fromkeys(part.strip() for part in _SPLIT_RE.split(str(value)) if part.strip()))


def read_sub_capabilities(value) -> list[dict[str, str]]:
    if value is None or value == '':
        return []
    raw = json.loads(value) if isinstance(value, str) else value
    if not isinstance(raw, list):
        return []
    items: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in raw:
        if hasattr(entry, 'model_dump'):
            entry = entry.model_dump()
        if not isinstance(entry, dict):
            continue
        parent = str(entry.get('parent') or '').strip()
        name = str(entry.get('name') or '').strip()
        if not parent or not name or (parent, name) in seen:
            continue
        seen.add((parent, name))
        items.append({'parent': parent, 'name': name})
    return items


def stored_sub_capabilities(items: list[dict[str, str]] | None) -> str | None:
    cleaned = read_sub_capabilities(items)
    return json.dumps(cleaned, ensure_ascii=False) if cleaned else None


def format_sub_capabilities(items: list[dict[str, str]]) -> str:
    return ','.join(f"{item['parent']}/{item['name']}" for item in read_sub_capabilities(items))


def parse_sub_capability_pairs(raw: str | None) -> list[dict[str, str]]:
    if not raw or not str(raw).strip():
        return []
    items: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for token in split_capability_tokens(str(raw)):
        if '/' not in token:
            raise ValueError(f'二级能力标签格式无效（应为“一级/二级”）: {token}')
        parent, name = token.split('/', 1)
        parent, name = parent.strip(), name.strip()
        if not parent or not name:
            raise ValueError(f'二级能力标签格式无效（应为“一级/二级”）: {token}')
        if (parent, name) not in seen:
            seen.add((parent, name))
            items.append({'parent': parent, 'name': name})
    return items


def validate_sub_capabilities(conn, items, *, existing_items=()) -> list[dict[str, str]]:
    cleaned = read_sub_capabilities(items)
    if not cleaned:
        return []
    existing_set = {(entry['parent'], entry['name']) for entry in read_sub_capabilities(existing_items)}
    rows = conn.execute('SELECT id, name, level, parent_id, enabled FROM capability_tags').fetchall()
    l1_by_id = {row['id']: dict(row) for row in rows if row['level'] == 1}
    l2_by_key: dict[tuple[str, str], dict] = {}
    for row in rows:
        if row['level'] == 2 and row['parent_id'] in l1_by_id:
            parent_row = l1_by_id[row['parent_id']]
            l2_by_key[(parent_row['name'], row['name'])] = {**dict(row), 'parent_enabled': parent_row['enabled']}
    for item in cleaned:
        key = (item['parent'], item['name'])
        match = l2_by_key.get(key)
        if not match:
            raise ValueError(f"无效的二级能力标签：{item['parent']}/{item['name']}")
        if key not in existing_set and (not match['enabled'] or not match['parent_enabled']):
            raise ValueError(f"二级能力标签已停用：{item['parent']}/{item['name']}")
    return cleaned


def enabled_capability_sets(conn) -> tuple[set[str], set[tuple[str, str]], set[str]]:
    rows = conn.execute('SELECT id, name, level, parent_id, enabled FROM capability_tags').fetchall()
    l1_by_id = {row['id']: dict(row) for row in rows if row['level'] == 1}
    enabled_l1 = {row['name'] for row in l1_by_id.values() if row['enabled']}
    disabled_l1 = {row['name'] for row in l1_by_id.values() if not row['enabled']}
    enabled_l2: set[tuple[str, str]] = set()
    for row in rows:
        if row['level'] == 2 and row['enabled'] and row['parent_id'] in l1_by_id:
            parent_row = l1_by_id[row['parent_id']]
            if parent_row['enabled']:
                enabled_l2.add((parent_row['name'], row['name']))
    return enabled_l1, enabled_l2, disabled_l1


def validate_l1_capabilities(conn, capabilities: str | None, *, existing_capabilities: str | None = None) -> str | None:
    tokens = split_capability_tokens(capabilities)
    if not tokens:
        return None
    existing_set = set(split_capability_tokens(existing_capabilities))
    l1_rows = {
        row['name']: bool(row['enabled'])
        for row in conn.execute('SELECT name, enabled FROM capability_tags WHERE level = 1')
    }
    for token in tokens:
        if token in existing_set:
            continue
        if token not in l1_rows:
            raise ValueError(f'无效的一级能力标签：{token}')
        if not l1_rows[token]:
            raise ValueError(f'一级能力标签已停用：{token}')
    return capabilities.strip() if capabilities and capabilities.strip() else None


def normalize_partner_capabilities(
    conn,
    capabilities: str | None,
    sub_capabilities,
    *,
    existing_capabilities: str | None = None,
    existing_sub_capabilities=None,
    sub_provided: bool,
) -> tuple[str | None, list[dict[str, str]]]:
    existing_subs = read_sub_capabilities(existing_sub_capabilities)
    if sub_provided:
        effective_subs = validate_sub_capabilities(conn, sub_capabilities, existing_items=existing_subs)
    else:
        effective_subs = existing_subs
    cleaned_caps = validate_l1_capabilities(conn, capabilities, existing_capabilities=existing_capabilities)
    effective_caps = ensure_parent_capabilities(cleaned_caps, effective_subs)
    return effective_caps, effective_subs


def ensure_parent_capabilities(capabilities: str | None, sub_items: list[dict[str, str]]) -> str | None:
    tokens = split_capability_tokens(capabilities)
    added = False
    for item in read_sub_capabilities(sub_items):
        if item['parent'] not in tokens:
            tokens.append(item['parent'])
            added = True
    if not tokens:
        return None
    if not added and capabilities and capabilities.strip():
        return capabilities.strip()
    sep = '、' if (capabilities and '、' in capabilities and ',' not in capabilities and '，' not in capabilities) else ','
    return sep.join(tokens)


def load_capability_tree(conn, *, include_disabled: bool = False) -> list[dict]:
    cat_where = '' if include_disabled else ' WHERE enabled = 1'
    cat_rows = [dict(r) for r in conn.execute(
        f'SELECT id, name, code, description, enabled, sort_order, is_preset FROM capability_tag_categories{cat_where} ORDER BY sort_order ASC, created_at ASC'
    )]
    tag_where = '' if include_disabled else ' WHERE enabled = 1'
    tag_rows = [dict(r) for r in conn.execute(
        f'SELECT id, name, category, description, enabled, sort_order, is_preset, level, parent_id, created_at, updated_at '
        f'FROM capability_tags{tag_where} ORDER BY sort_order ASC, created_at ASC'
    )]
    l1_by_id: dict[str, dict] = {}
    l1_by_cat: dict[str, list[dict]] = {}
    for row in tag_rows:
        if row['level'] == 1:
            node = {
                'id': row['id'],
                'name': row['name'],
                'category': row['category'],
                'description': row['description'],
                'enabled': bool(row['enabled']),
                'sortOrder': row['sort_order'],
                'isPreset': bool(row['is_preset']),
                'level': 1,
                'createdAt': row['created_at'],
                'updatedAt': row['updated_at'],
                'children': [],
            }
            l1_by_id[row['id']] = node
            l1_by_cat.setdefault(row['category'], []).append(node)
    for row in tag_rows:
        if row['level'] == 2 and row['parent_id'] in l1_by_id:
            parent = l1_by_id[row['parent_id']]
            parent['children'].append({
                'id': row['id'],
                'name': row['name'],
                'category': row['category'],
                'parentId': row['parent_id'],
                'parentName': parent['name'],
                'description': row['description'],
                'enabled': bool(row['enabled']),
                'sortOrder': row['sort_order'],
                'isPreset': bool(row['is_preset']),
                'level': 2,
                'createdAt': row['created_at'],
                'updatedAt': row['updated_at'],
            })
    tree = []
    seen_cats = set()
    for cat in cat_rows:
        seen_cats.add(cat['name'])
        tree.append({
            'id': cat['id'],
            'name': cat['name'],
            'code': cat['code'],
            'description': cat['description'],
            'enabled': bool(cat['enabled']),
            'sortOrder': cat['sort_order'],
            'isPreset': bool(cat['is_preset']),
            'tags': l1_by_cat.get(cat['name'], []),
        })
    if include_disabled:
        for cat_name, tags in l1_by_cat.items():
            if cat_name not in seen_cats:
                tree.append({
                    'id': '',
                    'name': cat_name,
                    'code': None,
                    'description': None,
                    'enabled': True,
                    'sortOrder': 999,
                    'isPreset': False,
                    'tags': tags,
                })
    return tree


def l1_l2_hierarchy_map(conn) -> tuple[list[str], dict[str, list[str]]]:
    l1_rows = conn.execute(
        'SELECT id, name FROM capability_tags WHERE enabled = 1 AND level = 1 ORDER BY sort_order ASC, name ASC'
    ).fetchall()
    l1_names = [row['name'] for row in l1_rows]
    id_to_name = {row['id']: row['name'] for row in l1_rows}
    hierarchy: dict[str, list[str]] = {name: [] for name in l1_names}
    l2_rows = conn.execute(
        'SELECT name, parent_id FROM capability_tags WHERE enabled = 1 AND level = 2 ORDER BY sort_order ASC, name ASC'
    ).fetchall()
    for row in l2_rows:
        parent_name = id_to_name.get(row['parent_id'])
        if parent_name:
            hierarchy[parent_name].append(row['name'])
    return l1_names, hierarchy
