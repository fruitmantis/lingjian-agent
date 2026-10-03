"""Explicit bounded real-provider smoke: synthetic PG data, loopback Runtime, no cloud resources."""
import argparse,json,os,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true');parser.add_argument('--runtime-environment',required=True)
    args=parser.parse_args()
    if not args.execute:raise SystemExit('Requires explicit --execute; maximum 5 provider attempts, no timeout retries')
    from cryptography.fernet import Fernet
    from urllib.parse import urlsplit
    private=json.loads(Path(args.runtime_environment).read_text())
    os.environ['DATABASE_URL']=private['DATABASE_URL']
    from backend.app.model_resolver import resolve_model_record,model_config_from_record
    models={}
    for workflow,scene in [('match','partner_match'),('development','partner_development')]:
        record=resolve_model_record(scene,read_only=True)
        if record.get('api_key_source')=='env' and record.get('api_key_env_name'):
            name=record['api_key_env_name'];os.environ[name]=private.get(name,'')
        selected=model_config_from_record(record)
        if urlsplit(selected.base_url).hostname!='api.deepseek.com' or selected.model!='deepseek-v4-flash' or not selected.api_key:raise SystemExit('Approved provider configuration unavailable')
        models[workflow]=selected
    root=Path(tempfile.mkdtemp(prefix='banfei-agentarts-real-'));print('REAL_MODEL_EVIDENCE',root,flush=True)
    os.environ.update(JWT_SECRET_KEY='synthetic-runtime-smoke-012345678901234567890123456789',BANFEI_IDENTITY_ENCRYPTION_KEY=Fernet.generate_key().decode(),
      BANFEI_IDENTITY_ORIGIN='http://localhost',BANFEI_ERROR_LOG_PATH=str(root/'errors.jsonl'),LINGJIAN_UPLOADS_DIR=str(root/'uploads'),
      BANFEI_RUNTIME_LOCAL_TEST='1',BANFEI_RUNTIME_POLL_SECONDS='.25',BANFEI_MATCH_EXECUTOR='runtime',BANFEI_DEVELOPMENT_EXECUTOR='runtime')
    from backend.tests.postgres_support import empty_postgres_schema
    from backend.app.postgres_storage import initialize_empty_schema
    from backend.tests.support.seed_validation_db import seed
    from backend.app.database import get_db
    from backend.app.model_timeout_settings import save,TimeoutSettings
    from backend.app.routers import match
    from backend.app import development_lifecycle as life,development_engine as engine,development_views as views
    from backend.app.development_types import Submit,DevelopmentRequest
    import httpx
    results=[];started=time.monotonic()
    try:
        with empty_postgres_schema() as url:
            os.environ['DATABASE_URL']=url;initialize_empty_schema(url);seed()
            save(TimeoutSettings(timeoutSeconds=300.,timeoutRetries=0))
            with get_db() as conn:user=dict(conn.execute("SELECT * FROM users WHERE username='user_a'").fetchone())
            for workflow in ['match','development']:
                selected=models[workflow]
                with get_db() as conn:
                    mid=conn.execute('SELECT id FROM model_configs ORDER BY id LIMIT 1').fetchone()[0]
                    conn.execute('UPDATE model_configs SET enabled=0,is_default=0')
                    conn.execute("UPDATE model_configs SET enabled=1,is_default=1,base_url=?,model_name=?,api_key='runtime-managed-placeholder',api_key_source='db',temperature=?,top_p=?,max_tokens=? WHERE id=?",(selected.base_url,selected.model,selected.temperature,selected.top_p,selected.max_tokens,mid))
                    conn.execute('UPDATE model_usage_configs SET model_config_id=?',(mid,))
                key=uuid.uuid4().hex+uuid.uuid4().hex
                with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
                os.environ['BANFEI_RUNTIME_URL']=f'http://127.0.0.1:{port}';os.environ['BANFEI_RUNTIME_SHARED_KEY']=key
                child_env={k:v for k,v in os.environ.items() if k in ('PATH','LANG','LC_ALL')}
                child_env.update(PYTHONPATH=str(ROOT),PYTHONDONTWRITEBYTECODE='1',BANFEI_RUNTIME_LOCAL_TEST='1',BANFEI_RUNTIME_SHARED_KEY=key,
                    BANFEI_RUNTIME_MODEL_URL=selected.base_url,BANFEI_RUNTIME_MODEL_NAME=selected.model,BANFEI_RUNTIME_MODEL_KEY=selected.api_key)
                logfile=root/(workflow+'-runtime.log')
                with logfile.open('w') as log:
                    child=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.agent_runtime.server:app','--host','127.0.0.1','--port',str(port),'--workers','1','--no-access-log'],cwd=ROOT,env=child_env,stdout=log,stderr=log)
                    try:
                        for _ in range(100):
                            if child.poll() is not None:raise RuntimeError('Runtime failed to start')
                            try:
                                if httpx.get(f'http://127.0.0.1:{port}/ping',trust_env=False,timeout=1).status_code==200:break
                            except httpx.ConnectError:pass
                            time.sleep(.05)
                        else:raise RuntimeError('Runtime readiness timed out')
                        print('RUNNING_SYNTHETIC',workflow,flush=True)
                        if workflow=='match':
                            outcome=match.match_partners(match.MatchRequest(requirement='合成验证项目：寻找制造行业知识库与数据治理伙伴，需核实已有案例及交付边界，不涉及真实客户。'),user)
                            if outcome.taskStatus not in ('ready','partial'):raise RuntimeError('Matching did not persist a result')
                            item={'workflow':workflow,'task_id':outcome.recordId,'status':outcome.taskStatus,'recommendations':len(outcome.recommendations)}
                        else:
                            accepted=life.create(Submit(submission_id=str(uuid.uuid4()),request=DevelopmentRequest(development_direction='合成验证：已有基本上云迁移经验，希望发展数据库迁移与回退验证能力，请给出现有课程或实验建议。未关联真实伙伴。')),user)
                            engine.execute(accepted['run_id']);detail=views.detail(accepted['plan_id'],user)
                            if not detail['payload'] or detail['runs'][0]['status']!='ready':raise RuntimeError('Development did not persist a valid version')
                            item={'workflow':workflow,'task_id':accepted['plan_id'],'run_id':accepted['run_id'],'status':'ready','versions':len(detail['versions']),'partner':detail['plan']['target_partner_id']}
                        with get_db() as conn:
                            item['runtime_stages']=[json.loads(r[0]) for r in conn.execute("SELECT value FROM app_metadata WHERE key LIKE 'runtime_stage:%'") if json.loads(r[0])['task_id']==item['task_id']]
                        results.append(item);print('PASSED_SYNTHETIC',workflow,flush=True)
                    finally:
                        child.terminate()
                        try:child.wait(timeout=5)
                        except subprocess.TimeoutExpired:child.kill();child.wait()
                attempts=sum((root/(w+'-runtime.log')).read_text().count('RUNTIME_MODEL_ATTEMPT') for w in ['match','development'] if (root/(w+'-runtime.log')).exists())
                if attempts>5:raise RuntimeError('Provider attempt ceiling exceeded')
    except Exception as error:
        (root/'result.json').write_text(json.dumps({'status':'failed','error_type':type(error).__name__,'results':results,'elapsed_seconds':round(time.monotonic()-started,3)},ensure_ascii=False,indent=2))
        print('FAILED',type(error).__name__,'see redacted evidence',flush=True);return 1
    (root/'result.json').write_text(json.dumps({'status':'passed','results':results,'provider_attempts':attempts,'elapsed_seconds':round(time.monotonic()-started,3),'temporary_services_stopped':True,'data':'synthetic only; dedicated PG schema removed'},ensure_ascii=False,indent=2))
    print('REAL_MODEL_PASSED',attempts,'attempts',flush=True);return 0
if __name__=='__main__':raise SystemExit(main())
