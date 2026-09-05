"""Verify migration only on this worktree's isolated runtime copy. Print no row content."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


def rows(conn,table):
    return conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()


def summarize(conn):
    tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    return {'schema':conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0],
            'tables':{t:{'count':len(rows(conn,t)),'sha256':hashlib.sha256(json.dumps(rows(conn,t),ensure_ascii=False).encode()).hexdigest()} for t in tables},
            'integrity':conn.execute('PRAGMA integrity_check').fetchall(),
            'foreign_keys':conn.execute('PRAGMA foreign_key_check').fetchall()}


def main():
    runtime=ROOT/'.isolation/runtime/app.db'
    if not runtime.exists() or runtime.is_symlink(): raise RuntimeError('Missing independent runtime copy')
    from backend.app.database import DATABASE_PATH, initialize_storage
    if DATABASE_PATH.resolve()!=runtime.resolve(): raise RuntimeError('Refusing database outside isolated copy')
    with sqlite3.connect(runtime) as c: before=summarize(c)
    initialize_storage()
    with sqlite3.connect(runtime) as c: after=summarize(c)
    initialize_storage()
    with sqlite3.connect(runtime) as c: repeated=summarize(c)
    unchanged={t:after['tables'][t]==v for t,v in before['tables'].items() if t!='app_metadata'}
    assert all(unchanged.values())
    assert after==repeated
    assert after['foreign_keys']==before['foreign_keys']
    assert after['integrity']==[('ok',)] and after['schema']=='10'
    evidence={'before':before,'after':after,'old_tables_unchanged':unchanged,'repeat_identical':True,'new_foreign_key_violations':0}
    target=ROOT/'.isolation/evidence/migration.json'
    target.write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    print(json.dumps({'schema_before':before['schema'],'schema_after':after['schema'],'unchanged_old_tables':len(unchanged),'new_tables':len(after['tables'])-len(before['tables']),'existing_foreign_key_violations':len(before['foreign_keys']),'new_foreign_key_violations':0,'integrity':'ok','repeat_identical':True},ensure_ascii=False))

if __name__=='__main__': main()
