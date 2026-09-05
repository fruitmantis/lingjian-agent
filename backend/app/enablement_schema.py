"""Additive v10 schema. No business rows from v9 are rewritten."""
import sqlite3


def migrate_to_v10(connection: sqlite3.Connection) -> None:
    version = int(connection.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0])
    if version >= 10:
        return
    if version != 9:
        raise RuntimeError('Enablement migration requires schema v9')
    connection.commit()
    try:
        connection.execute('BEGIN IMMEDIATE')
        for kind, table, versions, key, reference in (
            ('resource', 'enablement_resources', 'enablement_resource_versions', 'id', ''),
            ('case', 'case_share_configs', 'case_share_versions', 'case_id', ' REFERENCES cases(id) ON DELETE RESTRICT'),
        ):
            connection.execute(f'''CREATE TABLE {table} (
                {key} TEXT PRIMARY KEY{reference},
                draft_json TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
                status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','unpublished','revoked')),
                published_version INTEGER,
                system_visible INTEGER NOT NULL DEFAULT 0 CHECK(system_visible IN (0,1)),
                model_allowed INTEGER NOT NULL DEFAULT 0 CHECK(model_allowed IN (0,1)),
                partner_allowed INTEGER NOT NULL DEFAULT 0 CHECK(partner_allowed IN (0,1)),
                authorization_epoch INTEGER NOT NULL DEFAULT 1,
                created_by TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )''')
            connection.execute(f'''CREATE TABLE {versions} (
                source_id TEXT NOT NULL REFERENCES {table}({key}) ON DELETE RESTRICT,
                version INTEGER NOT NULL CHECK(version > 0),
                payload_json TEXT NOT NULL, authorization_epoch INTEGER NOT NULL,
                reviewed_revision INTEGER NOT NULL,
                published_by TEXT NOT NULL REFERENCES users(id), published_at TEXT NOT NULL,
                PRIMARY KEY(source_id, version)
            )''')
        connection.execute('''CREATE TABLE resource_capability_map (
            resource_id TEXT NOT NULL REFERENCES enablement_resources(id) ON DELETE CASCADE,
            capability_tag_id TEXT NOT NULL REFERENCES capability_tags(id) ON DELETE RESTRICT,
            PRIMARY KEY(resource_id,capability_tag_id))''')
        connection.execute('''CREATE TABLE enablement_reviews (
            id TEXT PRIMARY KEY, source_kind TEXT NOT NULL CHECK(source_kind IN ('resource','case')),
            source_id TEXT NOT NULL, revision INTEGER NOT NULL,
            reviewer_id TEXT NOT NULL REFERENCES users(id), reviewed_at TEXT NOT NULL,
            link_status TEXT NOT NULL CHECK(link_status IN ('available','unavailable','unknown')),
            content_checked INTEGER NOT NULL, authorization_checked INTEGER NOT NULL,
            note TEXT NOT NULL DEFAULT '')''')
        connection.execute('CREATE INDEX idx_enablement_reviews_source ON enablement_reviews(source_kind,source_id,revision)')
        connection.execute('''CREATE TABLE enablement_audit_events (
            id TEXT PRIMARY KEY, source_kind TEXT NOT NULL, source_id TEXT NOT NULL,
            action TEXT NOT NULL, actor_id TEXT NOT NULL REFERENCES users(id),
            revision INTEGER NOT NULL, authorization_epoch INTEGER NOT NULL,
            reason TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)''')
        connection.execute('CREATE INDEX idx_enablement_audit_source ON enablement_audit_events(source_kind,source_id,created_at)')
        connection.execute("UPDATE app_metadata SET value='10' WHERE key='schema_version'")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
