"""Replay the real isolated v9 snapshot when present; never connect to the original DB."""
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest
from backend.app.enablement_schema import migrate_to_v10

SNAPSHOT=Path(__file__).resolve().parents[2]/'.isolation/snapshots/baseline.db'


def table_digest(conn, table):
    rows=conn.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
    return hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()


def state(conn):
    tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='app_metadata'")]
    return {t:table_digest(conn,t) for t in tables}


@pytest.fixture
def v9_db(tmp_path):
    target=tmp_path/'v9.db'
    if SNAPSHOT.exists():
        with sqlite3.connect(SNAPSHOT.as_uri()+'?mode=ro',uri=True) as a, sqlite3.connect(target) as b: a.backup(b)
    else:
        # Clean-checkout fallback, with both valid rows and an intentional pre-existing orphan.
        with sqlite3.connect(target) as c:
            c.executescript('''CREATE TABLE app_metadata(key TEXT PRIMARY KEY,value TEXT);
            INSERT INTO app_metadata VALUES ('schema_version','9');
            CREATE TABLE users(id TEXT PRIMARY KEY); INSERT INTO users VALUES ('admin');
            CREATE TABLE partners(id TEXT PRIMARY KEY); INSERT INTO partners VALUES ('partner');
            CREATE TABLE cases(id TEXT PRIMARY KEY,partner_id TEXT REFERENCES partners(id));
            INSERT INTO cases VALUES ('valid','partner'); INSERT INTO cases VALUES ('orphan','missing');
            CREATE TABLE capability_tags(id TEXT PRIMARY KEY); INSERT INTO capability_tags VALUES ('tag');''')
    return target


def test_additive_v10_preserves_every_old_row_and_is_idempotent(v9_db):
    with sqlite3.connect(v9_db) as c:
        c.execute('PRAGMA foreign_keys=ON')
        before=state(c); fk=c.execute('PRAGMA foreign_key_check').fetchall()
        assert c.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]=='9'
        migrate_to_v10(c)
        assert c.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]=='10'
        assert {t:table_digest(c,t) for t in before}==before
        assert c.execute('PRAGMA foreign_key_check').fetchall()==fk
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        first=state(c)
        migrate_to_v10(c)
        assert state(c)==first


@pytest.mark.parametrize('failure_point',[1,3,7,10])
def test_migration_failure_is_atomic_and_retry_recovers(v9_db,failure_point):
    class FailingConnection(sqlite3.Connection):
        writes=0
        def execute(self,sql,*args):
            if sql.startswith('CREATE ') or sql.startswith("UPDATE app_metadata SET value='10'"):
                self.writes+=1
                if self.writes==failure_point: raise sqlite3.OperationalError('synthetic migration failure')
            return super().execute(sql,*args)
    with sqlite3.connect(v9_db,factory=FailingConnection) as c:
        before=state(c)
        with pytest.raises(sqlite3.OperationalError): migrate_to_v10(c)
        assert state(c)==before
        assert c.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]=='9'
        c.writes=100
        migrate_to_v10(c)
        assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


def test_recovery_snapshot_can_create_fresh_independent_database(v9_db,tmp_path):
    recovery=tmp_path/'recovered.db'
    with sqlite3.connect(v9_db) as source, sqlite3.connect(recovery) as target: source.backup(target)
    with sqlite3.connect(recovery) as c:
        migrate_to_v10(c)
        assert c.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]=='10'
    with sqlite3.connect(v9_db) as c:
        assert c.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]=='9'
    assert v9_db.stat().st_ino != recovery.stat().st_ino


def test_legacy_repair_stays_closed_on_v10(client):
    from backend.app.database import DATABASE_PATH
    from backend.scripts import repair_historical_data as repair
    with sqlite3.connect(DATABASE_PATH) as c:
        with pytest.raises(repair.RepairConflict): repair.inventory(c)
