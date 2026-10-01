"""Independent pg_catalog comparison; runtime connections are READ ONLY.

Uses the existing protected test-schema factory and initializer only for the
new target. Every observation is made through a separate psycopg connection.
No production rows, credentials or sequence values are emitted.
"""
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
import psycopg
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url


def direct(url, *, readonly=True):
    u = make_url(url)
    options = u.query.get('options', '')
    if readonly:
        options += ' -cdefault_transaction_read_only=on'
    return psycopg.connect(host=u.host, port=u.port or 5432, dbname=u.database,
                          user=u.username, password=u.password, options=options,
                          application_name='banfei_independent_review',
                          connect_timeout=5, row_factory=dict_row)


QUERIES = {
    'columns': """SELECT c.relname AS table_name, a.attname AS column_name,
        format_type(a.atttypid,a.atttypmod) AS type, a.attnotnull AS not_null,
        pg_get_expr(d.adbin,d.adrelid) AS default_expr, a.attidentity AS identity,
        a.attgenerated AS generated, co.collname AS collation
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
        LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
        LEFT JOIN pg_collation co ON co.oid=a.attcollation
        WHERE n.nspname=current_schema() AND c.relkind IN ('r','p')
        ORDER BY c.relname,a.attname""",
    'constraints': """SELECT c.relname AS table_name, con.contype AS type,
        pg_get_constraintdef(con.oid,true) AS definition, con.condeferrable AS deferrable,
        con.condeferred AS deferred, con.convalidated AS validated
        FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=current_schema() ORDER BY c.relname,con.contype,definition""",
    'indexes': """SELECT t.relname AS table_name, am.amname AS method,
        i.indisunique AS unique, i.indisprimary AS primary, i.indisvalid AS valid,
        i.indisready AS ready, i.indnullsnotdistinct AS nulls_not_distinct,
        ARRAY(SELECT pg_get_indexdef(i.indexrelid,k,true)
              FROM generate_series(1,i.indnatts) k) AS keys,
        i.indnkeyatts AS key_count, pg_get_expr(i.indpred,i.indrelid) AS predicate
        FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid
        JOIN pg_namespace n ON n.oid=t.relnamespace
        JOIN pg_class ic ON ic.oid=i.indexrelid JOIN pg_am am ON am.oid=ic.relam
        WHERE n.nspname=current_schema() ORDER BY t.relname,keys""",
    'sequences': """SELECT s.relname AS sequence_name, format_type(q.seqtypid,NULL) AS type,
        q.seqstart AS start,q.seqincrement AS increment,q.seqmin AS min,q.seqmax AS max,
        q.seqcache AS cache,q.seqcycle AS cycle,t.relname AS owned_table,
        a.attname AS owned_column,d.deptype AS dependency
        FROM pg_class s JOIN pg_namespace n ON n.oid=s.relnamespace
        JOIN pg_sequence q ON q.seqrelid=s.oid
        LEFT JOIN pg_depend d ON d.classid='pg_class'::regclass AND d.objid=s.oid
          AND d.refclassid='pg_class'::regclass AND d.deptype IN ('a','i')
        LEFT JOIN pg_class t ON t.oid=d.refobjid
        LEFT JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=d.refobjsubid
        WHERE n.nspname=current_schema() ORDER BY s.relname""",
    'relations': """SELECT c.relname,c.relkind,c.relpersistence,c.relrowsecurity,c.relforcerowsecurity
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=current_schema() AND c.relkind IN ('r','p','v','m') ORDER BY c.relname""",
    'triggers': """SELECT c.relname AS table_name,t.tgname AS trigger_name,
        t.tgenabled AS enabled,pg_get_triggerdef(t.oid,true) AS definition
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=current_schema() AND NOT t.tgisinternal ORDER BY c.relname,t.tgname""",
    'functions': """SELECT p.proname,pg_get_function_identity_arguments(p.oid) AS arguments,
        pg_get_functiondef(p.oid) AS definition FROM pg_proc p
        JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname=current_schema() AND p.prokind IN ('f','p') ORDER BY p.proname,arguments""",
}


def catalog(url):
    with direct(url) as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        identity = conn.execute("""SELECT current_database() AS database,current_schema() AS schema,
            current_user AS role,inet_server_addr()::text AS server,inet_server_port() AS port,
            current_setting('transaction_read_only') AS readonly,
            current_setting('server_version') AS server_version""").fetchone()
        result = {}
        for key, query in QUERIES.items():
            rows = conn.execute(query).fetchall()
            normalized = json.dumps(rows, ensure_ascii=False, sort_keys=True, default=str)
            # Object namespace names differ intentionally, object semantics do not.
            normalized = normalized.replace(identity['schema']+'.', '<schema>.')
            result[key] = json.loads(normalized)
        return identity,result


def difference(a,b):
    result={}
    for key in a:
        left=[json.dumps(x,sort_keys=True) for x in a[key]]
        right=[json.dumps(x,sort_keys=True) for x in b[key]]
        if sorted(left)!=sorted(right):
            result[key]={'runtime_only':[json.loads(x) for x in left if x not in right],
                         'initialized_only':[json.loads(x) for x in right if x not in left]}
    return result


def main():
    runtime=json.loads((ROOT/'.isolation/runtime/dev/environment.json').read_text())
    validation=json.loads((ROOT/'.isolation/runtime/dev/validation-environment.json').read_text())
    os.environ['BANFEI_TEST_DATABASE_URL']=validation['BANFEI_TEST_DATABASE_URL']
    from backend.tests.postgres_support import empty_postgres_schema
    from backend.app.postgres_storage import initialize_empty_schema
    runtime_identity,live=catalog(runtime['DATABASE_URL'])
    assert runtime_identity['database']=='banfei_agent' and runtime_identity['readonly']=='on'
    with empty_postgres_schema() as scoped:
        initialize_empty_schema(scoped)
        fresh_identity,fresh=catalog(scoped)
        assert fresh_identity['database'] in ('banfei_agent_test','banfei_validation')
        assert fresh_identity['schema'].startswith('validation_')
        delta=difference(live,fresh)
    with direct(validation['BANFEI_TEST_DATABASE_URL']) as conn:
        cleaned=not conn.execute('SELECT 1 FROM pg_namespace WHERE nspname=%s',
                                  (fresh_identity['schema'],)).fetchone()
    imports={}
    for path in sorted((ROOT/'scripts').glob('migrate_*.py')):
        try:
            importlib.import_module('scripts.'+path.stem)
            imports[path.name]='ok'
        except Exception as error:
            imports[path.name]={'error':type(error).__name__,'message':str(error)}
    report={'runtime':runtime_identity,'initialized':fresh_identity,'differences':delta,
            'runtime_catalog':live,'initialized_catalog':fresh,
            'schema_removed':cleaned,'migration_imports':imports}
    output=Path(__file__).with_name('catalog-result.json')
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'runtime':runtime_identity,'initialized':fresh_identity,
        'counts':{k:len(v) for k,v in live.items()},'differences':delta,
        'schema_removed':cleaned,'migration_imports':imports},ensure_ascii=False))


if __name__=='__main__':main()
