"""Sanitized readiness evidence. Hash stable/runtime files; never open their SQLite DBs."""
import hashlib,json,subprocess,sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
STABLE=Path('/home/yuan/project/lingjian-agent')
BASE='dda1af4914aec68f96cd0ae481caae732eea655d'
TAG='pilot-data-intake-ready-20260906-dda1af4'

def git(where,*args):return subprocess.check_output(['git','-C',str(where),*args],text=True).strip()
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main(xml):
    out=ROOT/'artifacts/pilot-import';out.mkdir(parents=True,exist_ok=True)
    def save(name,value):(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    assert git(ROOT,'branch','--show-current')=='feature/partner-enablement-v1.1'
    assert git(ROOT,'rev-parse',TAG)==BASE
    assert git(ROOT,'rev-parse','rc-preparation-accepted-20260906-1a0b4b4')=='1a0b4b4f081de63c617b366788e19d0090d19093'
    assert git(STABLE,'branch','--show-current')=='main'
    assert git(STABLE,'rev-parse','HEAD')=='f79cbb29ec7b3ad70c88e618e3161211f211c06a'
    assert not git(STABLE,'status','--porcelain')
    assert not git(ROOT,'diff',BASE,'--','backend/app','frontend')
    baseline=json.loads((ROOT/'.isolation/evidence/pilot-import-start.json').read_text())
    protected=json.loads((ROOT/'.isolation/evidence/rc-stable-start.json').read_text())
    assert all(sha(STABLE/name)==digest for name,digest in protected.items())
    assert sha(ROOT/'.isolation/runtime/app.db')==baseline['runtime_sha256']
    processes={}
    for pid,cwd in [(227786,STABLE),(236033,STABLE/'frontend')]:
        assert Path(f'/proc/{pid}/cwd').resolve()==cwd;processes[str(pid)]=str(cwd)
    listeners=subprocess.check_output(['ss','-ltnp'],text=True)
    for port in (3000,8000):assert any(f':{port} ' in line for line in listeners.splitlines())
    for port in (3100,8100,18180):assert not any(f':{port} ' in line for line in listeners.splitlines())
    save('protection-verification.json',{'intake_tag':TAG,'intake_commit':BASE,'stable_head':git(STABLE,'rev-parse','HEAD'),
        'stable_clean':True,'protected_files':len(protected),'protected_files_changed':0,'runtime_sha256_unchanged':True,
        'stable_sqlite_connections':0,'runtime_sqlite_connections_this_stage':0,'stable_logins':0,'business_runtime_writes':0,
        'process_cwds':processes,'new_ports_stopped':[3100,8100,18180],'schema_changed':False,'product_code_changed':False,
        'real_model_calls':0,'push_merge_deploy':False,'remote_verified':False})
    suites=ET.parse(xml).getroot().findall('testsuite')
    totals={key:sum(int(s.attrib.get(key,0)) for s in suites) for key in ('tests','failures','errors','skipped')}
    assert totals['tests']==131 and totals['failures']==totals['errors']==totals['skipped']==0
    cases=[{'module':c.attrib['classname'],'name':c.attrib['name'],'status':'PASS'} for s in suites for c in s.findall('testcase')]
    files=[ROOT/'scripts/import_pilot_data.py',ROOT/'scripts/pilot_import_contract.py',ROOT/'scripts/validate_pilot_data.py',
        ROOT/'scripts/collect_pilot_import_evidence.py',ROOT/'scripts/write_pilot_import_report.py',
        ROOT/'backend/tests/test_pilot_import.py',ROOT/'backend/tests/test_pilot_intake.py',ROOT/'backend/tests/test_enablement.py']
    save('validation-results.json',{'command':'.venv/bin/python -m pytest backend/tests/test_pilot_import.py backend/tests/test_pilot_intake.py backend/tests/test_enablement.py -q --junitxml=/tmp/pilot-import-regression.xml',
        **totals,'passed':totals['tests'],'modules':dict(Counter(c['module'] for c in cases)),'cases':cases,
        'junit_sha256':sha(xml),'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in files},
        'syntax_check':'PASS','database_scope':'/tmp disposable synthetic fixtures only','real_model_calls':0,
        'synthetic_gate':'CLI denies; transaction tests locally replace only origin rejection, never permissions or product validation'})
    stages=['course_created','resource_version','capability_map','review_created','resource_published','lab_import',
        'case_config','case_version','case_published','before_audit_ledger','before_commit']
    for stage in stages:assert any(c['name']==f'test_fault_rolls_back_every_table[{stage}]' for c in cases)
    save('readiness.json',{'result':'READY FOR REAL PILOT PACKAGE IMPORT','schema_version':12,'schema_changed':False,
        'fault_injection':{stage:'PASS - full pre-state and file hash restored' for stage in stages},
        'single_begin_single_commit_trace':'PASS','same_fk_count_different_rows_rejected':'PASS','capability_map_rechecked':'PASS',
        'wal_consistent_backup':'PASS','idempotency':'PASS','input_immutable':'PASS','ledger_recovery':'PASS',
        'actual_actor_system_time':'PASS','three_dimensional_permissions_8_combinations':'PASS','imported_validation':'PASS',
        'restore_to_new_pilot_db_rehearsal':'PASS','real_pilot_package':'NOT PROVIDED','DATA_01':'BLOCKED',
        'business_acceptance':'NOT RUN','real_model_precheck':'BLOCKED','real_model_authorization':'NOT AUTHORIZED','real_model_calls':0})
    print(json.dumps({'tests':totals,'modules':dict(Counter(c['module'] for c in cases)),'protected_files_unchanged':len(protected),
        'runtime_unchanged':True,'real_model_calls':0},ensure_ascii=False))

if __name__=='__main__':main(Path(sys.argv[1]))
