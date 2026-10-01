"""Manage the existing private runtime and its single HTTP port-80 entrypoint."""
from pathlib import Path
import http.client
import ipaddress
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / '.isolation'
CONFIG = Path(os.environ.get('BANFEI_ENV_FILE', ROOT / '.isolation/runtime/dev/environment.json'))
STATE = RUN / 'services.json'
ENTRY_STATE = RUN / 'entry-service.json'
CADDYFILE = ROOT / 'deploy/Caddyfile'
SYSTEMD_UNITS = ('banfei-backend.service', 'banfei-frontend.service', 'banfei-http.service')


def service_manager(environment):
    manager = environment.get('BANFEI_RUNTIME_MANAGER', 'local')
    if manager not in ('local', 'systemd'):
        raise RuntimeError('BANFEI_RUNTIME_MANAGER must be local or systemd')
    return manager


def read_environment():
    if not CONFIG.is_file():
        raise RuntimeError('Existing private environment file is required; no environment or data will be recreated')
    if CONFIG.suffix == '.json':
        values = json.loads(CONFIG.read_text())
    else:
        from dotenv import dotenv_values
        values = dotenv_values(CONFIG)
    return {key: str(value) for key, value in values.items() if value is not None}


def origins(environment):
    """Canonical browser Origins; an explicit :80 is equivalent to the default port."""
    result = []
    for value in environment.get('BANFEI_IDENTITY_ORIGIN', '').split(','):
        value = value.strip()
        parsed = urlsplit(value)
        if (parsed.scheme != 'http' or not parsed.hostname or parsed.port not in (None, 80)
                or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise RuntimeError('BANFEI_IDENTITY_ORIGIN must list HTTP IP/localhost origins on port 80')
        try:
            host = ipaddress.ip_address(parsed.hostname).compressed
        except ValueError:
            if parsed.hostname != 'localhost':
                raise RuntimeError('BANFEI_IDENTITY_ORIGIN must use the actual IP or localhost') from None
            host = 'localhost'
        origin = 'http://' + ('[' + host + ']' if ':' in host else host)
        if origin not in result:
            result.append(origin)
    if not result:
        raise RuntimeError('BANFEI_IDENTITY_ORIGIN is required')
    return result


def caddy_binary(environment):
    binary = environment.get('BANFEI_CADDY_BIN') or shutil.which('caddy')
    if not binary or not Path(binary).is_file():
        raise RuntimeError('Existing Caddy 2 binary is required; configure BANFEI_CADDY_BIN')
    return str(Path(binary).resolve())


def check_ports(ports):
    for port in ports:
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(('0.0.0.0' if port == 80 else '127.0.0.1', port))
            except PermissionError:
                for table in (Path('/proc/net/tcp'), Path('/proc/net/tcp6')):
                    if table.exists() and any(row.split()[3] == '0A' and int(row.split()[1].rsplit(':', 1)[1], 16) == port for row in table.read_text().splitlines()[1:]):
                        raise RuntimeError(f'Port {port} is occupied; no service was stopped')
            except OSError as error:
                raise RuntimeError(f'Port {port} is unavailable; no service was stopped') from error


def write_private(path, content):
    fd, temporary = tempfile.mkstemp(prefix='.banfei-http-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(content)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def update_environment(updates):
    if CONFIG.suffix == '.json':
        values = json.loads(CONFIG.read_text())
        values.update(updates)
        content = json.dumps(values, ensure_ascii=False, indent=2) + '\n'
    else:
        lines = CONFIG.read_text().splitlines()
        keys = set(updates)
        lines = [line for line in lines if line.split('=', 1)[0].strip().removeprefix('export ') not in keys]
        content = '\n'.join(lines + [f'{key}={value}' for key, value in updates.items()]) + '\n'
    if CONFIG.read_text() != content:
        write_private(CONFIG, content)


def update_frontend(path, updates):
    lines = path.read_text().splitlines() if path.exists() else []
    lines = [line for line in lines if line.split('=', 1)[0].strip() not in updates]
    content = '\n'.join(lines + [f'{key}={value}' for key, value in updates.items()]) + '\n'
    if not path.exists() or path.read_text() != content:
        write_private(path, content)


def initialize():
    environment = read_environment()
    allowed = origins(environment)
    if running(STATE) or running(ENTRY_STATE):
        raise RuntimeError('Stop this project before changing its HTTP entry configuration')
    check_ports([80])
    binary = caddy_binary(environment)
    result = subprocess.run([binary, 'adapt', '--config', str(CADDYFILE), '--adapter', 'caddyfile'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError('Caddy HTTP configuration was rejected; private configuration was not changed')
    updates = {'BANFEI_IDENTITY_ORIGIN': ','.join(allowed), 'CORS_ORIGINS': ','.join(allowed),
               'NEXT_PUBLIC_API_BASE_URL': '/api', 'BANFEI_API_PROXY_TARGET': 'http://127.0.0.1:8000',
               'FORWARDED_ALLOW_IPS': '127.0.0.1'}
    update_environment(updates)
    for name in ('.env.local', '.env.production.local'):
        path = ROOT / 'frontend' / name
        if name == '.env.local' or path.exists():
            update_frontend(path, {key: updates[key] for key in ('NEXT_PUBLIC_API_BASE_URL', 'BANFEI_API_PROXY_TARGET')})
    print(f'HTTP configuration ready: {allowed[0]}; existing accounts, data and application keys preserved')


def process_start(pid):
    return (Path('/proc') / str(pid) / 'stat').read_text().split(') ')[1].split()[19]


def identity(pid):
    proc = Path('/proc') / str(pid)
    return {'cwd': str((proc / 'cwd').resolve()), 'start': process_start(pid)}


def caddy_command(environment):
    return [caddy_binary(environment), 'run', '--config', str(CADDYFILE), '--adapter', 'caddyfile']


def owned(item):
    try:
        proc = Path('/proc') / str(item['pid'])
        if item['name'] == 'caddy':
            return (proc.stat().st_uid == os.getuid()
                    and process_start(item['pid']) == item['start']
                    and (proc / 'cmdline').read_bytes().rstrip(b'\0').decode().split('\0') == item['command'])
        return identity(item['pid']) == item['identity'] and Path(item['identity']['cwd']).is_relative_to(ROOT)
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return False


def running(state):
    return state.exists() and any(owned(item) for item in json.loads(state.read_text()))


def stop_state(state):
    if not state.exists():
        return
    items = json.loads(state.read_text())
    for item in reversed(items):
        if owned(item) and os.getpgid(item['pid']) == item['pid']:
            os.killpg(item['pid'], signal.SIGTERM)
    for _ in range(50):
        if not any(owned(item) for item in items):
            state.unlink()
            return
        time.sleep(0.1)
    raise RuntimeError('Some verified project processes are still exiting; no unrelated process was signalled')


def stop():
    if service_manager(read_environment()) == 'systemd':
        require_root()
        subprocess.run(['systemctl', 'stop', *reversed(SYSTEMD_UNITS)], check=True)
        print('Stopped only the three Banfei systemd services')
        return
    stop_state(ENTRY_STATE)
    stop_state(STATE)
    print('Stopped only verified project process groups')


def start():
    environment = read_environment()
    if service_manager(environment) == 'systemd':
        require_root()
        origins(environment)
        subprocess.run(['systemctl', 'start', *SYSTEMD_UNITS], check=True)
        for _ in range(60):
            try:
                with urlopen('http://127.0.0.1/api/health', timeout=2) as response:
                    if response.status == 200:
                        print(f'HTTP ready: {origins(environment)[0]}; Banfei systemd services active')
                        return
            except OSError:
                time.sleep(0.5)
        raise RuntimeError('Banfei HTTP systemd services started but the entrypoint is not healthy')
    if running(STATE) or running(ENTRY_STATE):
        raise RuntimeError('Project services are already managed; use status')
    allowed = origins(environment)
    if environment.get('CORS_ORIGINS') != ','.join(allowed) or environment.get('NEXT_PUBLIC_API_BASE_URL') != '/api' or environment.get('BANFEI_API_PROXY_TARGET') != 'http://127.0.0.1:8000':
        raise RuntimeError('Run init before starting HTTP')
    front_env = (ROOT / 'frontend/.env.local').read_text()
    if 'NEXT_PUBLIC_API_BASE_URL=/api' not in front_env or 'BANFEI_API_PROXY_TARGET=http://127.0.0.1:8000' not in front_env:
        raise RuntimeError('Wrong isolated frontend API configuration; run init')
    check_ports([80, 3000, 8000])
    (RUN / 'logs').mkdir(parents=True, exist_ok=True)
    items = []
    try:
        for name, command, cwd in [
            ('backend', [str(ROOT / '.venv/bin/python'), str(ROOT / 'backend/scripts/isolated_server.py')], ROOT),
            ('frontend', ['npm', 'run', 'dev', '--', '-p', '3000', '-H', '127.0.0.1'], ROOT / 'frontend'),
        ]:
            with (RUN / f'logs/{name}.log').open('ab') as log:
                process = subprocess.Popen(command, cwd=cwd, env={**os.environ, **environment}, stdout=log,
                                           stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
            items.append({'name': name, 'pid': process.pid, 'identity': identity(process.pid)})
            STATE.write_text(json.dumps(items))
        for url in ('http://127.0.0.1:8000/health', 'http://127.0.0.1:3000/login'):
            for _ in range(40):
                try:
                    with urlopen(url, timeout=2) as response:
                        if response.status == 200:
                            break
                except Exception:
                    time.sleep(0.5)
            else:
                raise RuntimeError('Project application service did not become healthy')
        command = caddy_command(environment)
        with (RUN / 'logs/caddy.log').open('ab') as log:
            process = subprocess.Popen(command, cwd=ROOT, env={**os.environ, **environment}, stdout=log,
                                       stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            started = process_start(process.pid)
        except Exception:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            raise
        ENTRY_STATE.write_text(json.dumps([{'name': 'caddy', 'pid': process.pid, 'start': started, 'command': command}]))
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError('Caddy stopped; check the private Caddy log and port-80 permission')
            try:
                connection = http.client.HTTPConnection('127.0.0.1', 80, timeout=2)
                connection.request('GET', '/api/health', headers={'Host': urlsplit(allowed[0]).netloc})
                response = connection.getresponse()
                response.read()
                connection.close()
                if response.status == 200:
                    print(f'HTTP ready: {allowed[0]}; frontend 3000 and backend 8000 are loopback-only')
                    return
            except OSError:
                time.sleep(0.5)
        raise RuntimeError('HTTP entrypoint health check failed')
    except Exception:
        stop()
        raise


def require_root():
    if os.geteuid() != 0:
        raise RuntimeError('Run systemd mode with sudo; existing application services remain unchanged')


def status():
    if service_manager(read_environment()) == 'systemd':
        result = []
        for name in SYSTEMD_UNITS:
            active = subprocess.run(['systemctl', 'is-active', '--quiet', name], check=False).returncode == 0
            result.append({'name': name, 'running': active})
        print(json.dumps(result))
        return
    items = [item for state in (STATE, ENTRY_STATE) if state.exists() for item in json.loads(state.read_text())]
    print(json.dumps([{'name': item['name'], 'pid': item['pid'], 'running': owned(item)} for item in items]))


if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if action == 'init':
        initialize()
    elif action == 'start':
        start()
    elif action == 'stop':
        stop()
    elif action == 'status':
        status()
    else:
        raise SystemExit('Use init|start|stop|status')
