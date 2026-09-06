"""Collect actual Phase D results; keep credentials, raw model output and logs private."""
import ast
import hashlib
import json
import struct
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts/enablement-phase-d'
LOG=ROOT/'.isolation/logs'
CANARY='INTERNAL_SECRET_PHASE_B_DO_NOT_SHARE'

def write(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def count(records):
    return {s:sum(r['status']==s for r in records) for s in ['PASS','FAIL','NOT RUN','BLOCKED']}

backend=[];backend_runs=[];properties={};locations={}
for filename,label in [('phase-d-backend-final.xml','full suite excluding owned port 8100 process test'),('phase-d-adapter-final.xml','owned port 8100 process test selected from adapter batch')]:
    root=ET.parse(LOG/filename).getroot();records=[]
    for case in root.iter('testcase'):
        file=case.attrib['classname'].replace('.','/')+'.py'
        if filename=='phase-d-adapter-final.xml' and file!='backend/tests/test_phase_d_process.py':continue
        if file not in locations:
            locations[file]={n.name:n.lineno for n in ast.walk(ast.parse((ROOT/file).read_text())) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        status='FAIL' if case.find('failure') is not None or case.find('error') is not None else 'NOT RUN' if case.find('skipped') is not None else 'PASS'
        prop={p.attrib['name']:p.attrib['value'] for p in case.findall('./properties/property')}
        for key,value in prop.items():
            try:value=json.loads(value)
            except json.JSONDecodeError:pass
            properties.setdefault(key,[]).append(value)
        record={'file':file,'test':case.attrib['name'],'line':locations[file].get(case.attrib['name'].split('[')[0]),'status':status,'seconds':float(case.attrib['time']),'properties':prop}
        records.append(record);backend.append(record)
    backend_runs.append({'label':label,'evidence':'.isolation/logs/'+filename,'sha256':digest(LOG/filename),'counts':count(records),'total':len(records)})
write('backend-test-results.json',{'runs':backend_runs,'tests':backend})

browser=[];browser_runs=[]
for filename,label in [('phase-d-browser-final.json','final full suite')]:
    report=json.loads((LOG/filename).read_text());records=[]
    def walk(suite):
        for spec in suite.get('specs',[]):
            for test in spec['tests']:
                record={'file':'frontend/e2e/'+Path(spec['file']).name,'test':spec['title'],'line':spec['line'],
                    'status':'PASS' if test['status']=='expected' else 'NOT RUN' if test['status']=='skipped' else 'FAIL',
                    'seconds':sum(r['duration'] for r in test['results'])/1000,'outcome':test['status']}
                records.append(record);browser.append(record)
        for child in suite.get('suites',[]):walk(child)
    for suite in report['suites']:walk(suite)
    browser_runs.append({'label':label,'evidence':'.isolation/logs/'+filename,'sha256':digest(LOG/filename),'counts':count(records),'stats':report['stats']})
browser_execution_count=len(browser)
browser=list({(r['file'],r['test']):r for r in browser}.values())
write('browser-test-results.json',{'runs':browser_runs,'execution_count':browser_execution_count,'unique_test_count':len(browser),'tests':browser})

screens=[]
for path in sorted(OUT.rglob('*.png')):
    width,height=struct.unpack('>II',path.read_bytes()[16:24])
    viewport_width=int(path.stem.rsplit('-',1)[-1])
    screens.append({'path':str(path.relative_to(ROOT)),'viewport':{'width':viewport_width,'height':768 if viewport_width==1366 else 1080},'image_width':width,'image_height':height,'full_page':True,'sha256':digest(path),'data':'synthetic only'})
assert len(screens)==52,len(screens)
write('screenshot-manifest.json',{'count':len(screens),'screenshots':screens,'layout_checks':['document scrollWidth <= viewport width','navigation visible inside sidebar','no unhandled page errors in lifecycle/regression runs'],'visual_review_evidence':'docs/enablement/PHASE_D_VISUAL_REVIEW.md'})

# Only final successful execution logs, not the deliberate pre-fix failing test log.
scanned=['phase-d-backend-final.log','phase-d-adapter-final.log','phase-d-browser-final.log','phase-d-typecheck.log','phase-d-build.log']
assert all(CANARY not in (LOG/name).read_text() for name in scanned)
logs=[{'path':'.isolation/logs/'+name,'sha256':digest(LOG/name)} for name in scanned]

matrix=json.loads((OUT/'acceptance-matrix.json').read_text())
for row in matrix['requirements']:
    row['real_model_validation_required']=row['id'] in {'DEV-03','DEV-04','DEV-05','DEV-07','DEV-08','DEV-11','MOD-01','MOD-02'}
    if row['id'].startswith('DATA'):
        row.update(status='BLOCKED',reason='BUSINESS DATA REQUIRED',evidence=['FIRST_PILOT_DATA_CHECKLIST.md']);continue
    if row['id'].startswith('DEV'):
        for file in ['backend/tests/test_phase_d_business_samples.py']:
            if file not in row['automated_tests']:row['automated_tests'].append(file)
    if row['id'].startswith(('CASE','SEC')) and 'backend/tests/test_phase_d_revocation.py' not in row['automated_tests']:row['automated_tests'].append('backend/tests/test_phase_d_revocation.py')
    required=[r for r in backend if r['file'] in row['automated_tests']]+[r for r in browser if r['file'] in row['e2e_tests']]
    missing=set(row['automated_tests']+row['e2e_tests'])-{r['file'] for r in required}
    row['status']='NOT RUN' if missing else 'FAIL' if any(r['status']=='FAIL' for r in required) else 'NOT RUN' if any(r['status']=='NOT RUN' for r in required) else 'PASS'
    row['reason']='本阶段工程/mock 自动化范围通过；真实供应商与业务签审不在该 PASS 内' if row['status']=='PASS' else '缺少执行证据或测试未通过'
    row['verified_test_count']=len(required)
    row['evidence']=['artifacts/enablement-phase-d/backend-test-results.json','artifacts/enablement-phase-d/browser-test-results.json']
    if row['id'].startswith('NFR'):row['evidence'].append('artifacts/enablement-phase-d/validation-results.json')
    row['real_model_status']='BLOCKED - USER AUTHORIZATION REQUIRED' if row['real_model_validation_required'] else 'NOT REQUIRED'
    row['business_review_status']='BLOCKED - BUSINESS DATA REQUIRED' if row['real_business_review_required'] else 'NOT REQUIRED'
for acc in matrix['acceptance']:
    related=[r for r in matrix['requirements'] if acc['id'] in r['acc']]
    acc['requirements']=[r['id'] for r in related]
    if acc['id']=='ACC-20':acc.update(status='BLOCKED',reason='BUSINESS DATA REQUIRED')
    else:
        acc['status']='FAIL' if any(r['status']=='FAIL' for r in related) else 'NOT RUN' if not related or any(r['status']=='NOT RUN' for r in related) else 'PASS'
        acc['reason']='仅本阶段工程/mock 自动化范围；真实业务签审未执行'
    acc['evidence']=['PHASE_D_ACCEPTANCE_MATRIX.md','artifacts/enablement-phase-d/backend-test-results.json','artifacts/enablement-phase-d/browser-test-results.json']
matrix['summary']={'requirements':count(matrix['requirements']),'acceptance':count(matrix['acceptance'])}
write('acceptance-matrix.json',matrix)

lines=['# Phase D 验收矩阵','','唯一需求基线：V1.1 §27，53 项 P0（51 项软件、2 项业务）；ACC 定义来自 §27.1，关联来自 §27.2。P1 与未来事项不混入一期。',
       '', '**PASS 仅表示本阶段工程/mock 自动化证据通过，不代表真实供应商、首批数据或真实业务验收。** 真实模型仍为 BLOCKED - USER AUTHORIZATION REQUIRED，0 调用；业务数据仍为 BLOCKED - BUSINESS DATA REQUIRED。',
       '', '逐测试名称、源码行、耗时、结果及原始结果文件哈希见 `artifacts/enablement-phase-d/backend-test-results.json` 和 `browser-test-results.json`。',
       '', '| P0 | 唯一需求定义 | ACC | 后端测试 | E2E | 真实模型 | 真实业务 | 工程状态 | 证据/未通过原因 |','|---|---|---|---|---|---|---|---|---|']
for r in matrix['requirements']:
    lines.append('| '+' | '.join([r['id'],r['definition'],','.join(r['acc']),'<br>'.join(r['automated_tests']),'<br>'.join(r['e2e_tests']),r.get('real_model_status','否'),r.get('business_review_status','BLOCKED - BUSINESS DATA REQUIRED'),r['status'],'<br>'.join(r['evidence'])+'<br>'+r['reason']])+' |')
lines+=['','## ACC-01～20','','| ACC | 验收定义 | 状态 | 原因 |','|---|---|---|---|']
for r in matrix['acceptance']:lines.append('| '+' | '.join([r['id'],r['definition'],r['status'],r['reason']])+' |')
(ROOT/'PHASE_D_ACCEPTANCE_MATRIX.md').write_text('\n'.join(lines)+'\n')

result={'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),
    'phase_c_accepted':'351489c3d3c89899837930bd7aab01fe61f4a52a','tested_implementation_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'schema_changed':False,
    'backend':{'runs':backend_runs,'total':len(backend),**count(backend),'warnings':'2 existing Starlette 422 constant deprecation warnings'},
    'browser':{'runs':browser_runs,'total':len(browser),'execution_count':browser_execution_count,**count(browser)},
    'typecheck':{'status':'PASS','command':'npm run typecheck','evidence':'.isolation/logs/phase-d-typecheck.log'},
    'build':{'status':'PASS','command':'npm run build','evidence':'.isolation/logs/phase-d-build.log'},
    'metrics':{key:values[-1] for key,values in properties.items() if key in ['http_creation','kill_restart','catalog_performance','candidate_performance','parallel_plans','fixed_samples']},
    'supplier_mock':properties.get('loopback_supplier',[]),
    'real_model':{'status':'BLOCKED','execution':'NOT RUN','reason':'USER AUTHORIZATION REQUIRED','provider':None,'model':None,'calls':0,'time':None},
    'business_data':{'status':'BLOCKED','reason':'BUSINESS DATA REQUIRED','requirements':['DATA-01','DATA-02']},
    'business_pilot':{'status':'NOT RUN','reason':'real resources, model authorization and human business review pending'},
    'canary':{'status':'PASS','internal_authorized_view':'asserted present','forbidden_boundaries':['model request','persisted generated output','transferable preview','copy','errors','application logs','audit fields'],'final_execution_logs_scanned':logs},
    'iteration_findings':[{'issue':'expired Run accepted late result','pre_fix':'1 failed','fixed':True},{'issue':'dribbled HTTP response exceeded total deadline','pre_fix':'1 failed; 0.4857s with 0.25s limit','fixed':True},{'issue':'synthetic test used nonexistent AI tag name','pre_fix':'1 fixture assertion failed','fixed':True}],'screenshots':len(screens),'visual_review':{'layout':'PASS','state_language':'PRODUCT REVIEW REQUIRED: sidebar latest Run failure label and Plan active wording can be ambiguous','partner_text':'IMPROVEMENT RECOMMENDED; whitelist unchanged','business_signoff':'NOT RUN'},'recommendation':'CONDITIONAL GO',
    'scope':'engineering automation complete; no real provider call, approved business data or business sign-off'}
if result['backend']['FAIL'] or result['browser']['FAIL']:result['recommendation']='NO-GO'
write('validation-results.json',result)
print(json.dumps({'backend':count(backend),'browser':count(browser),'screenshots':len(screens),'matrix':matrix['summary'],'recommendation':result['recommendation']},ensure_ascii=False))
