"""Caddy entrypoint configuration; never initialize accounts, databases or application keys."""
from datetime import datetime, timezone
from pathlib import Path
import ipaddress
import http.client
import json
import os
import shutil
import socket
import ssl
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(os.environ.get('BANFEI_ENV_FILE', ROOT / '.isolation/runtime/dev/environment.json'))
HTTPS = ROOT / '.isolation/runtime/caddy'
CADDYFILE = HTTPS / 'Caddyfile'
ROOT_CERT = HTTPS / 'root.crt'


def read_environment():
    if not CONFIG.is_file():
        raise RuntimeError('Existing private environment file is required; no environment or data will be recreated')
    if CONFIG.suffix == '.json':
        values = json.loads(CONFIG.read_text())
    else:
        from dotenv import dotenv_values
        values = dotenv_values(CONFIG)
    return {key: str(value) for key, value in values.items() if value is not None}


def origin_settings(environment):
    origin = environment.get('BANFEI_HTTPS_ORIGIN', '').rstrip('/')
    parsed = urlsplit(origin)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or parsed.port not in (None, 443):
        raise RuntimeError('BANFEI_HTTPS_ORIGIN must be https://localhost or https://<IP>, on port 443')
    if any(char.isspace() for char in origin):
        raise RuntimeError('Invalid HTTPS origin')
    host = parsed.hostname if parsed.hostname == 'localhost' else ipaddress.ip_address(parsed.hostname).compressed
    bind = '127.0.0.1' if host == 'localhost' else ('::' if ':' in host else '0.0.0.0')
    # Match the browser's serialized Origin (lowercase host, no default :443).
    return 'https://' + ('[' + host + ']' if ':' in host else host), bind


def check_ports(bind, ports):
    for port in ports:
        with socket.socket(socket.AF_INET6 if ':' in bind else socket.AF_INET) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((bind, port))
            except PermissionError:
                # Check all listeners, including non-loopback/IPv6, without sudo.
                for table in (Path('/proc/net/tcp'), Path('/proc/net/tcp6')):
                    if table.exists() and any(row.split()[3] == '0A' and int(row.split()[1].rsplit(':', 1)[1], 16) == port for row in table.read_text().splitlines()[1:]):
                        raise RuntimeError(f'Port {port} is occupied; no service was stopped')
            except OSError as error:
                raise RuntimeError(f'Port {port} is unavailable; no service was stopped') from error


def caddy_environment(environment):
    origin, bind = origin_settings(environment)
    return {**os.environ, **environment, 'BANFEI_HTTPS_ORIGIN': origin,
            'BANFEI_HTTPS_HOST': urlsplit(origin).hostname, 'BANFEI_HTTPS_BIND': bind,
            'XDG_DATA_HOME': str(HTTPS / 'data'), 'XDG_CONFIG_HOME': str(HTTPS / 'config')}


def caddy_binary(environment):
    binary = environment.get('BANFEI_CADDY_BIN') or shutil.which('caddy')
    if not binary or not Path(binary).is_file():
        raise RuntimeError('Install Caddy 2 first, then configure BANFEI_CADDY_BIN with its absolute path')
    return str(Path(binary).resolve())


def write_environment(updates):
    if CONFIG.suffix == '.json':
        values = json.loads(CONFIG.read_text())
        values.update(updates)
        CONFIG.write_text(json.dumps(values, ensure_ascii=False, indent=2) + '\n')
    else:
        patch_env_file(CONFIG, updates)
    CONFIG.chmod(0o600)


def patch_env_file(path, updates):
    lines = path.read_text().splitlines() if path.exists() else []
    keys = set(updates)
    lines = [line for line in lines if line.split('=', 1)[0].strip().removeprefix('export ') not in keys]
    path.write_text('\n'.join(lines + [f'{key}={value}' for key, value in updates.items()]) + '\n')
    path.chmod(0o600)


