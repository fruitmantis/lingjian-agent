"""Lifecycle for ONLY this worktree's isolated snapshot services."""
from pathlib import Path
import json
import os
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / '.isolation'
STATE = RUN / 'services.json'

def identity(pid):
    proc = Path('/proc') / str(pid)
    return {'cwd': str((proc / 'cwd').resolve()), 'start': (proc / 'stat').read_text().split(') ')[1].split()[19]}

def owned(item):
    try:
        return identity(item['pid']) == item['identity'] and Path(item['identity']['cwd']).is_relative_to(ROOT)
    except (FileNotFoundError, ProcessLookupError):
        return False

def stop():
    if not STATE.exists():
        print('No managed isolated services'); return
    items = json.loads(STATE.read_text())
    for item in reversed(items):
        if owned(item) and os.getpgid(item['pid']) == item['pid']:
            os.killpg(item['pid'], signal.SIGTERM)
    print('Stopped only verified isolated process groups; old services untouched')

def start():
    if STATE.exists() and any(owned(i) for i in json.loads(STATE.read_text())):
        raise SystemExit('Isolated services already managed; use status')
    for port in (3100,8100):
        with socket.socket() as s:
            try: s.bind(('127.0.0.1',port))
            except OSError: raise SystemExit(f'Port {port} busy; no process stopped')
    expected='NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8100'
    if expected not in (ROOT/'frontend/.env.local').read_text():
        raise SystemExit('Wrong isolated frontend API configuration')
    (RUN/'logs').mkdir(parents=True,exist_ok=True)
    items=[]
    try:
        for name,command,cwd in [
            ('backend',[str(ROOT/'.venv/bin/python'),str(ROOT/'backend/scripts/isolated_server.py')],ROOT),
            ('frontend',['npm','run','dev','--','-p','3100','-H','127.0.0.1'],ROOT/'frontend')]:
            with (RUN/f'logs/{name}.log').open('ab') as log:
                p=subprocess.Popen(command,cwd=cwd,stdout=log,stderr=log,stdin=subprocess.DEVNULL,start_new_session=True)
            items.append({'name':name,'pid':p.pid,'identity':identity(p.pid)})
            STATE.write_text(json.dumps(items))
        for url in ('http://127.0.0.1:8100/health','http://127.0.0.1:3100/login'):
            for _ in range(40):
                try:
                    with urlopen(url,timeout=2) as response:
                        if response.status==200: break
                except Exception: time.sleep(0.5)
            else: raise RuntimeError('Isolated service did not become healthy')
        print('Isolated snapshot ready at http://127.0.0.1:3100; backend 8100; external model access blocked')
    except Exception:
        stop(); raise

if __name__ == '__main__':
    action=sys.argv[1] if len(sys.argv)>1 else 'status'
    if action=='start': start()
    elif action=='stop': stop()
    elif action=='status':
        print(json.dumps([{'name':i['name'],'pid':i['pid'],'running':owned(i)} for i in json.loads(STATE.read_text())] if STATE.exists() else []))
    else: raise SystemExit('Use start|stop|status')
