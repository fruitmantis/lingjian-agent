"""Schema 17 preserves originals and business IDs, removes only superseded case machinery."""
import json
import os
import sqlite3
from pathlib import Path
import pytest
from backend.app import database,partner_materials_schema as schema
from backend.app.postgres_storage import Connection,engine_for
from .postgres_support import empty_postgres_schema


def legacy(path,monkeypatch):
    with monkeypatch.context() as patch:
        patch.setenv('DATABASE_URL','sqlite://')
        patch.setattr(database,'DATABASE_PATH',path)
        patch.setattr(database,'DATA_DIR',path.parent)
        patch.setattr(schema,'migrate',lambda *_:None)
        database.initialize_storage()
    conn=sqlite3.connect(path);conn.row_factory=sqlite3.Row
    # Fixtures only. The normal authentication bootstrap isn't needed for a schema replay.
    conn.execute("INSERT INTO users (id,username,hashed_password,role,status,created_at,updated_at) VALUES ('admin','fixture','hash','admin','active','now','now')")
    conn.execute("INSERT INTO partners (id,name,ai_profile,created_at) VALUES ('p','伙伴','保留旧画像','now')")
    conn.execute("INSERT INTO cases (id,partner_id,title,description,created_at) VALUES ('c','p','内部标题','内部原文','now')")
    conn.execute("INSERT INTO partner_documents (id,partner_id,filename,file_path,file_type,extracted_text,created_at) VALUES ('d','p','old.pptx','/private/original.pptx','pptx','旧提取缓存','now')")
    conn.execute("INSERT INTO case_share_configs (case_id,draft_json,status,published_version,system_visible,created_by,created_at,updated_at) VALUES ('c','{}','published',1,1,'admin','now','now')")
    payload={'title':'旧公开标题','summary':'旧公开摘要','_permissions':{'system_visible':True}}
    conn.execute("INSERT INTO case_share_versions VALUES ('c',1,?,1,1,'admin','now')",(json.dumps(payload),));conn.commit();return conn

@pytest.mark.parametrize('fail',[True,False])
def test_sqlite_transaction_rollback_and_repeatable_migration(tmp_path,monkeypatch,fail):
    conn=legacy(tmp_path/'legacy.db',monkeypatch)
    if fail:
        with pytest.raises(RuntimeError):
            with conn:schema.migrate(conn,fault=lambda:(_ for _ in ()).throw(RuntimeError('injected')))
        assert conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]=='16'
        assert 'visible' not in [r[1] for r in conn.execute('PRAGMA table_info(cases)')]
    with conn: result=schema.migrate(conn)
    assert result['schema_version']==17
    assert schema.migrate(conn)['already_current']
    assert tuple(conn.execute('SELECT id,title,description,visible FROM cases').fetchone())==('c','内部标题','内部原文',0)
    assert conn.execute('SELECT ai_profile FROM partners').fetchone()[0]=='保留旧画像'
    assert conn.execute('SELECT file_path FROM partner_documents').fetchone()[0]=='/private/original.pptx'
    assert '旧公开标题' in conn.execute("SELECT reason FROM enablement_audit_events WHERE action='legacy_content_preserved'").fetchone()[0]
    assert not conn.execute("SELECT name FROM sqlite_master WHERE name IN ('case_share_configs','case_share_versions','enablement_reviews')").fetchall()
    assert not conn.execute('PRAGMA foreign_key_check').fetchall();conn.close()

@pytest.mark.skipif(not os.environ.get('BANFEI_TEST_DATABASE_URL'),reason='Dedicated PostgreSQL test database required')
def test_postgres_migration_ddl_rollback_and_preserved_rows(tmp_path,monkeypatch):
    source=legacy(tmp_path/'pg-source.db',monkeypatch)
    # Replay the real v16 SQLite table definitions in a disposable PostgreSQL schema.
    # Only migration-relevant tables are required; runtime business tables are not mutated.
    names=['app_metadata','users','partners','cases','partner_documents','deliverables','case_share_configs','case_share_versions','enablement_reviews','enablement_audit_events']
    with empty_postgres_schema() as url:
        engine=engine_for(url)
        with engine.begin() as raw:
            for name in names:
                sql=source.execute("SELECT sql FROM sqlite_master WHERE name=?",(name,)).fetchone()[0]
                raw.exec_driver_sql(sql)
                rows=source.execute('SELECT * FROM '+name).fetchall()
                if rows:
                    columns=rows[0].keys();statement=f"INSERT INTO {name} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
                    conn=Connection(raw)
                    for row in rows: conn.execute(statement,tuple(row))
        with pytest.raises(RuntimeError):
            with engine.begin() as raw: schema.migrate(Connection(raw),fault=lambda:(_ for _ in ()).throw(RuntimeError('injected')))
        with engine.begin() as raw:
            conn=Connection(raw);assert conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]=='16'
            result=schema.migrate(conn);assert result['schema_version']==17
            assert tuple(conn.execute('SELECT id,title,description,visible FROM cases').fetchone())==('c','内部标题','内部原文',0)
        with engine.connect() as raw: assert schema.migrate(Connection(raw))['already_current']
    source.close()
