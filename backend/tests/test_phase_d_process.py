"""Owned 8000 process crash/restart and real HTTP latency; synthetic /tmp only."""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from datetime import datetime,timedelta,timezone
from pathlib import Path
import jwt
from backend.tests.test_process_recovery import PROJECT_ROOT, PROCESS_SECRET, free_port, wait_health, stop_process, request_json


def test_development_kill_restart_retry_and_http_creation(tmp_path,record_property):
    # Fail if occupied. Never discover or terminate somebody else's listener.
    with socket.socket() as sock:sock.bind(('127.0.0.1',8000))
    fake_port=free_port();db=tmp_path/'development.db'
    env={**os.environ,'LINGJIAN_DATABASE_PATH':str(db),'LINGJIAN_UPLOADS_DIR':str(tmp_path/'uploads'),
         'LINGJIAN_CHROMA_DIR':str(tmp_path/'chroma'),'JWT_SECRET_KEY':PROCESS_SECRET,
         'BOOTSTRAP_ADMIN_USERNAME':'unused_bootstrap','BOOTSTRAP_ADMIN_PASSWORD':'UnusedBootstrap123',
         'VALIDATION_FAKE_LLM_BASE_URL':f'http://127.0.0.1:{fake_port}/v1'}
    env.pop('LINGJIAN_ALLOW_REAL_DEVELOPMENT_MODEL',None)
    for key in ['DEVELOPMENT_MODEL_TIMEOUT_SECONDS','DEVELOPMENT_RUN_TIMEOUT_SECONDS']:env.pop(key,None)
    fake=backend=restarted=None
    with (tmp_path/'mock.log').open('w') as fl,(tmp_path/'backend.log').open('w') as bl:
        try:
            subprocess.run([sys.executable,'-m','backend.tests.support.seed_validation_db'],cwd=PROJECT_ROOT,env=env,check=True,capture_output=True)
            with sqlite3.connect(db) as conn:
                tag=conn.execute('SELECT id FROM capability_tags WHERE enabled=1 LIMIT 1').fetchone()[0]
                config=conn.execute('SELECT id FROM model_configs LIMIT 1').fetchone()[0]
                conn.execute("UPDATE model_usage_configs SET model_config_id=? WHERE scene_key='partner_development'",(config,))
            fake=subprocess.Popen([sys.executable,'-m','uvicorn','backend.tests.support.fake_llm_server:app','--host','127.0.0.1','--port',str(fake_port)],cwd=PROJECT_ROOT,env=env,stdout=fl,stderr=subprocess.STDOUT)
            wait_health(f'http://127.0.0.1:{fake_port}/health',fake)
            def launch():return subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--app-dir','backend','--host','127.0.0.1','--port','8000'],cwd=PROJECT_ROOT,env=env,stdout=bl,stderr=subprocess.STDOUT)
            backend=launch();base='http://127.0.0.1:8000';wait_health(base+'/health',backend)
            token=jwt.encode({'sub':'user-a-id','username':'user_a','role':'user','ver':0,'iat':datetime.now(timezone.utc),'exp':datetime.now(timezone.utc)+timedelta(hours=1)},PROCESS_SECRET,algorithm='HS256')
            request={'target_partner_id':'partner-1','raw_demand':'合成可靠性验证','development_goal':'数据库交付',
                'trainee_role':'工程师','trainee_count':3,'known_baseline':'入门','duration_weeks':4,'hours_per_week':3,
                'constraints':dict.fromkeys(['language','site','account','network','environment','cost','budget'],'无要求'),
                'model_input_allowed':True,'partner_goal_allowed':True,'targets':[{'capability_tag_id':tag,'requirement':'独立交付'}]}
            def post(path,body):return request_json(base+path,token=token,payload=body)
            def run_status(run_id):
                with sqlite3.connect(db) as conn:return conn.execute('SELECT status FROM development_runs WHERE id=?',(run_id,)).fetchone()[0]
            def wait_status(run_id,expected):
                end=time.monotonic()+15
                while time.monotonic()<end:
                    if run_status(run_id)==expected:return
                    time.sleep(.025)
                raise AssertionError(f'Run did not reach {expected}')
            code,first=post('/development/plans',{'submission_id':'process-first-plan','request':request});assert code==202
            pid=first['plan_id'];wait_status(first['run_id'],'ready')
            with sqlite3.connect(db) as conn:v1=conn.execute('SELECT current_version_id FROM development_plans WHERE id=?',(pid,)).fetchone()[0]
            assert post(f'/development/plans/{pid}/confirm',{'version_id':v1})[0]==204
            code,second=post(f'/development/plans/{pid}/revise',{'submission_id':'process-crash-revise','based_on_version_id':v1,'instruction':'调整','request':{**request,'development_goal':'C_SLOW 合成数据库交付'}})
            assert code==202;wait_status(second['run_id'],'running')
            assert Path(f'/proc/{backend.pid}/cwd').resolve()==PROJECT_ROOT
            assert '--port\x008000' in Path(f'/proc/{backend.pid}/cmdline').read_text()
            backend.kill();backend.wait(timeout=5)
            started=time.monotonic();restarted=launch();wait_health(base+'/health',restarted);wait_status(second['run_id'],'interrupted')
            recovered_seconds=time.monotonic()-started;assert recovered_seconds<60
            with sqlite3.connect(db) as conn:
                assert conn.execute('SELECT current_version_id,confirmed_version_id FROM development_plans WHERE id=?',(pid,)).fetchone()==(v1,v1)
                assert conn.execute('SELECT count(*) FROM development_versions WHERE plan_id=?',(pid,)).fetchone()[0]==1
            _,retry=post(f'/development/plans/{pid}/revise',{'submission_id':'process-retry-revise','based_on_version_id':v1,'instruction':'重试','request':request})
            wait_status(retry['run_id'],'ready')
            with sqlite3.connect(db) as conn:
                current,confirmed=conn.execute('SELECT current_version_id,confirmed_version_id FROM development_plans WHERE id=?',(pid,)).fetchone()
                assert current!=v1 and confirmed==v1
                assert conn.execute('SELECT count(*) FROM development_versions WHERE plan_id=?',(pid,)).fetchone()[0]==2
            elapsed=[];runs=[]
            for index in range(50):
                started=time.perf_counter()
                code,created=post('/development/plans',{'submission_id':f'process-latency-{index:03d}','request':{**request,'development_goal':'C_SLOW 延迟验证'}})
                elapsed.append(time.perf_counter()-started);assert code==202;runs.append(created['run_id'])
                assert run_status(created['run_id']) in ('pending','running')
            ordered=sorted(elapsed);assert ordered[47]<=1
            record_property('http_creation',json.dumps({'sample_count':50,'p50_seconds':ordered[24],'p95_seconds':ordered[47],
                'max_seconds':max(elapsed),'scope':'HTTP loopback 8000 + bearer validation + SQLite commit + executor enqueue; excludes model completion/browser/source site',
                'slow_model_seconds_per_call':3,'real_model_calls':0}))
            record_property('kill_restart',json.dumps({'port':8000,'recovery_seconds':recovered_seconds,'status':'interrupted','retry':'ready','versions':2,'confirmed_preserved':True}))
        finally:
            stop_process(restarted);stop_process(backend);stop_process(fake)
    assert 'INTERNAL_SECRET_PHASE_B_DO_NOT_SHARE' not in (tmp_path/'backend.log').read_text()
