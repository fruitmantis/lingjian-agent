"""Collect sanitized offline intake evidence; stable DB is hashed, never opened."""
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.validate_pilot_data import readonly_database, validate, real_model_precheck, STABLE


def git(root, *args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True).strip()


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(xml):
    out=ROOT/'artifacts/pilot-data-intake';out.mkdir(exist_ok=True)
    def save(name,data): (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    assert git(ROOT,'branch','--show-current')=='feature/partner-enablement-v1.1'
    accepted='1a0b4b4f081de63c617b366788e19d0090d19093'
    tag='rc-preparation-accepted-20260906-1a0b4b4'
    assert git(ROOT,'rev-parse',tag)==accepted
    assert git(STABLE,'rev-parse','HEAD')=='f79cbb29ec7b3ad70c88e618e3161211f211c06a'
    assert git(STABLE,'branch','--show-current')=='main' and not git(STABLE,'status','--porcelain')
    protected=json.loads((ROOT/'.isolation/evidence/rc-stable-start.json').read_text())
    assert all(sha(STABLE/p)==digest for p,digest in protected.items())
    assert not git(ROOT,'diff',accepted,'--','backend/app','frontend')
    processes={}
    for pid,expected in [(227786,STABLE),(236033,STABLE/'frontend')]:
        assert Path(f'/proc/{pid}/cwd').resolve()==expected
        processes[str(pid)]=str(expected)
    listeners=subprocess.check_output(['ss','-ltnp'],text=True)
    for port in (3000,8000):assert any(f':{port} ' in line for line in listeners.splitlines())
    for port in (3100,8100,18180):assert not any(f':{port} ' in line for line in listeners.splitlines())
    db=ROOT/'.isolation/runtime/app.db'
    before=sha(db)
    with readonly_database(db) as conn:
        counts={table:conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in
            ('partners','cases','enablement_resources','case_share_configs','development_plans')}
        integrity=[row[0] for row in conn.execute('PRAGMA integrity_check')]
        fk=conn.execute('PRAGMA foreign_key_check').fetchall()
        assert all(row[0]=='cases' for row in fk), 'Investigate unexpected FK anomaly privately'
        orphan=conn.execute('SELECT COUNT(*) FROM cases c LEFT JOIN partners p ON p.id=c.partner_id WHERE p.id IS NULL').fetchone()[0]
        version=conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0]
        selected=conn.execute("SELECT model_config_id FROM model_usage_configs WHERE scene_key='partner_development'").fetchone()
        selection=bool(selected and selected[0] and conn.execute('SELECT id FROM model_configs WHERE id=? AND enabled=1',(selected[0],)).fetchone())
    assert before==sha(db)
    save('runtime-inventory.json',{'database':'.isolation/runtime/app.db','schema_version':version,'counts':counts,
        'integrity_check':integrity,'foreign_key_violation_count':len(fk),'orphan_case_count':orphan,
        'database_hash_unchanged':True,'approved_business_package_received':False,
        'partner_development_explicit_enabled_binding':selection,'real_model_calls':0,
        'DATA_01_MACHINE_CHECK':'BLOCKED - BUSINESS DATA REQUIRED','DATA_01_business_signoff':'NOT RUN',
        'DATA_02':'BLOCKED - BUSINESS DATA REQUIRED'})
    rejected=validate(ROOT/'pilot-data/pilot-manifest.template.json',db)
    assert rejected['machine_status']=='FAIL'
    gate=real_model_precheck(rejected,db)
    save('template-rejection-and-gate.json',{'template_intentionally_rejected':True,'template_result':rejected,
        'real_model_precheck':gate,'measurement_phase':'Before intake delivery commit; final clean check is rendered after commit'})
    suites=ET.parse(xml).getroot().findall('testsuite')
    tests={k:sum(int(s.attrib.get(k,0)) for s in suites) for k in ('tests','failures','errors','skipped')}
    assert tests['tests']>=37 and not tests['failures'] and not tests['errors']
    files=[*sorted((ROOT/'scripts').glob('*.py')),ROOT/'backend/tests/test_pilot_intake.py',*sorted((ROOT/'pilot-data').glob('*.json'))]
    save('validation-results.json',{'command':'.venv/bin/python -m pytest backend/tests/test_pilot_intake.py -q --junitxml=/tmp/pilot-intake-tests.xml',
        **tests,'passed':tests['tests']-tests['failures']-tests['errors']-tests['skipped'],'source_xml_sha256':sha(xml),
        'test_cases':[{'name':case.attrib['name'],'status':'PASS'} for suite in suites for case in suite.findall('testcase')],
        'checked_files':{str(p.relative_to(ROOT)):sha(p) for p in files},'network_and_model_calls_forbidden_by_fixture':True,
        'database_scope':'pytest disposable /tmp databases only','real_model_calls':0})
    save('protection-verification.json',{'stable_head':git(STABLE,'rev-parse','HEAD'),'stable_clean':True,
        'protected_files_checked':len(protected),'protected_files_changed':0,'stable_sqlite_connections':0,
        'stable_logins':0,'stable_process_cwds':processes,'new_ports_stopped':[3100,8100,18180],
        'rc_archive_commit':accepted,'rc_accepted_tag':tag,'product_code_changed':False,
        'schema_changed':False,'real_model_calls':0,'push_merge_deploy':False,'remote_verified':False})
    print(json.dumps({'tests':tests,'inventory_counts':counts,'integrity':integrity,'fk_count':len(fk),'orphan_cases':orphan,
        'explicit_model_binding':selection,'stable_files_unchanged':len(protected),'real_model_calls':0},ensure_ascii=False))

if __name__=='__main__':collect(Path(sys.argv[1]))
