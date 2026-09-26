"""Small configuration safety checks; no business database or real service changes."""
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('https_runtime', ROOT/'backend/scripts/https_runtime.py')
https = importlib.util.module_from_spec(spec)
spec.loader.exec_module(https)


class HttpsConfigurationTests(unittest.TestCase):
    def test_shared_origins_and_rejected_inputs(self):
        for value, bind in [('https://localhost','127.0.0.1'),('https://203.0.113.10','0.0.0.0'),('https://10.0.0.8','0.0.0.0')]:
            self.assertEqual(https.origin_settings({'BANFEI_HTTPS_ORIGIN':value}), (value,bind))
        self.assertEqual(https.origin_settings({'BANFEI_HTTPS_ORIGIN':'https://LOCALHOST:443/'}), ('https://localhost','127.0.0.1'))
        for value in ['http://localhost','https://localhost:444','https://user@localhost','https://localhost/path','https://localhost?x=1','https://localhost\n']:
            with self.assertRaises((ValueError,RuntimeError)):
                https.origin_settings({'BANFEI_HTTPS_ORIGIN':value})

    def test_busy_port_is_not_taken_over(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));listener.listen()
            with self.assertRaisesRegex(RuntimeError,'unavailable'):
                https.check_ports('127.0.0.1',[listener.getsockname()[1]])

    def test_dotenv_patch_preserves_application_secrets_and_other_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'runtime.env'
            path.write_text('JWT_SECRET_KEY="keep$exact=value"\nBANFEI_IDENTITY_ENCRYPTION_KEY=unchanged\nCORS_ORIGINS=http://localhost:3000\n')
            https.patch_env_file(path, {'CORS_ORIGINS':'https://localhost'})
            self.assertIn('JWT_SECRET_KEY="keep$exact=value"',path.read_text())
            self.assertIn('BANFEI_IDENTITY_ENCRYPTION_KEY=unchanged',path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_initialization_is_repeatable_and_preserves_keys_and_ca(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); config=root/'environment.json'; data=root/'caddy'
            (root/'frontend').mkdir();(root/'deploy').mkdir();data.mkdir()
            (root/'deploy/Caddyfile').write_text((ROOT/'deploy/Caddyfile').read_text())
            (root/'frontend/.env.local').write_text('EXISTING=keep\nNEXT_PUBLIC_API_BASE_URL=http://localhost:8000\n')
            ca=data/'data/caddy/pki/authorities/local';ca.mkdir(parents=True)
            (ca/'root.crt').write_bytes(b'existing CA');(ca/'root.key').write_bytes(b'existing private key')
            config.write_text(json.dumps({'BANFEI_HTTPS_ORIGIN':'https://localhost','JWT_SECRET_KEY':'original-signing','BANFEI_IDENTITY_ENCRYPTION_KEY':'original-encryption','DATABASE_URL':'original-database'}))
            with patch.multiple(https,ROOT=root,CONFIG=config,HTTPS=data,CADDYFILE=data/'Caddyfile'), \
                 patch.object(https,'caddy_binary',return_value='/installed/caddy'), \
                 patch.object(https,'check_ports'), patch.object(https.subprocess,'run') as run:
                run.return_value.returncode=0
                https.initialize(); first=config.read_bytes(); https.initialize()
                self.assertEqual(first,config.read_bytes())
                self.assertEqual((ca/'root.crt').read_bytes(),b'existing CA')
                self.assertEqual((ca/'root.key').read_bytes(),b'existing private key')
                values=json.loads(first)
                self.assertEqual(values['JWT_SECRET_KEY'],'original-signing')
                self.assertEqual(values['BANFEI_IDENTITY_ENCRYPTION_KEY'],'original-encryption')
                self.assertEqual(values['DATABASE_URL'],'original-database')
                self.assertEqual(values['BANFEI_IDENTITY_ORIGIN'],'https://localhost')
                self.assertIn('EXISTING=keep',(root/'frontend/.env.local').read_text())
                self.assertEqual(len(list(data.glob('config-before-*'))),1)
                self.assertIn('tls internal',(data/'Caddyfile').read_text())
                self.assertIn('skip_install_trust',(data/'Caddyfile').read_text())
                run.return_value.returncode=1
                with self.assertRaisesRegex(RuntimeError,'rejected'):https.initialize()
                self.assertEqual(config.read_bytes(),first)


if __name__=='__main__':unittest.main()
