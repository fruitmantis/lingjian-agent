"""Local main launcher preserves existing data configuration and owns its ports."""
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
    (tmp_path / 'frontend').mkdir()
    (tmp_path / 'frontend/.env.local').write_text('NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000\n')
    return module


def test_main_launcher_uses_existing_private_configuration(tmp_path, monkeypatch):
    module = launcher(tmp_path, monkeypatch)
    private = tmp_path / '.isolation/runtime/dev'
    private.mkdir(parents=True)
    database = private / 'app.db'
    database.write_bytes(b'existing synthetic file; launcher must not open or initialize it')
    before = database.read_bytes()
    config = {'LINGJIAN_DATABASE_PATH': str(database),
              'CORS_ORIGINS': 'http://127.0.0.1:3000',
              'NEXT_PUBLIC_API_BASE_URL': 'http://127.0.0.1:8000'}
    (private / 'environment.json').write_text(json.dumps(config))
    monkeypatch.delenv('LINGJIAN_DATABASE_PATH', raising=False)
    binds = []
    class Socket:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def bind(self, address): binds.append(address)
    monkeypatch.setattr(module.socket, 'socket', Socket)
    launches = []
    def spawn(command, **kwargs):
        launches.append((command, kwargs))
        return SimpleNamespace(pid=100 + len(launches))
    monkeypatch.setattr(module.subprocess, 'Popen', spawn)
    monkeypatch.setattr(module, 'identity', lambda _: {'cwd': str(tmp_path), 'start': 'synthetic'})
    urls = []
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *_): pass
    def health(url, **_):
        urls.append(url)
        return Response()
    monkeypatch.setattr(module, 'urlopen', health)
    module.start()
    assert binds == [('127.0.0.1', 3000), ('127.0.0.1', 8000)]
    assert len(launches) == 2
    assert launches[1][0] == ['npm', 'run', 'dev', '--', '-p', '3000', '-H', '127.0.0.1']
    assert all(all(kwargs['env'][k] == v for k, v in config.items()) for _, kwargs in launches)
    assert urls == ['http://127.0.0.1:8000/health', 'http://127.0.0.1:3000/login']
    assert database.read_bytes() == before


def test_busy_main_port_does_not_launch_or_stop_any_process(tmp_path, monkeypatch):
    module = launcher(tmp_path, monkeypatch)
    class BusySocket:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def bind(self, address): raise OSError('occupied')
    monkeypatch.setattr(module.socket, 'socket', BusySocket)
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('must not spawn'))
    monkeypatch.setattr(module, 'stop', lambda: pytest.fail('must not stop another listener'))
    with pytest.raises(SystemExit, match='Port 3000 busy; no process stopped'):
        module.start()
