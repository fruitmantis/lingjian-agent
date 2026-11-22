"""Explicit schema 25 -> 26 two-tier capability tag hierarchy migration.

Preserves existing Level-1 UUIDs (and resource_capability_map FKs), separates Level-2
tags from partners.capabilities into partners.sub_capabilities without model calls,
and enforces (level=1, name) and (level=2, parent_id, name) uniqueness.
"""
from datetime import datetime, timezone
import uuid

from .capability_hierarchy import (
    CATALOG,
    LEGACY_ALIASES,
    read_sub_capabilities,
    split_capability_tokens,
    stored_sub_capabilities,
)


def migrate(conn):
    conn.lock_writer()
    version = conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]
    if version == '26':
        return {'schema_version': 26, 'already_current': True}
    if version != '25':
        raise RuntimeError('Capability hierarchy migration requires schema 25')

    now = datetime.now(timezone.utc).isoformat()

    # 1. Additive schema changes and constraint replacement on capability_tags & partners.
    conn.execute('ALTER TABLE capability_tags ADD COLUMN IF NOT EXISTS level INTEGER NOT NULL DEFAULT 1')
    conn.execute('ALTER TABLE capability_tags ADD COLUMN IF NOT EXISTS parent_id TEXT')
    conn.execute('ALTER TABLE capability_tags DROP CONSTRAINT IF EXISTS uq_capability_tags_0')
    conn.execute('DROP INDEX IF EXISTS uq_capability_tags_0')
    existing_constraints = {
        row[0]
        for row in conn.execute("SELECT conname FROM pg_constraint WHERE conrelid = 'capability_tags'::regclass").fetchall()
    }
    if 'ck_capability_tags_level' not in existing_constraints:
        conn.execute('ALTER TABLE capability_tags ADD CONSTRAINT ck_capability_tags_level CHECK (level IN (1, 2))')
    if 'ck_capability_tags_hierarchy' not in existing_constraints:
        conn.execute(
            'ALTER TABLE capability_tags ADD CONSTRAINT ck_capability_tags_hierarchy '
            'CHECK ((level = 1 AND parent_id IS NULL) OR (level = 2 AND parent_id IS NOT NULL))'
        )
    if 'fk_capability_tags_parent' not in existing_constraints:
        conn.execute(
            'ALTER TABLE capability_tags ADD CONSTRAINT fk_capability_tags_parent '
            'FOREIGN KEY (parent_id) REFERENCES capability_tags(id) ON DELETE RESTRICT'
        )
    conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_capability_tags_l1_name ON capability_tags (name) WHERE level = 1')
    conn.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_capability_tags_l2_parent_name ON capability_tags (parent_id, name) WHERE level = 2'
    )
    conn.execute('ALTER TABLE partners ADD COLUMN IF NOT EXISTS sub_capabilities TEXT')

    # 2. Upsert the 2 official top-level categories.
    for cat in CATALOG['categories']:
        existing_cat = conn.execute(
            'SELECT id FROM capability_tag_categories WHERE name = ?', (cat['name'],)
        ).fetchone()
        if existing_cat:
            conn.execute(
                'UPDATE capability_tag_categories SET code=?, description=?, enabled=1, sort_order=?, is_preset=1, updated_at=? WHERE id=?',
                (cat['code'], cat.get('description', ''), cat['sort_order'], now, existing_cat['id']),
            )
        else:
            conn.execute(
                'INSERT INTO capability_tag_categories (id, name, code, description, enabled, sort_order, is_preset, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, 1, ?, 1, ?, ?)',
                (str(uuid.uuid4()), cat['name'], cat['code'], cat.get('description', ''), cat['sort_order'], now, now),
            )

    # 3. Upsert the 25 official Level-1 tags (preserving existing UUIDs).
    l1_ids: dict[str, str] = {}
    for item in CATALOG['tags']:
        row = conn.execute(
            'SELECT id FROM capability_tags WHERE name = ? AND level = 1', (item['name'],)
        ).fetchone()
        if row:
            l1_id = row['id']
            conn.execute(
                'UPDATE capability_tags SET category=?, sort_order=?, is_preset=1, updated_at=? WHERE id=?',
                (item['category'], item['sort_order'], now, l1_id),
            )
        else:
            l1_id = str(uuid.uuid4())
            conn.execute(
                'INSERT INTO capability_tags (id, name, category, level, parent_id, description, enabled, sort_order, is_preset, created_at, updated_at) '
                'VALUES (?, ?, ?, 1, NULL, ?, 1, ?, 1, ?, ?)',
                (l1_id, item['name'], item['category'], '', item['sort_order'], now, now),
            )
        l1_ids[item['name']] = l1_id

    # 4. Clean up obsolete unused preset categories (keep any still referenced by custom tags or suggestions).
    official_cat_names = tuple(cat['name'] for cat in CATALOG['categories'])
    conn.execute(
        'DELETE FROM capability_tag_categories '
        'WHERE is_preset = 1 '
        'AND name NOT IN (?, ?) '
        'AND name NOT IN (SELECT DISTINCT category FROM capability_tags) '
        'AND id NOT IN (SELECT DISTINCT suggested_category_id FROM capability_tag_suggestions WHERE suggested_category_id IS NOT NULL)',
        official_cat_names,
    )

    # 5. Insert all 88 official Level-2 tags under their Level-1 parents.
    l2_count = 0
    l2_to_parents: dict[str, list[str]] = {}
    for item in CATALOG['tags']:
        parent_id = l1_ids[item['name']]
        for idx, child_name in enumerate(item['children'], 1):
            l2_to_parents.setdefault(child_name, []).append(item['name'])
            existing_l2 = conn.execute(
                'SELECT id FROM capability_tags WHERE parent_id = ? AND name = ? AND level = 2',
                (parent_id, child_name),
            ).fetchone()
            if existing_l2:
                conn.execute(
                    'UPDATE capability_tags SET category=?, sort_order=?, is_preset=1, updated_at=? WHERE id=?',
                    (item['category'], idx, now, existing_l2['id']),
                )
            else:
                conn.execute(
                    'INSERT INTO capability_tags (id, name, category, level, parent_id, description, enabled, sort_order, is_preset, created_at, updated_at) '
                    'VALUES (?, ?, ?, 2, ?, ?, 1, ?, 1, ?, ?)',
                    (str(uuid.uuid4()), child_name, item['category'], parent_id, '', idx, now, now),
                )
            l2_count += 1

    # 6. Separate Level-1 and Level-2 capabilities on existing partners without losing custom values.
    l1_set = set(l1_ids)
    # Also allow custom Level-1 tags already present in DB.
    for row in conn.execute('SELECT name FROM capability_tags WHERE level = 1'):
        l1_set.add(row['name'])

    partners_migrated = 0
    l2_assignments_migrated = 0
    legacy_aliases_applied = 0

    for partner in conn.execute('SELECT id, name, capabilities, sub_capabilities FROM partners ORDER BY id').fetchall():
        raw_caps = partner['capabilities']
        tokens = split_capability_tokens(raw_caps)
        existing_subs = read_sub_capabilities(partner['sub_capabilities'])
        if not tokens and not existing_subs:
            continue

        l1_list: list[str] = []
        l2_tokens: list[str] = []
        custom_tokens: list[str] = []
        partner_aliased = False

        for token in tokens:
            if token in LEGACY_ALIASES:
                alias = LEGACY_ALIASES[token]
                legacy_aliases_applied += 1
                partner_aliased = True
                if alias.get('level') == 1 and alias['name'] not in l1_list:
                    l1_list.append(alias['name'])
            elif token in l1_set:
                if token not in l1_list:
                    l1_list.append(token)
            elif token in l2_to_parents:
                l2_tokens.append(token)
            else:
                if token not in custom_tokens:
                    custom_tokens.append(token)

        if not l2_tokens and not partner_aliased:
            continue

        sub_items = list(existing_subs)
        seen_subs = {(s['parent'], s['name']) for s in sub_items}
        for token in l2_tokens:
            parents = l2_to_parents[token]
            if len(parents) == 1:
                parent_name = parents[0]
            else:
                matched_parents = [p for p in parents if p in l1_list]
                if len(matched_parents) != 1:
                    raise RuntimeError(
                        f"Ambiguous Level-2 capability {token!r} for partner {partner['id']} ({partner['name']}): "
                        f"candidates={parents}, partner_l1={l1_list}"
                    )
                parent_name = matched_parents[0]
            if parent_name not in l1_list:
                l1_list.append(parent_name)
            if (parent_name, token) not in seen_subs:
                seen_subs.add((parent_name, token))
                sub_items.append({'parent': parent_name, 'name': token})
                l2_assignments_migrated += 1

        final_l1 = list(dict.fromkeys(l1_list + custom_tokens))
        new_caps = ','.join(final_l1) if final_l1 else None
        new_subs = stored_sub_capabilities(sub_items)
        conn.execute(
            'UPDATE partners SET capabilities=?, sub_capabilities=?, updated_at=? WHERE id=?',
            (new_caps, new_subs, now, partner['id']),
        )
        partners_migrated += 1

    conn.execute("UPDATE app_metadata SET value='26' WHERE key='schema_version'")
    categories_count = conn.execute('SELECT COUNT(*) FROM capability_tag_categories').fetchone()[0]
    l1_total = conn.execute('SELECT COUNT(*) FROM capability_tags WHERE level = 1').fetchone()[0]
    l2_total = conn.execute('SELECT COUNT(*) FROM capability_tags WHERE level = 2').fetchone()[0]
    return {
        'schema_version': 26,
        'categories_count': categories_count,
        'l1_count': l1_total,
        'l2_count': l2_total,
        'partners_migrated': partners_migrated,
        'l2_assignments_migrated': l2_assignments_migrated,
        'legacy_aliases_applied': legacy_aliases_applied,
    }