def initialize(*, caddy_running=False):
    environment = read_environment()
    origin, bind = origin_settings(environment)
    redirect = environment.get('BANFEI_HTTPS_REDIRECT', '0')
    if redirect not in ('0', '1'):
        raise RuntimeError('BANFEI_HTTPS_REDIRECT must be 0 or 1')
    binary = caddy_binary(environment)
    if caddy_running:
        previous = HTTPS / 'settings.json'
        if not previous.exists() or json.loads(previous.read_text()) != {'origin': origin, 'redirect': redirect}:
            raise RuntimeError('Stop this project HTTPS entrypoint before changing its address or redirect setting')
    else:
        check_ports(bind, [443] + ([80] if redirect == '1' else []))
    updates = {'BANFEI_HTTPS_ORIGIN': origin, 'BANFEI_IDENTITY_ORIGIN': origin, 'CORS_ORIGINS': origin,
               'NEXT_PUBLIC_API_BASE_URL': '/api', 'BANFEI_API_PROXY_TARGET': 'http://127.0.0.1:8000',
               'FORWARDED_ALLOW_IPS': '127.0.0.1'}
    environment.update(updates)
    HTTPS.mkdir(parents=True, exist_ok=True, mode=0o700)
    HTTPS.chmod(0o700)
    # Configuration snapshots contain existing application secrets: private, never logged.
    if any(read_environment().get(key) != value for key, value in updates.items()):
        backup = HTTPS / ('config-before-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        backup.mkdir(mode=0o700)
        shutil.copy2(CONFIG, backup / CONFIG.name)
        (backup / CONFIG.name).chmod(0o600)
        for name in ('.env.local', '.env.production.local'):
            path = ROOT / 'frontend' / name
            if path.exists():
                shutil.copy2(path, backup / name)
                (backup / name).chmod(0o600)
    template = (ROOT / 'deploy/Caddyfile').read_text()
    if redirect == '1':
        host = urlsplit(origin).hostname
        if ':' in host:
            host = '[' + host + ']'
        template += '\nhttp://' + host + ' {\n\tbind {$BANFEI_HTTPS_BIND}\n\tredir {$BANFEI_HTTPS_ORIGIN}{uri} 308\n}\n'
    # Adapt validates syntax without issuing certificates or installing trust roots.
    candidate = HTTPS / 'Caddyfile.pending'
    candidate.write_text(template)
    result = subprocess.run([binary, 'adapt', '--config', str(candidate), '--adapter', 'caddyfile'],
                            env=caddy_environment(environment), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError('Caddy configuration was rejected; existing runtime configuration was not changed')
    candidate.replace(CADDYFILE)
    write_environment(updates)
    for name in ('.env.local', '.env.production.local'):
        path = ROOT / 'frontend' / name
        if name == '.env.local' or path.exists():
            patch_env_file(path, {key: updates[key] for key in ('NEXT_PUBLIC_API_BASE_URL', 'BANFEI_API_PROXY_TARGET')})
    (HTTPS / 'settings.json').write_text(json.dumps({'origin': origin, 'redirect': redirect}))
    print(f'HTTPS configuration ready: {origin}; existing accounts, data and application keys preserved')
    print('Save your existing identity Key before switching. Restart the application services with this configuration.')
    print(f'After first HTTPS start, export only this public CA certificate: {ROOT_CERT}')
    print('Clients must explicitly trust this root certificate; Caddy does not install client trust automatically.')


def export_root():
    source = HTTPS / 'data/caddy/pki/authorities/local/root.crt'
    if source.is_file():
        shutil.copyfile(source, ROOT_CERT)
        ROOT_CERT.chmod(0o644)
    return ROOT_CERT


def tls_context():
    return ssl.create_default_context(cafile=str(export_root()))


def healthy(environment):
    """Verify the configured hostname/IP certificate locally, including NAT hosts."""
    origin, bind = origin_settings(environment)
    parsed = urlsplit(origin)
    context = tls_context()
    connection = http.client.HTTPSConnection(parsed.hostname, 443, context=context, timeout=2)
    try:
        raw = socket.create_connection(('::1' if bind == '::' else '127.0.0.1', 443), timeout=2)
        connection.sock = context.wrap_socket(raw, server_hostname=parsed.hostname)
        connection.request('GET', '/api/health', headers={'Host': parsed.netloc})
        response = connection.getresponse()
        response.read()
        return response.status == 200
    finally:
        connection.close()
