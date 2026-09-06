import json,sqlite3,hashlib
from pathlib import Path
import pytest
from backend.app.development_schema import migrate_to_v12,DDL

@pytest.mark.parametrize('fault_at',list(range(1,len(DDL)+3))+[None])
def test_v12_failure_atomic_replay_and_old_data(tmp_path,fault_at):
    source=Path(__file__).resolve().parents[2]/'.isolation/snapshots/phase-c-pre-v12.db'
    target=tmp_path/'v12.db'
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(target) as dst:src.backup(dst)
    def digest(conn):
        return {r[0]:hashlib.sha256(json.dumps(conn.execute(f'SELECT * FROM "{r[0]}" ORDER BY rowid').fetchall(),ensure_ascii=False).encode()).hexdigest() for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('app_metadata','model_usage_configs')").fetchall()}
    class Fault(sqlite3.Connection):
        n=0
        def execute(self,sql,*args):
            if sql.startswith(('CREATE ','INSERT OR IGNORE INTO model_usage_configs',"UPDATE app_metadata SET value='12'")):
                self.n+=1
                if self.n==fault_at:raise sqlite3.OperationalError('injected failure')
            return super().execute(sql,*args)
    with sqlite3.connect(target,factory=Fault) as conn:
        before=digest(conn);fk=conn.execute('PRAGMA foreign_key_check').fetchall()
        if fault_at:
            with pytest.raises(sqlite3.OperationalError):migrate_to_v12(conn)
            assert conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]=='11'
            assert conn.execute("SELECT count(*) FROM sqlite_master WHERE name='development_plans'").fetchone()[0]==0
        migrate_to_v12(conn);migrate_to_v12(conn)
        after=digest(conn);assert all(after[k]==v for k,v in before.items())
        assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==fk
        assert conn.execute("SELECT model_config_id FROM model_usage_configs WHERE scene_key='partner_development'").fetchone()[0] is None
