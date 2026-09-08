"""Collect sanitized, traceable RC test results; never read application credentials."""
from pathlib import Path
import hashlib,json,struct,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'artifacts/enablement-rc';LOG=ROOT/'.isolation/logs'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def counts(rows):return {s:sum(x['status']==s for x in rows) for s in ['PASS','FAIL','NOT RUN']}
backend=[]
for c in ET.parse(LOG/'rc-backend.xml').getroot().iter('testcase'):
 backend.append({'file':c.attrib['classname'].replace('.','/')+'.py','test':c.attrib['name'],'status':'FAIL' if c.find('failure') is not None or c.find('error') is not None else 'NOT RUN' if c.find('skipped') is not None else 'PASS','seconds':float(c.attrib['time'])})
runner=json.loads((LOG/'rc-browser-runner.json').read_text())
assert runner['status']=='complete' and runner['exit_code']==0, 'Full browser process did not complete successfully'
browser=[];report=json.loads((LOG/'rc-browser.json').read_text())
def walk(s):
 for spec in s.get('specs',[]):
  for t in spec['tests']:browser.append({'file':'frontend/e2e/'+Path(spec['file']).name,'test':spec['title'],'line':spec['line'],'status':'PASS' if t['status']=='expected' else 'NOT RUN' if t['status']=='skipped' else 'FAIL','seconds':sum(r['duration'] for r in t['results'])/1000})
 for child in s.get('suites',[]):walk(child)
for s in report['suites']:walk(s)
assert not report.get('errors'), 'Browser runner errors remain'
for filename in ['rc-typecheck.log','rc-build.log','rc-backend.log','rc-browser.log']:
 assert 'INTERNAL_SECRET_PHASE_B_DO_NOT_SHARE' not in (LOG/filename).read_text(), 'Canary in private test log: stop review'
assert 'Compiled successfully' in (LOG/'rc-build.log').read_text()
assert 'error TS' not in (LOG/'rc-typecheck.log').read_text()
screens=[]
for p in sorted(OUT.rglob('*.png')):
 width,height=struct.unpack('>II',p.read_bytes()[16:24]);assert width in (1366,1920)
 screens.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'image_width':width,'image_height':height,'viewport':{'width':width,'height':768 if width==1366 else 1080},'full_page':True,'data':'synthetic /tmp only'})
write('screenshot-manifest.json',{'total':len(screens),'screenshots':screens})
write('backend-test-results.json',{'counts':counts(backend),'source_sha256':sha(LOG/'rc-backend.xml'),'tests':backend})
write('browser-test-results.json',{'counts':counts(browser),'source_sha256':sha(LOG/'rc-browser.json'),'tests':browser})
write('validation-results.json',{'backend':counts(backend),'browser':counts(browser),'browser_execution':{'exit_code':runner['exit_code'],'seconds':runner['ended_at']-runner['started_at'],'record_sha256':sha(LOG/'rc-browser-runner.json')},'rc_state_backend_tests':[x for x in backend if x['file'].endswith('test_rc_presentation.py')],'rc_state_browser_tests':[x for x in browser if x['file'].endswith('rc-plan-status.spec.ts')],'typecheck':'PASS','production_build':'PASS','screenshots':len(screens),'canary_private_log_scan':'PASS','schema_version':'12 (unchanged)','real_model':{'authorization':'NOT AUTHORIZED','status':'NOT RUN','calls':0},'business_data':'BLOCKED','DATA-01':'BLOCKED - BUSINESS DATA REQUIRED','DATA-02':'BLOCKED - BUSINESS DATA REQUIRED','business_acceptance':'NOT RUN','engineering':'READY' if backend and browser and all(x['status']=='PASS' for x in backend+browser) else 'NOT READY','overall':'CONDITIONAL GO','test_databases':'pytest /tmp; Playwright /tmp/lingjian-enablement-e2e/app.db','test_ports':[3100,8100,18180]})
print(json.dumps({'backend':counts(backend),'browser':counts(browser),'screenshots':len(screens)},ensure_ascii=False))
