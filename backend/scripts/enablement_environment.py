"""Lifecycle for this main workspace and its optional Caddy HTTPS entrypoint."""
from pathlib import Path
import json
import os
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import https_runtime as https

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / '.isolation'
STATE = RUN / 'services.json'
HTTPS_STATE = RUN / 'https-service.json'

def identity(pid):
    proc = Path('/proc') / str(pid)
    return {'cwd': str((proc / 'cwd').resolve()), 'start': (proc / 'stat').read_text().split(') ')[1].split()[19]}

def owned(item):
    try:
        if item['name'] == 'caddy':
            # A file-capability process hides /proc/<pid>/cwd from its own UID.
            # Match its start time, owner and exact project config command instead.
            proc = Path('/proc') / str(item['pid'])
            expected = item.get('command') or caddy_command(https.read_environment())
            started = item.get('start') or item['identity']['start']
            return (proc.stat().st_uid == os.getuid()
                    and (proc/'stat').read_text().split(') ')[1].split()[19] == started
                    and (proc/'cmdline').read_bytes().rstrip(b'\0').decode().split('\0') == expected)
        return identity(item['pid']) == item['identity'] and Path(item['identity']['cwd']).is_relative_to(ROOT)
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return False

def stop(state=STATE):
    if state == STATE:
        stop(HTTPS_STATE)
    if not state.exists():
        print('No managed isolated services'); return
    items = json.loads(state.read_text())
    for item in reversed(items):
        if owned(item) and os.getpgid(item['pid']) == item['pid']:
            os.killpg(item['pid'], signal.SIGTERM)
    for _ in range(50):
        if not any(owned(item) for item in items):
            print('Stopped only verified isolated process groups; old services untouched')
            return
        time.sleep(0.1)
    raise SystemExit('Some isolated processes are still exiting; no unrelated process was signalled')

def https_running():
    return HTTPS_STATE.exists() and any(owned(i) for i in json.loads(HTTPS_STATE.read_text()))

def caddy_command(environment):
    return [https.caddy_binary(environment), 'run', '--config', str(https.CADDYFILE), '--adapter', 'caddyfile']

def start_https():
    if https_running():
        print('This project HTTPS entrypoint is already running'); return
    environment = https.read_environment()
    origin, bind = https.origin_settings(environment)
    if environment.get('BANFEI_IDENTITY_ORIGIN') != origin or environment.get('NEXT_PUBLIC_API_BASE_URL') != '/api' or not https.CADDYFILE.is_file():
        raise RuntimeError('Run init-https before starting HTTPS')
    https.check_ports(bind, [443] + ([80] if environment.get('BANFEI_HTTPS_REDIRECT') == '1' else []))
    (RUN/'logs').mkdir(parents=True, exist_ok=True)
    with (RUN/'logs/caddy.log').open('ab') as log:
        command = caddy_command(environment)
        process = subprocess.Popen(command,
            cwd=ROOT, env=https.caddy_environment(environment), stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
    started = (Path('/proc')/str(process.pid)/'stat').read_text().split(') ')[1].split()[19]
    HTTPS_STATE.write_text(json.dumps([{'name':'caddy','pid':process.pid,'start':started,'command':command}]))
    try:
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError('Caddy stopped; check .isolation/logs/caddy.log and low-port bind permission')
            try:
                if https.healthy(environment):
                    print(f'HTTPS ready: {origin}; CA export: {https.ROOT_CERT}'); return
            except (OSError, ValueError):
                time.sleep(0.5)
        raise RuntimeError('HTTPS health check failed with certificate verification enabled')
    except Exception:
        stop(HTTPS_STATE); raise

def start():
    if STATE.exists() and any(owned(i) for i in json.loads(STATE.read_text())):
        raise SystemExit('Isolated services already managed; use status')
    for port in (3000,8000):
        with socket.socket() as s:
            # A stopped HTTP service can leave TIME_WAIT sockets; still reject live listeners.
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try: s.bind(('127.0.0.1',port))
            except OSError: raise SystemExit(f'Port {port} busy; no process stopped')
    environment = dict(os.environ)
    environment.update(https.read_environment())
    secured = bool(environment.get('BANFEI_HTTPS_ORIGIN'))
    if secured and not https_running():
        _, bind = https.origin_settings(environment)
        https.check_ports(bind, [443] + ([80] if environment.get('BANFEI_HTTPS_REDIRECT') == '1' else []))
    expected='NEXT_PUBLIC_API_BASE_URL=' + ('/api' if secured else 'http://localhost:8000')
    if expected not in (ROOT/'frontend/.env.local').read_text():
        raise SystemExit('Wrong isolated frontend API configuration')
    # Preserve the existing manual-test configuration when restarting this main.
    # This file is private runtime configuration, never a new database or seed.
    (RUN/'logs').mkdir(parents=True,exist_ok=True)
    items=[]
    try:
        for name,command,cwd in [
            ('backend',[str(ROOT/'.venv/bin/python'),str(ROOT/'backend/scripts/isolated_server.py')],ROOT),
            ('frontend',['npm','run','dev','--','-p','3000','-H','127.0.0.1'],ROOT/'frontend')]:
            with (RUN/f'logs/{name}.log').open('ab') as log:
                p=subprocess.Popen(command,cwd=cwd,env=environment,stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
            items.append({'name':name,'pid':p.pid,'identity':identity(p.pid)})
            STATE.write_text(json.dumps(items))
        for url in ('http://127.0.0.1:8000/health','http://127.0.0.1:3000/login'):
            for _ in range(40):
                try:
                    with urlopen(url,timeout=2) as response:
                        if response.status==200: break
                except Exception: time.sleep(0.5)
            else: raise RuntimeError('Isolated service did not become healthy')
        if secured:
            start_https()
        print('Current main ready; frontend 3000 and backend 8000; only enabled model endpoints allowed')
    except Exception:
        stop(); raise

if __name__ == '__main__':
    action=sys.argv[1] if len(sys.argv)>1 else 'status'
    if action=='start': start()
    elif action=='stop': stop()
    elif action=='init-https': https.initialize(caddy_running=https_running())
    elif action=='https-start': start_https()
    elif action=='https-stop': stop(HTTPS_STATE)
    elif action=='status':
        items = [i for path in (STATE, HTTPS_STATE) if path.exists() for i in json.loads(path.read_text())]
        print(json.dumps([{'name':i['name'],'pid':i['pid'],'running':owned(i)} for i in items]))
    else: raise SystemExit('Use init-https|start|stop|status|https-start|https-stop')
