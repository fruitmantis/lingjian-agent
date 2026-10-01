"""Schema 17: native document processing and simple case visibility.

The explicit runtime command takes a complete backup first. Tests use disposable PostgreSQL schemas. Existing partner/case/file IDs are preserved.
"""
import json
from pathlib import Path

FILE_COLUMNS = {
    'processing_status': "TEXT NOT NULL DEFAULT 'processing'",
    'processing_error': 'TEXT', 'preview_error': 'TEXT', 'preview_path': 'TEXT', 'processed_at': 'TEXT',
}


def migrate(conn, fault=None):
    version = conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]
    if int(version) >= 17: return {'schema_version': int(version), 'already_current': True}
    if str(version) != '16': raise RuntimeError('Partner materials migration requires schema 16')
    conn.lock_writer()
    for name, kind in {'category_id':'TEXT', 'visible':'INTEGER NOT NULL DEFAULT 0', 'updated_at':'TEXT'}.items():
        conn.execute(f'ALTER TABLE cases ADD COLUMN {name} {kind}')
    for name,kind in {'materials_revision':'INTEGER NOT NULL DEFAULT 0','profile_materials_revision':'INTEGER NOT NULL DEFAULT 0','profile_updated_at':'TEXT'}.items():
        conn.execute(f'ALTER TABLE partners ADD COLUMN {name} {kind}')
    for table in ('partner_documents','deliverables'):
        columns = dict(FILE_COLUMNS)
        if table == 'deliverables': columns.update(file_type="TEXT NOT NULL DEFAULT ''", extracted_text='TEXT')
        for name,kind in columns.items(): conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {kind}')
        # The old cache may have been truncated; it is retained until an explicit retry.
        conn.execute(f"UPDATE {table} SET processing_status='failed',processing_error='旧资料尚未完整解析，请点击重试。'")
    from .material_contract import file_type
    for row in conn.execute('SELECT id,filename FROM deliverables').fetchall():
        conn.execute('UPDATE deliverables SET file_type=? WHERE id=?',(file_type(row[1]),row[0]))
    # Preserve original internal descriptions. Only previously public, identical content
    # stays visible; otherwise require the administrator to explicitly display it.
    retained=0
    rows=conn.execute('''SELECT c.id,c.title,c.description,s.status,s.system_visible,v.payload_json
        FROM cases c JOIN case_share_configs s ON s.case_id=c.id
        LEFT JOIN case_share_versions v ON v.source_id=s.case_id AND v.version=s.published_version''').fetchall()
    for row in rows:
        payload=json.loads(row[5]) if row[5] else {}
        same=payload.get('title')==row[1] and payload.get('summary','')==(row[2] or '')
        has_files=conn.execute('SELECT 1 FROM deliverables WHERE case_id=? LIMIT 1',(row[0],)).fetchone() is not None
        visible=int(not has_files and row[3]=='published' and row[4] and payload.get('_permissions',{}).get('system_visible') and same)
        # Keep different legacy public content in the existing audit, not a new version system.
        if payload and not same:
            import uuid
            from datetime import datetime, timezone
            # Current runtime contains no attachment reference in legacy snapshots.
            # Metadata is preserved in existing audit storage and in the full backup.
            conn.execute("INSERT INTO enablement_audit_events VALUES (?,?,?,?,?,?,?,?,?)",(str(uuid.uuid4()),'case',row[0],'legacy_content_preserved',payload.get('published_by') or conn.execute('SELECT created_by FROM case_share_configs WHERE case_id=?',(row[0],)).fetchone()[0],1,1,json.dumps(payload,ensure_ascii=False),datetime.now(timezone.utc).isoformat()))
            retained+=1
        conn.execute('UPDATE cases SET visible=? WHERE id=?',(visible,row[0]))
    conn.execute('UPDATE cases SET updated_at=created_at')
    conn.execute('''UPDATE partners SET materials_revision=1 WHERE id IN
        (SELECT partner_id FROM partner_documents UNION SELECT c.partner_id FROM cases c JOIN deliverables d ON d.case_id=c.id)''')
    if fault: fault()
    conn.execute('DROP TABLE case_share_versions')
    conn.execute('DROP TABLE case_share_configs')
    conn.execute('DROP TABLE enablement_reviews')
    conn.execute("UPDATE app_metadata SET value='17' WHERE key='schema_version'")
    return {'schema_version':17,'preserved_legacy_contents':retained}
