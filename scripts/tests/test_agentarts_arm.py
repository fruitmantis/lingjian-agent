"""Offline deployment-boundary checks; no services, PG, real keys or network."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


manager = load('arm_manager_test', 'backend/scripts/enablement_environment.py')
preflight = load('arm_preflight_test', 'deploy/agentarts/arm/preflight.py')
handoff = load('arm_handoff_test', 'deploy/agentarts/arm/configure_runtime.py')
from backend.app.runtime_endpoint import validate_endpoint, operation_url

APPROVED = 'https://defaultgw-gzswgzdcgz.cn-southwest-2.huaweicloud-agentarts.com/runtimes/banfei-runtime-test/invocations'


def settings():
    return {'BANFEI_DEPLOYMENT_PROFILE': 'agentarts', 'BANFEI_RUNTIME_MANAGER': 'systemd',
        'BANFEI_IDENTITY_ORIGIN': 'http://banfei-agentarts.test', 'CORS_ORIGINS': 'http://banfei-agentarts.test',
        'DATABASE_URL': 'postgresql+psycopg://banfei_agentarts_app:synthetic@127.0.0.1:55432/banfei_agentarts',
        'LINGJIAN_UPLOADS_DIR': '/var/lib/banfei-agentarts/uploads', 'TMPDIR': '/var/lib/banfei-agentarts/tmp',
        'BANFEI_ERROR_LOG_PATH': '/var/log/banfei-agentarts/errors.jsonl',
        'BANFEI_MATCH_EXECUTOR': 'runtime', 'BANFEI_DEVELOPMENT_EXECUTOR': 'runtime',
        'BANFEI_API_PROXY_TARGET': 'http://127.0.0.1:8001'}


class DeploymentTests(unittest.TestCase):
    def test_profile_is_explicit_and_services_exclude_original_and_caddy(self):
        self.assertEqual(manager.systemd_units(settings()), manager.AGENTARTS_UNITS)
        with self.assertRaises(RuntimeError): manager.systemd_units({})
        with patch.object(manager, 'ROOT', Path('/opt/banfei/builds/original')):
            self.assertEqual(manager.systemd_units({}), manager.SYSTEMD_UNITS)
        with self.assertRaises(RuntimeError): manager.systemd_units({'BANFEI_DEPLOYMENT_PROFILE': 'typo'})

    def test_new_profile_requires_hostname_own_pg_paths_and_runtime(self):
        manager.validate_agentarts(settings())
        self.assertEqual(manager.origins(settings()), ['http://banfei-agentarts.test'])
        for key, value in [('BANFEI_RUNTIME_MANAGER', 'local'), ('DATABASE_URL', 'postgresql://banfei_app:x@127.0.0.1:5432/banfei_arm'),
                           ('LINGJIAN_UPLOADS_DIR', '/opt/banfei/uploads'), ('BANFEI_MATCH_EXECUTOR', 'local')]:
            with self.subTest(key=key), self.assertRaises(RuntimeError): manager.validate_agentarts({**settings(), key: value})
        for origin in ['http://113.44.99.83', 'http://localhost', 'https://banfei-agentarts.test', 'http://banfei-agentarts.test:3001']:
            with self.subTest(origin=origin), self.assertRaises(RuntimeError): manager.origins({**settings(), 'BANFEI_IDENTITY_ORIGIN': origin})

    def test_start_stop_status_only_address_own_services_and_health(self):
        with patch.object(manager, 'read_environment', return_value=settings()), patch.object(manager, 'require_root'), patch.object(manager, 'validate_agentarts_frontend'), \
             patch.object(manager.subprocess, 'run') as run, patch.object(manager, 'urlopen') as health, contextlib.redirect_stdout(io.StringIO()):
            run.return_value.returncode = 0
            health.return_value.__enter__.return_value.status = 200
            manager.start(); manager.stop(); manager.status()
            self.assertEqual(run.call_args_list[0].args[0], ['systemctl', 'start', *manager.AGENTARTS_UNITS])
            self.assertEqual(run.call_args_list[1].args[0], ['systemctl', 'stop', *reversed(manager.AGENTARTS_UNITS)])
            self.assertEqual(health.call_args.args[0], 'http://127.0.0.1:3001/api/health')
            self.assertTrue(all('banfei-http.service' not in call.args[0] for call in run.call_args_list))

    def test_wrong_frontend_target_fails_before_any_service_start(self):
        with tempfile.TemporaryDirectory() as folder:
            frontend = Path(folder)/'frontend.env'
            frontend.write_text('NEXT_PUBLIC_API_BASE_URL=/api\nBANFEI_API_PROXY_TARGET=http://127.0.0.1:8000\nBANFEI_IDENTITY_ORIGIN=http://banfei-agentarts.test\n')
            with patch.object(manager, 'AGENTARTS_FRONTEND_ENV', frontend), patch.object(manager, 'read_environment', return_value=settings()), patch.object(manager, 'require_root'), patch.object(manager.subprocess, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'mismatch'): manager.start()
                run.assert_not_called()
                frontend.write_text(frontend.read_text().replace(':8000', ':8001'))
                manager.validate_agentarts_frontend(settings())

    def test_init_only_updates_own_config_and_external_frontend_env(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); config = root/'backend.json'; front = root/'frontend.env'
            config.write_text(json.dumps({**settings(), 'JWT_SECRET_KEY': 'preserve-synthetic-key'}))
            with patch.multiple(manager, ROOT=root, CONFIG=config, AGENTARTS_FRONTEND_ENV=front), \
                 patch.object(manager, 'running', return_value=False), patch.object(manager, 'check_ports') as ports, \
                 patch.object(manager, 'caddy_binary') as caddy, patch.object(manager.subprocess, 'run') as run, contextlib.redirect_stdout(io.StringIO()):
                run.return_value.returncode = 3
                manager.initialize()
                self.assertEqual(json.loads(config.read_text())['JWT_SECRET_KEY'], 'preserve-synthetic-key')
                self.assertIn('BANFEI_API_PROXY_TARGET=http://127.0.0.1:8001', front.read_text())
                self.assertFalse((root/'frontend').exists()); ports.assert_not_called(); caddy.assert_not_called()
                self.assertEqual({call.args[0][-1] for call in run.call_args_list}, set(manager.AGENTARTS_UNITS))

    def test_next_accepts_loopback_8000_and_8001_and_rejects_other_destinations(self):
        for target in ['http://127.0.0.1:8000', 'http://127.0.0.1:8001', 'https://127.0.0.1:8001',
                       'http://example.com:8001', 'http://127.0.0.1:80', 'http://user@127.0.0.1:8001', 'http://127.0.0.1:8001/?x=1']:
            environment = {**os.environ, 'BANFEI_API_PROXY_TARGET': target}
            result = subprocess.run(['node', '--input-type=module', '-e', 'await import('+json.dumps(str(ROOT/'frontend/next.config.mjs'))+')'], env=environment, capture_output=True)
            with self.subTest(target=target): self.assertEqual(result.returncode == 0, target in ['http://127.0.0.1:8000', 'http://127.0.0.1:8001'])

    def test_preflight_rejects_placeholder_configuration(self):
        self.assertTrue(preflight.configuration_errors(settings()))
        self.assertTrue(all('synthetic@' not in error for error in preflight.configuration_errors(settings())))

    def test_handoff_atomic_private_write_preserves_unrelated_values(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'backend.env'; path.write_text('OTHER=preserved\nBANFEI_RUNTIME_SHARED_KEY=old-synthetic\n'); path.chmod(0o600)
            original = path.read_bytes()
            handoff.replace_values(path, original, {'BANFEI_RUNTIME_SHARED_KEY': 'new-synthetic-only'})
            self.assertEqual(path.read_text(), 'OTHER=preserved\nBANFEI_RUNTIME_SHARED_KEY=new-synthetic-only\n')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(RuntimeError): handoff.replace_values(path, original, {'KEY': 'synthetic'})
            before = path.read_bytes()
            with self.assertRaises(ValueError): handoff.replace_values(path, before, {'KEY': 'bad\nNEW=field'})
            self.assertEqual(path.read_bytes(), before)
            link = Path(folder)/'link'; link.symlink_to(path)
            with self.assertRaises(RuntimeError): handoff.replace_values(link, before, {'KEY': 'synthetic'})

    def test_handoff_refuses_before_prompt_if_noninteractive(self):
        with patch.object(handoff.sys, 'argv', ['configure_runtime.py']), patch.object(handoff.os, 'geteuid', return_value=0), \
             patch.object(handoff.sys.stdin, 'isatty', return_value=False), patch.object(handoff.getpass, 'getpass') as prompt:
            with self.assertRaises(RuntimeError): handoff.main()
            prompt.assert_not_called()


    def test_handoff_echo_fallback_aborts_before_read_and_preserves_file(self):
        # Exercise Python's real fallback: its warning must stop _raw_input,
        # both before the first credential and after one hidden prompt succeeds.
        for failing_prompt in (1, 2):
            with self.subTest(failing_prompt=failing_prompt), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'backend.env'
                original = (b'BANFEI_DEPLOYMENT_PROFILE=agentarts\n'
                            b'BANFEI_MATCH_EXECUTOR=runtime\n'
                            b'BANFEI_DEVELOPMENT_EXECUTOR=runtime\n'
                            b'OTHER=preserved\n')
                path.write_bytes(original); path.chmod(0o600)
                config = SimpleNamespace(parent=path.parent, is_file=path.is_file,
                    is_symlink=path.is_symlink, read_bytes=path.read_bytes,
                    stat=lambda: SimpleNamespace(st_uid=0, st_mode=0o100600, st_nlink=1))
                prompts = []
                def simulated_terminal(prompt):
                    prompts.append(prompt)
                    if len(prompts) == failing_prompt:
                        return handoff.getpass.fallback_getpass(prompt)
                    return 'synthetic-hidden-platform-key'
                stdout, stderr = io.StringIO(), io.StringIO()
                with patch.object(handoff, 'CONFIG', config), \
                     patch.object(handoff.sys, 'argv', ['configure_runtime.py']), \
                     patch.object(handoff.os, 'geteuid', return_value=0), \
                     patch.object(handoff.sys.stdin, 'isatty', return_value=True), \
                     patch.object(handoff.getpass, 'getpass', side_effect=simulated_terminal), \
                     patch.object(handoff.getpass, '_raw_input') as echoed_input, \
                     patch.object(handoff, 'replace_values') as save, \
                     contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    with self.assertRaisesRegex(RuntimeError, 'Hidden terminal input unavailable'):
                        handoff.main()
                    echoed_input.assert_not_called(); save.assert_not_called()
                self.assertEqual(len(prompts), failing_prompt)
                self.assertEqual(path.read_bytes(), original)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(list(Path(folder).iterdir()), [path])
                self.assertEqual(stdout.getvalue() + stderr.getvalue(), '')


class EndpointTests(unittest.TestCase):
    def test_latest_and_named_endpoint_survive_every_operation(self):
        operation = str(uuid.uuid4())
        for selector in ['Latest', 'dev']:
            base, local = validate_endpoint(APPROVED+'?endpoint='+selector, external_approved=True)
            self.assertFalse(local)
            for suffix in ['runtime-info', 'jobs', 'jobs/'+operation, 'jobs/'+operation+'/retry']:
                self.assertEqual(operation_url(base, suffix), APPROVED+'/'+suffix+'?endpoint='+selector)

    def test_unknown_duplicate_or_untrusted_query_is_rejected(self):
        for query in ['endpoint=Latest&endpoint=dev', 'token=secret', 'endpoint=', 'endpoint=https://evil.invalid', 'endpoint=Latest&x=1', 'endpoint=Latest%26x%3D1']:
            with self.subTest(query=query), self.assertRaises(ValueError): validate_endpoint(APPROVED+'?'+query, external_approved=True)

    def test_destination_path_and_approval_are_fail_closed(self):
        with self.assertRaises(ValueError): validate_endpoint(APPROVED+'?endpoint=Latest')
        for url in [APPROVED.replace('https:', 'http:'), APPROVED.replace('huaweicloud-agentarts.com', 'huaweicloud-agentarts.com.evil.invalid'),
                    APPROVED.replace('defaultgw-gzswgzdcgz.cn-southwest-2.huaweicloud-agentarts.com', '127.0.0.1'),
                    APPROVED.replace('/invocations', '/invocations/../other'), APPROVED+'#fragment']:
            with self.subTest(url=url), self.assertRaises(ValueError): validate_endpoint(url, external_approved=True)
        with self.assertRaises(ValueError): operation_url(APPROVED, '//evil.invalid/path')

    def test_loopback_test_transport_keeps_original_paths(self):
        with self.assertRaises(ValueError): validate_endpoint('http://127.0.0.1:19081')
        base, local = validate_endpoint('http://127.0.0.1:19081', local_test=True)
        self.assertTrue(local); self.assertEqual(operation_url(base, 'jobs'), 'http://127.0.0.1:19081/jobs')

    def test_real_bridge_dispatch_keeps_endpoint_selector_and_pins_it(self):
        import httpx
        from backend.app import runtime_bridge as bridge
        from backend.agent_runtime.contracts import model_route
        incarnation = str(uuid.uuid4()); saved = {}; seen = []; wire = {}
        def handle(request):
            seen.append(str(request.url))
            if request.url.path.endswith('/runtime-info'):
                return httpx.Response(200, json={'protocol':'banfei-runtime-v1','incarnation':incarnation,
                    'provider_route':model_route('https://api.deepseek.com','deepseek-flash')})
            if request.method == 'POST' and request.url.path.endswith('/jobs'):
                wire['packet'] = json.loads(request.content)
                status, attempt = 'accepted', 0
            elif request.method == 'GET':
                status, attempt = 'awaiting_retry', 1
            else:
                self.assertTrue(request.url.path.endswith('/retry'))
                self.assertEqual(json.loads(request.content)['after_attempt'], 1)
                status, attempt = 'completed', 2
            packet = wire['packet']
            return httpx.Response(202 if request.method == 'POST' else 200, json={**{k:packet[k] for k in ('protocol','task_id','run_id','session_id','operation_id','incarnation','workflow','stage','snapshot','model_fingerprint')},
                'status':status,'attempt':attempt,'updated_at':'2026-10-02T00:00:00Z','result':{'in_scope':False}})
        @contextlib.contextmanager
        def db(): yield SimpleNamespace(lock_writer=lambda:None)
        values = {'BANFEI_MATCH_EXECUTOR':'runtime','BANFEI_RUNTIME_URL':APPROVED+'?endpoint=Latest',
            'BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED':'1','BANFEI_RUNTIME_SHARED_KEY':'synthetic-only-012345678901234567890','BANFEI_AGENTARTS_BEARER':'synthetic-only'}
        with patch.dict(os.environ, values), patch.multiple(bridge, get_db=db, authorize=lambda *args:None, source_stamp=lambda conn:'same',
                load=lambda conn,key:copy.deepcopy(saved.get(key)), save=lambda conn,key,value:saved.update({key:copy.deepcopy(value)}),
                pinned_configuration=lambda *args:None, configuration_stamp=lambda cfg:{'fingerprint':'a'*64},
                model_config_from_record=lambda cfg:SimpleNamespace(base_url='https://api.deepseek.com',model='deepseek-flash',temperature=.3,top_p=1,max_tokens=1000),
                get_settings=lambda:SimpleNamespace(timeoutSeconds=1,timeoutRetries=1),
                client_for=lambda:httpx.Client(transport=httpx.MockTransport(handle),trust_env=False)), \
                bridge.run_scope('match',str(uuid.uuid4()),str(uuid.uuid4())):
            raw = bridge.execute_stage('match','understanding',{'requirement':'synthetic','standard_tags':[]},{},lambda:None)
            self.assertFalse(json.loads(raw)['in_scope'])
            operation = wire['packet']['operation_id']
            self.assertEqual(seen, [APPROVED+'/runtime-info?endpoint=Latest', APPROVED+'/jobs?endpoint=Latest',
                APPROVED+'/jobs/'+operation+'?endpoint=Latest', APPROVED+'/jobs/'+operation+'/retry?endpoint=Latest'])
            os.environ['BANFEI_RUNTIME_URL'] = APPROVED+'?endpoint=dev'
            with self.assertRaisesRegex(ValueError,'destination changed'):
                bridge.execute_stage('match','initial_selection',{}, {},lambda:None)
            self.assertEqual(len(seen),4)


if __name__ == '__main__': unittest.main()
