"""Run selected existing browser checks on an owned snapshot and high loopback ports.
Requires BANFEI_TEST_DATABASE_URL. Never starts/stops main services or uses runtime data.
"""
import json,os,shutil,socket,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.tests.postgres_support import empty_postgres_schema

def main():
    for port in (19080,19180,19280,19300,19800):
        with socket.socket() as s:s.bind(('127.0.0.1',port))
    modules=Path(os.environ['BANFEI_EXISTING_NODE_MODULES']).resolve()
    caddy=Path(os.environ['BANFEI_EXISTING_CADDY']).resolve()
    if not modules.is_dir() or not caddy.is_file():raise SystemExit('Existing read-only dependencies required')
    root=Path(tempfile.mkdtemp(prefix='banfei-e2e-'))
    snapshot=root/'source';snapshot.mkdir()
    for folder in ('frontend','backend','shared'):
        shutil.copytree(ROOT/folder,snapshot/folder,ignore=shutil.ignore_patterns('node_modules','.next','.env*','__pycache__','playwright-report','test-results'))
    # Change only the disposable fixture copy, never live settings.
    prepare=snapshot/'backend/tests/support/prepare_e2e.py'
    preparation=prepare.read_text().replace('    seed()',"    seed()\n    from backend.app import agent_settings\n    from backend.app.database import get_db\n    with get_db() as conn:\n        values=agent_settings.migrate(conn)\n        for agent,workflow in [('partner_match','match'),('partner_development','development')]:\n            values['agents'][agent].update(executor='runtime',runtimeUrl='http://127.0.0.1:19280/'+workflow)\n        conn.execute('UPDATE app_metadata SET value=? WHERE key=?',(json.dumps(values),agent_settings.KEY))")
    prepare.write_text(preparation)
    (snapshot/'frontend/node_modules').symlink_to(modules,target_is_directory=True)
    (snapshot/'.venv').symlink_to(Path(sys.executable).parent.parent,target_is_directory=True)
    config=snapshot/'frontend/playwright.config.ts';text=config.read_text()
    for a,b in [('18180','19180'),('8000','19800'),('3000','19300'),('http://localhost','http://127.0.0.1:19080')]:text=text.replace(a,b)
    text=text.replace('  DATABASE_URL: validationDatabase,',"  BANFEI_MATCH_EXECUTOR:'runtime', BANFEI_DEVELOPMENT_EXECUTOR:'runtime', BANFEI_RUNTIME_URL:'http://127.0.0.1:19280', BANFEI_RUNTIME_LOCAL_TEST:'1', BANFEI_RUNTIME_POLL_SECONDS:'0.1', BANFEI_RUNTIME_SHARED_KEY:'browser-synthetic-only-01234567890123456789', BANFEI_RUNTIME_MODEL_URL:'http://127.0.0.1:19180/v1', BANFEI_RUNTIME_MODEL_NAME:'validation-fake', BANFEI_MODEL_PROXY_API_KEY:'synthetic-only',\n  DATABASE_URL: validationDatabase,")
    text=text.replace('  webServer: [',"  webServer: [{command:'.venv/bin/python -B -m uvicorn backend.tests.support.runtime_gateway:app --host 127.0.0.1 --port 19280 --no-access-log',cwd:'..',url:'http://127.0.0.1:19280/health',env:validationEnvironment,reuseExistingServer:false,timeout:30000},")
    text=text.replace('../.isolation/tools/caddy run --config ../deploy/Caddyfile',str(caddy)+' run --config '+str(root/'Caddyfile'))
    config.write_text(text)
    (root/'Caddyfile').write_text('{\n admin off\n persist_config off\n auto_https off\n}\nhttp://127.0.0.1:19080 {\n bind 127.0.0.1\n reverse_proxy 127.0.0.1:19300\n}\n')
    next_config=snapshot/'frontend/next.config.mjs';next_config.write_text(next_config.read_text().replace("url.port !== '8000'","url.port !== '19800'"))
    # Only the isolated COPY adapts preexisting tests hardcoded to HTTP80.
    for f in (snapshot/'frontend/e2e').glob('*.ts'):f.write_text(f.read_text().replace('http://localhost','http://127.0.0.1:19080'))
    with empty_postgres_schema() as url:
        env=dict(os.environ,DATABASE_URL=url,PLAYWRIGHT_DATABASE_URL=url,BANFEI_TEST_ROOT=str(root),
            PLAYWRIGHT_REUSE_SERVER='0',PLAYWRIGHT_MODEL_MODE='replay',PLAYWRIGHT_HTTP_ORIGIN='http://127.0.0.1:19080',
            PYTHONPATH=str(snapshot),PYTHONDONTWRITEBYTECODE='1',XDG_CONFIG_HOME=str(root/'xdg-config'),XDG_DATA_HOME=str(root/'xdg-data'),
            ENABLEMENT_EVIDENCE_DIR=str(root/'screenshots'),AGENT_EVIDENCE_DIR=str(root/'screenshots'))
        print('BROWSER_EVIDENCE',root,flush=True)
        result=subprocess.run(['node',str(modules/'@playwright/test/cli.js'),'test',*(sys.argv[1:] or ['e2e/agent-settings.spec.ts','e2e/unified-entry.spec.ts','e2e/optional-development-partner.spec.ts']),'--config=playwright.config.ts'],cwd=snapshot/'frontend',env=env,capture_output=True,text=True)
        (root/'browser.log').write_text(result.stdout+result.stderr)
        print(result.stdout[-10000:]);print(result.stderr[-3000:]);print('EXIT',result.returncode)
        return result.returncode
if __name__=='__main__':raise SystemExit(main())
