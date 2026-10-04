"""Offline CLI tests: synthetic credentials, mocked transport, no sockets or model calls."""
import contextlib
from email.message import Message
import getpass
import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import HTTPSHandler, build_opener
from urllib.response import addinfourl
import uuid
import warnings

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_runtime_v2', ROOT / 'deploy/agentarts/verify_runtime_v2.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
URL = 'https://defaultgw-gzswgzdcgz.cn-southwest-2.huaweicloud-agentarts.com/runtimes/banfei-matching/invocations?endpoint=Latest'
KEY = 'synthetic-platform-key-never-real'
SHARED = 'synthetic-shared-key-never-real-32chars'


class Response(io.BytesIO):
    status = 200
    headers = {}


class HandshakeTests(unittest.TestCase):
    def setUp(self):
        guard = patch('socket.socket.connect', side_effect=AssertionError('Offline test attempted network'))
        guard.start()
        self.addCleanup(guard.stop)
        self.info = dict(protocol=cli.PROTOCOL, workflow='match', incarnation=str(uuid.uuid4()),
                         provider_endpoint=cli.PROXY_DIGEST)

    def transport(self, info=None, error=None, raw=None):
        opener = Mock()
        opener.open.side_effect = error
        opener.open.return_value = Response(raw if raw is not None else json.dumps(info or self.info).encode())
        return opener

    def test_both_workflows_one_get_headers_and_query(self):
        sessions = []
        for workflow in ('match', 'development'):
            opener = self.transport(dict(self.info, workflow=workflow))
            with patch.object(cli, 'build_opener', return_value=opener) as build:
                result = cli.verify(URL, workflow, KEY, SHARED)
            self.assertEqual(result['workflow'], workflow)
            opener.open.assert_called_once()
            request = opener.open.call_args.args[0]
            self.assertEqual(request.get_method(), 'GET')
            self.assertIsNone(request.data)
            self.assertEqual(request.full_url, URL.replace('/invocations?', '/invocations/runtime-info?'))
            headers = {k.lower(): v for k, v in request.header_items()}
            self.assertEqual(headers['authorization'], 'Bearer ' + KEY)
            self.assertEqual(headers['x-banfei-runtime-key'], SHARED)
            sessions.append(uuid.UUID(headers['x-hw-agentarts-session-id']))
            self.assertEqual(build.call_args.args[0].proxies, {})
            self.assertIsInstance(build.call_args.args[1], cli.NoRedirect)
        self.assertNotEqual(*sessions)

    def test_unsafe_urls_rejected_before_transport(self):
        urls = [URL.replace('https:', 'http:'), URL.replace('.com/', '.com.evil.test/'),
                URL.replace('https://', 'https://user:password@'), URL + '&token=secret',
                URL.replace('.com/', '.com:8443/'), URL + '#fragment',
                URL.replace('/invocations', '/jobs'), URL.replace('Latest', ''),
                URL.replace('/runtimes/', '/runtimes/../'), URL.replace('https://', 'https://\n')]
        with patch.object(cli, 'build_opener') as build:
            for url in urls:
                with self.subTest(url=url), self.assertRaises(cli.VerificationError):
                    cli.verify(url, 'match', KEY, SHARED)
            build.assert_not_called()

    def test_credentials_fail_before_request(self):
        with patch.object(cli, 'build_opener') as build:
            for key, shared in [('', SHARED), ('Bearer ' + KEY, SHARED), (KEY + '\n', SHARED),
                                (KEY, 'short'), (KEY, SHARED + '\r\n')]:
                with self.assertRaises(cli.VerificationError):
                    cli.verify(URL, 'match', key, shared)
            build.assert_not_called()

    def test_all_handshake_fields_checked(self):
        for field, value in [('protocol', 'banfei-runtime-v1'), ('workflow', 'development'),
                             ('provider_endpoint', '0' * 64), ('incarnation', 'invalid'), ('incarnation', None)]:
            with self.subTest(field=field, value=value):
                opener = self.transport(dict(self.info, **{field: value}))
                with patch.object(cli, 'build_opener', return_value=opener), self.assertRaisesRegex(cli.VerificationError, field):
                    cli.verify(URL, 'match', KEY, SHARED)

    def test_http_diagnostic_retained_secrets_hidden_and_no_retry(self):
        headers = Message()
        headers['X-Request-Id'] = 'synthetic-request-123'
        body = json.dumps({'error_code': 'APIG.0301', 'message': 'Unauthorized',
                           'echo': KEY + ' ' + SHARED}).encode()
        error = HTTPError(URL, 401, 'Unauthorized', headers, io.BytesIO(body))
        opener = self.transport(error=error)
        with patch.object(cli, 'build_opener', return_value=opener), self.assertRaises(cli.VerificationError) as caught:
            cli.verify(URL, 'match', KEY, SHARED)
        message = str(caught.exception)
        for expected in ('HTTP 401', 'APIG.0301', 'Unauthorized', 'synthetic-request-123'):
            self.assertIn(expected, message)
        for secret in (KEY, SHARED):
            self.assertNotIn(secret, message)
        opener.open.assert_called_once()

    def test_redirects_disabled_and_network_failure_useful(self):
        for status in (301, 302, 303, 307, 308):
            self.assertIsNone(cli.NoRedirect().redirect_request(None, None, status, '', {}, 'https://evil.test'))
        opener = self.transport(error=URLError('DNS lookup failed'))
        with patch.object(cli, 'build_opener', return_value=opener), self.assertRaisesRegex(cli.VerificationError, 'DNS lookup failed'):
            cli.verify(URL, 'match', KEY, SHARED)
        opener.open.assert_called_once()

    def test_real_urllib_redirect_pipeline_never_forwards_credentials(self):
        calls = []
        class SyntheticHTTPS(HTTPSHandler):
            def https_open(self, request):
                calls.append(request)
                headers = Message()
                headers['Location'] = 'https://evil.test/collect'
                response = addinfourl(io.BytesIO(b'redirected by gateway'), headers, request.full_url, 302)
                response.msg = 'Found'
                return response
        def offline_opener(*handlers):
            return build_opener(*handlers, SyntheticHTTPS())
        with patch.object(cli, 'build_opener', side_effect=offline_opener), self.assertRaisesRegex(cli.VerificationError, 'HTTP 302'):
            cli.verify(URL, 'match', KEY, SHARED)
        self.assertEqual(len(calls), 1)
        self.assertIn('.huaweicloud-agentarts.com/', calls[0].full_url)

    def test_malformed_and_oversized_response(self):
        for raw, expected in [(b'<html>gateway unavailable</html>', 'gateway unavailable'),
                              (b'[]', 'JSON'), (b'x' * (cli.MAX_BODY + 1), '64 KiB')]:
            opener = self.transport(raw=raw)
            with patch.object(cli, 'build_opener', return_value=opener), self.assertRaisesRegex(cli.VerificationError, expected):
                cli.verify(URL, 'match', KEY, SHARED)

    def test_interactive_cli_hides_keys_and_reports_success(self):
        output = io.StringIO()
        with patch.object(cli.sys.stdin, 'isatty', return_value=True), patch('builtins.input', side_effect=['2', URL]), \
             patch.object(cli.getpass, 'getpass', side_effect=[KEY, SHARED]) as hidden, \
             patch.object(cli, 'build_opener', return_value=self.transport(dict(self.info, workflow='development'))), \
             contextlib.redirect_stdout(output):
            self.assertEqual(cli.main([]), 0)
        self.assertEqual(hidden.call_count, 2)
        self.assertIn('握手通过', output.getvalue())
        self.assertNotIn(KEY, output.getvalue())
        self.assertNotIn(SHARED, output.getvalue())

    def test_no_terminal_or_hidden_input_support_fails_closed(self):
        with patch.object(cli.sys.stdin, 'isatty', return_value=False), patch.object(cli, 'build_opener') as build, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['--workflow', 'match']), 1)
            build.assert_not_called()
        def unavailable(*args):
            warnings.warn('Cannot control echo on the terminal.', getpass.GetPassWarning)
            raise AssertionError('Must not fall back to echoed input')
        with patch.object(cli.sys.stdin, 'isatty', return_value=True), patch('builtins.input', return_value=URL), \
             patch.object(cli.getpass, 'getpass', side_effect=unavailable), patch.object(cli, 'build_opener') as build, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cli.main(['--workflow', 'match']), 1)
            build.assert_not_called()


if __name__ == '__main__':
    unittest.main()
