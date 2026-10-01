"""HTTP port-80 launcher preserves existing data and owns only its three services."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def launcher(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'scripts/enablement_environment.py'
    spec = importlib.util.spec_from_file_location('local_baseline_launcher', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'RUN', tmp_path / '.isolation')
    monkeypatch.setattr(module, 'STATE', tmp_path / '.isolation/services.json')
    monkeypatch.setattr(module, 'ENTRY_STATE', tmp_path / '.isolation/entry-service.json')
    monkeypatch.setattr(module, 'CONFIG', tmp_path / '.isolation/runtime/dev/environment.json')
    (tmp_path / 'frontend').mkdir()
    (tmp_path / 'frontend/.env.local').write_text(
        'NEXT_PUBLIC_API_BASE_URL=/api\nBANFEI_API_PROXY_TARGET=http://127.0.0.1:8000\n')
    return module


def test_main_launcher_uses_existing_private_configuration(tmp_path, monkeypatch):
    module = launcher(tmp_path, monkeypatch)
    private = tmp_path / '.isolation/runtime/dev'
    private.mkdir(parents=True)
    database = private / 'existing-material.txt'
    database.write_bytes(b'existing synthetic file; launcher must not open or initialize it')
    before = database.read_bytes()
    config = {'DATABASE_URL': __import__('os').environ['DATABASE_URL'],
              'BANFEI_IDENTITY_ORIGIN': 'http://203.0.113.10,http://localhost',
              'CORS_ORIGINS': 'http://203.0.113.10,http://localhost',
              'NEXT_PUBLIC_API_BASE_URL': '/api',
              'BANFEI_API_PROXY_TARGET': 'http://127.0.0.1:8000'}
    (private / 'environment.json').write_text(json.dumps(config))
    # The launcher passes the existing PostgreSQL configuration through unchanged.
    ports = []
    monkeypatch.setattr(module, 'check_ports', lambda values: ports.extend(values))
    monkeypatch.setattr(module, 'caddy_command', lambda _: ['/installed/caddy', 'run', '--config', 'deploy/Caddyfile'])
    launches = []
    def spawn(command, **kwargs):
        launches.append((command, kwargs))
        return SimpleNamespace(pid=100 + len(launches), poll=lambda: None)
    monkeypatch.setattr(module.subprocess, 'Popen', spawn)
    monkeypatch.setattr(module, 'identity', lambda _: {'cwd': str(tmp_path), 'start': 'synthetic'})
    monkeypatch.setattr(module, 'process_start', lambda _: 'synthetic')
    urls = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return b'healthy'
    def health(url, **_):
        urls.append(url)
        return Response()
    monkeypatch.setattr(module, 'urlopen', health)
    class Connection:
        def __init__(self, host, port, timeout):
            assert (host, port) == ('127.0.0.1', 80)
        def request(self, method, path, headers):
            assert (method, path, headers['Host']) == ('GET', '/api/health', '203.0.113.10')
        def getresponse(self): return Response()
        def close(self): pass
    monkeypatch.setattr(module.http.client, 'HTTPConnection', Connection)
    module.start()
    assert ports == [80, 3000, 8000]
    assert len(launches) == 3
    assert launches[1][0] == ['npm', 'run', 'dev', '--', '-p', '3000', '-H', '127.0.0.1']
    assert launches[2][0][0] == '/installed/caddy'
    assert all(all(kwargs['env'][k] == v for k, v in config.items()) for _, kwargs in launches)
    assert urls == ['http://127.0.0.1:8000/health', 'http://127.0.0.1:3000/login']
    assert database.read_bytes() == before


def test_busy_main_port_does_not_launch_or_stop_any_process(tmp_path, monkeypatch):
    module = launcher(tmp_path, monkeypatch)
    private = tmp_path / '.isolation/runtime/dev'
    private.mkdir(parents=True)
    (private / 'environment.json').write_text(json.dumps({
        'BANFEI_IDENTITY_ORIGIN': 'http://203.0.113.10', 'CORS_ORIGINS': 'http://203.0.113.10',
        'NEXT_PUBLIC_API_BASE_URL': '/api', 'BANFEI_API_PROXY_TARGET': 'http://127.0.0.1:8000'}))
    def busy(_): raise RuntimeError('Port 80 is unavailable; no service was stopped')
    monkeypatch.setattr(module, 'check_ports', busy)
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('must not spawn'))
    monkeypatch.setattr(module, 'stop', lambda: pytest.fail('must not stop another listener'))
    with pytest.raises(RuntimeError, match='Port 80 is unavailable; no service was stopped'):
        module.start()
