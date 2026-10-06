"""Additive schema 20; old reports/intro/summaries are retained for rollback."""
def migrate(conn):
    version=conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]
    if version=='20':return {'schema_version':20,'already_current':True}
    if version!='19':raise RuntimeError('Expected schema 19')
    from .storage_models import partner_profile_sources
    partner_profile_sources.create(conn.connection,checkfirst=True)
    conn.execute("INSERT INTO app_metadata(key,value) SELECT 'profile_source_legacy:'||id,json_build_object('ai_profile',ai_profile,'intro',intro,'profile_materials_revision',profile_materials_revision,'profile_updated_at',profile_updated_at)::text FROM partners ON CONFLICT(key) DO NOTHING")
    conn.execute("UPDATE app_metadata SET value='20' WHERE key='schema_version'")
    return {'schema_version':20,'legacy_fields_retained':True}

def rollback(conn):
    if conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]!='20':
        raise RuntimeError('Expected schema 20')
    # Keep contribution table and legacy archive; rollback performs no physical deletion.
    conn.execute("""UPDATE partners p SET ai_profile=(a.value::jsonb)->>'ai_profile',
        intro=(a.value::jsonb)->>'intro',
        profile_materials_revision=((a.value::jsonb)->>'profile_materials_revision')::integer,
        profile_updated_at=(a.value::jsonb)->>'profile_updated_at'
        FROM app_metadata a WHERE a.key='profile_source_legacy:'||p.id""")
    conn.execute("UPDATE app_metadata SET value='19' WHERE key='schema_version'")
    return {'schema_version':19,'contributions_and_legacy_archive_retained':True}
