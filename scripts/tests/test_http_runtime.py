"""HTTP entry configuration tests; isolated temporary files only."""
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('environment', ROOT / 'backend/scripts/enablement_environment.py')
environment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(environment)


class HttpConfigurationTests(unittest.TestCase):
    def test_origin_normalization_and_rejected_inputs(self):
        self.assertEqual(environment.origins({'BANFEI_IDENTITY_ORIGIN':
            'http://203.0.113.10:80,http://LOCALHOST:80,http://203.0.113.10'}),
            ['http://203.0.113.10', 'http://localhost'])
        for value in ('https://203.0.113.10', 'http://203.0.113.10:8000',
                      'http://user@localhost', 'http://localhost/path',
                      'http://localhost?x=1', 'http://example.com'):
            with self.subTest(value=value), self.assertRaises((RuntimeError, ValueError)):
                environment.origins({'BANFEI_IDENTITY_ORIGIN': value})

    def test_busy_port_is_not_taken_over(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                environment.check_ports([listener.getsockname()[1]])

    def test_init_preserves_secrets_and_other_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'environment.json'
            frontend = root / 'frontend'
            frontend.mkdir()
            (frontend / '.env.local').write_text('EXISTING=keep\nNEXT_PUBLIC_API_BASE_URL=/old\n')
            config.write_text(json.dumps({'BANFEI_IDENTITY_ORIGIN': 'http://203.0.113.10:80,http://localhost',
                'JWT_SECRET_KEY': 'original-signing', 'BANFEI_IDENTITY_ENCRYPTION_KEY': 'original-encryption',
                'DATABASE_URL': 'original-database', 'OTHER_SETTING': 'keep'}))
            with patch.multiple(environment, ROOT=root, CONFIG=config, CADDYFILE=ROOT / 'deploy/Caddyfile'), \
                 patch.object(environment, 'caddy_binary', return_value='/installed/caddy'), \
                 patch.object(environment, 'check_ports'), \
                 patch.object(environment, 'running', return_value=False), \
                 patch.object(environment.subprocess, 'run') as run:
                run.return_value.returncode = 0
                environment.initialize()
                first = config.read_bytes()
                environment.initialize()
                self.assertEqual(first, config.read_bytes())
                values = json.loads(first)
                self.assertEqual(values['BANFEI_IDENTITY_ORIGIN'], 'http://203.0.113.10,http://localhost')
                self.assertEqual(values['CORS_ORIGINS'], values['BANFEI_IDENTITY_ORIGIN'])
                self.assertEqual(values['JWT_SECRET_KEY'], 'original-signing')
                self.assertEqual(values['BANFEI_IDENTITY_ENCRYPTION_KEY'], 'original-encryption')
                self.assertEqual(values['DATABASE_URL'], 'original-database')
                self.assertEqual(values['OTHER_SETTING'], 'keep')
                self.assertIn('EXISTING=keep', (frontend / '.env.local').read_text())
                self.assertIn('NEXT_PUBLIC_API_BASE_URL=/api', (frontend / '.env.local').read_text())
                run.return_value.returncode = 1
                with self.assertRaisesRegex(RuntimeError, 'rejected'):
                    environment.initialize()
                self.assertEqual(config.read_bytes(), first)

    def test_caddy_template_has_only_http_listener(self):
        template = (ROOT / 'deploy/Caddyfile').read_text()
        self.assertIn(':80 {', template)
        self.assertIn('reverse_proxy 127.0.0.1:3000', template)
        self.assertNotIn(':443', template)
        self.assertNotIn('tls ', template)
        self.assertNotIn('redir', template)


if __name__ == '__main__':
    unittest.main()
