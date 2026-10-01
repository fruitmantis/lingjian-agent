"""Schema 16->17 PG replay: original IDs and content survive rollback and upgrade."""
import json
import pytest
from sqlalchemy import inspect
from backend.app import partner_materials_schema as schema
from backend.app.database import get_db
from .postgres_support import snapshot, foreign_key_violations

def legacy():
    with get_db() as conn:
        conn.execute("UPDATE app_metadata SET value='16' WHERE key='schema_version'")
        for table,columns in {'cases':['category_id','visible','updated_at'],'partners':['materials_revision','profile_materials_revision','profile_updated_at'],'partner_documents':list(schema.FILE_COLUMNS),'deliverables':[*schema.FILE_COLUMNS,'file_type','extracted_text']}.items():
            for column in columns:conn.execute(f'ALTER TABLE {table} DROP COLUMN {column}')
        conn.execute('CREATE TABLE case_share_configs(case_id TEXT PRIMARY KEY REFERENCES cases(id),draft_json TEXT,status TEXT,published_version INTEGER,system_visible INTEGER,created_by TEXT REFERENCES users(id),created_at TEXT,updated_at TEXT)')
        conn.execute('CREATE TABLE case_share_versions(source_id TEXT REFERENCES case_share_configs(case_id),version INTEGER,payload_json TEXT,authorization_epoch INTEGER,reviewed_revision INTEGER,published_by TEXT REFERENCES users(id),published_at TEXT)')
        conn.execute('CREATE TABLE enablement_reviews(id TEXT PRIMARY KEY)')
        conn.execute("INSERT INTO users(id,username,hashed_password,role,status,created_at,updated_at) VALUES ('admin','fixture','hash','admin','active','now','now')")
        conn.execute("INSERT INTO partners(id,name,ai_profile,created_at) VALUES ('p','伙伴','保留旧画像','now')")
        conn.execute("INSERT INTO cases(id,partner_id,title,description,created_at) VALUES ('c','p','内部标题','内部原文','now')")
        conn.execute("INSERT INTO partner_documents(id,partner_id,filename,file_path,file_type,extracted_text,created_at) VALUES ('d','p','old.pptx','/private/original.pptx','pptx','旧提取缓存','now')")
        conn.execute("INSERT INTO case_share_configs VALUES ('c','{}','published',1,1,'admin','now','now')")
        conn.execute("INSERT INTO case_share_versions VALUES ('c',1,?,1,1,'admin','now')",(json.dumps({'title':'旧公开标题','summary':'旧公开摘要','_permissions':{'system_visible':True}}),))

@pytest.mark.parametrize('fail',[True,False])
def test_postgres_transaction_rollback_and_repeatable_migration(fail):
    legacy()
    with get_db() as conn:before=snapshot(conn)
    if fail:
        with pytest.raises(RuntimeError,match='injected'):
            with get_db() as conn:schema.migrate(conn,fault=lambda:(_ for _ in ()).throw(RuntimeError('injected')))
        with get_db() as conn:
            assert snapshot(conn)==before
            assert 'visible' not in [r['name'] for r in inspect(conn.connection).get_columns('cases')]
    with get_db() as conn:assert schema.migrate(conn)['schema_version']==17
    with get_db() as conn:
        assert schema.migrate(conn)['already_current']
        assert tuple(conn.execute('SELECT id,title,description,visible FROM cases').fetchone())==('c','内部标题','内部原文',0)
        assert conn.execute('SELECT ai_profile FROM partners').fetchone()[0]=='保留旧画像'
        assert conn.execute('SELECT file_path FROM partner_documents').fetchone()[0]=='/private/original.pptx'
        assert '旧公开标题' in conn.execute("SELECT reason FROM enablement_audit_events WHERE action='legacy_content_preserved'").fetchone()[0]
        assert not {'case_share_configs','case_share_versions','enablement_reviews'} & set(inspect(conn.connection).get_table_names())
        assert not foreign_key_violations(conn)

def test_postgres_migration_refuses_wrong_version_without_writing():
    with get_db() as conn:conn.execute("UPDATE app_metadata SET value='15' WHERE key='schema_version'")
    with get_db() as conn:before=snapshot(conn)
    with pytest.raises(RuntimeError,match='schema 16'):
        with get_db() as conn:schema.migrate(conn)
    with get_db() as conn:assert snapshot(conn)==before
