"""Offline ASGI authentication checks; no DB, cloud requests or real credentials."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch, Mock
from urllib.error import HTTPError
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from backend.agent_runtime import server

spec = importlib.util.spec_from_file_location('verify_runtime_v2', ROOT / 'deploy/agentarts/verify_runtime_v2.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
KEY = 'synthetic-shared-key-auth-diagnostic-only'
PLATFORM = 'synthetic-platform-key-auth-diagnostic-only'
URL = 'https://synthetic.huaweicloud-agentarts.com/runtimes/matching/invocations'


class AuthDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.socket.connect', 'backend.agent_runtime.provider.completion'):
            guard = patch(target, side_effect=AssertionError('Network/model call forbidden'))
            guard.start()
            self.addCleanup(guard.stop)

    def test_all_401_branches_and_cli_reason_visibility(self):
        cases = [(None, KEY, 'runtime_shared_key_unconfigured'),
                 ('', KEY, 'runtime_shared_key_unconfigured'),
                 ('short-synthetic', KEY, 'runtime_shared_key_too_short'),
                 (KEY, None, 'runtime_key_header_missing'),
                 (KEY, '', 'runtime_key_mismatch'),
                 (KEY, KEY + '-wrong', 'runtime_key_mismatch'),
                 (KEY + ' ', KEY, 'runtime_key_mismatch'),
                 ('合成' * 32, KEY, 'runtime_key_mismatch')]
        for configured, supplied, reason in cases:
            with self.subTest(reason=reason, empty_header=supplied == ''):
                # Entire environment is synthetic during the ASGI call.
                env = {} if configured is None else {'BANFEI_RUNTIME_SHARED_KEY': configured}
                headers = {'X-Hw-Agentarts-Session-Id': str(uuid.uuid4())}
                if supplied is not None:
                    headers['X-Banfei-Runtime-Key'] = supplied
                with patch.dict(os.environ, env, clear=True), TestClient(server.create_app('match')) as client:
                    for method, path in [('GET', '/runtime-info'), ('POST', '/jobs')]:
                        response = client.request(method, path, headers=headers)
                        self.assertEqual(response.status_code, 401)
                        self.assertEqual(response.json(), {'detail': 'Unauthorized', 'reason_code': reason})
                    self.assertFalse(client.app.state.jobs)
                # Feed the actual ASGI denial to the existing CLI: preserve code, no credentials.
                error = HTTPError(URL, 401, 'Unauthorized', {}, io.BytesIO(response.content))
                opener = Mock()
                opener.open.side_effect = error
                stderr = io.StringIO()
                with patch.object(cli.sys.stdin, 'isatty', return_value=True), \
                     patch('builtins.input', return_value=URL), \
                     patch.object(cli.getpass, 'getpass', side_effect=[PLATFORM, KEY]), \
                     patch.object(cli, 'build_opener', return_value=opener), contextlib.redirect_stderr(stderr):
                    self.assertEqual(cli.main(['--workflow', 'match']), 1)
                self.assertIn(reason, stderr.getvalue())
                self.assertNotIn(KEY, stderr.getvalue())
                self.assertNotIn(PLATFORM, stderr.getvalue())
                opener.open.assert_called_once()

    def test_valid_shared_key_keeps_session_validation_and_handshake(self):
        env = {'BANFEI_RUNTIME_SHARED_KEY': KEY, 'BANFEI_MODEL_PROXY_API_KEY': 'synthetic-no-model'}
        with patch.dict(os.environ, env, clear=True), TestClient(server.create_app('match')) as client:
            self.assertEqual(client.get('/ping').status_code, 200)
            response = client.get('/runtime-info', headers={'X-Banfei-Runtime-Key': KEY})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), {'detail': 'Session required'})
            response = client.get('/runtime-info', headers={'x-banfei-runtime-key': KEY,
                                  'X-Hw-Agentarts-Session-Id': str(uuid.uuid4())})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['protocol'], 'banfei-runtime-v2')
            self.assertNotIn('reason_code', response.json())
            self.assertFalse(client.app.state.jobs)

    def test_build_target_selection_without_docker_or_sudo(self):
        source = (ROOT / 'deploy/agentarts/build-arm64-local.sh').read_text()
        # Execute only the real argument parser, ending before all QEMU/Docker operations.
        parser = source[source.index('# Optional single Runtime build;'):source.index('qemu_source=')]
        script = 'set -euo pipefail\nimage_options() { printf "option=%s\\n" "$@"; }\n' + parser
        for args, expected in [([], 'matching development'), (['--target', 'matching'], 'matching'),
                               (['--target', 'development', '--build-only'], 'development')]:
            result = subprocess.run(['bash', '-c', script, 'offline-target-test', *args], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Runtime targets: ' + expected + '\n', result.stdout)
            if '--build-only' in args:
                self.assertIn('option=--build-only', result.stdout)
        for args in (['--target'], ['--target', 'unknown']):
            result = subprocess.run(['bash', '-c', script, 'offline-target-test', *args], text=True, capture_output=True)
            self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
