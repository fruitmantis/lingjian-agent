"""Synthetic, offline v2 credential handoff tests; never read host private config."""
import contextlib
import getpass
import importlib.util
import io
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import warnings

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('configure_runtime_v2', ROOT / 'deploy/agentarts/arm/configure_runtime_v2.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
ORIGINAL = (b'# synthetic configuration only\nBANFEI_DEPLOYMENT_PROFILE=agentarts\n'
            b'DATABASE_URL=postgresql+psycopg://banfei_agentarts_app:synthetic@127.0.0.1:55432/banfei_agentarts\n'
            b'JWT_SECRET_KEY=synthetic-preserved-application-signing-key\n'
            b'BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED=1\n'
            b'BANFEI_MATCH_AGENTARTS_BEARER=synthetic-old-key\n')
KEYS = {'match': ('synthetic-match-platform', 'synthetic-match-shared-key-more-than32'),
        'development': ('synthetic-development-platform', 'synthetic-development-shared-key-more-than32')}


class HandoffTests(unittest.TestCase):
    def setUp(self):
        guard = patch('socket.socket.connect', side_effect=AssertionError('Network forbidden'))
        guard.start()
        self.addCleanup(guard.stop)

    def test_candidate_four_keys_preserves_other_config_and_closes_gate(self):
        output = tool.candidate_config(ORIGINAL, KEYS)
        values = tool.parse_config(output)
        self.assertEqual(values['BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED'], '0')
        self.assertIn(b'JWT_SECRET_KEY=synthetic-preserved-application-signing-key\n', output)
        self.assertIn(b'# synthetic configuration only\n', output)
        for workflow, pair in KEYS.items():
            prefix = 'BANFEI_' + workflow.upper()
            self.assertEqual(values[prefix + '_AGENTARTS_BEARER'], pair[0])
            self.assertEqual(values[prefix + '_RUNTIME_SHARED_KEY'], pair[1])
        self.assertNotIn(b'synthetic-old-key', output)

    def test_wrong_isolation_and_unsafe_input_fail_closed(self):
        for original in (ORIGINAL.replace(b'55432', b'5432'), ORIGINAL.replace(b'=agentarts', b'=original'),
                         ORIGINAL + b'BANFEI_DEPLOYMENT_PROFILE=agentarts\n', ORIGINAL + b'INVALID LINE\n'):
            with self.assertRaises(tool.SetupError):
                tool.candidate_config(original, KEYS)
        for pair in [('Bearer synthetic', KEYS['match'][1]), ('synthetic', 'short'),
                     ('synthetic$key', KEYS['match'][1]), ('synthetic\nkey', KEYS['match'][1])]:
            with self.assertRaises((tool.SetupError, tool.VerificationError)):
                tool.candidate_config(ORIGINAL, dict(KEYS, match=pair))

    def test_atomic_private_file_and_concurrent_change(self):
        with tempfile.TemporaryDirectory(prefix='v2-handoff-offline-') as directory:
            path = Path(directory) / 'backend.env'
            path.write_bytes(ORIGINAL)
            path.chmod(0o600)
            candidate = tool.candidate_config(ORIGINAL, KEYS)
            tool.save_private(path, ORIGINAL, candidate)
            self.assertEqual(path.read_bytes(), candidate)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual([p.name for p in path.parent.iterdir()], ['backend.env'])
            with self.assertRaises(tool.SetupError):
                tool.save_private(path, ORIGINAL, candidate)
            self.assertEqual(path.read_bytes(), candidate)
            alias = path.parent / 'alias'
            alias.symlink_to(path)
            with self.assertRaises(OSError):
                tool.read_private(alias)
            path.chmod(0o644)
            with self.assertRaises(tool.SetupError):
                tool.read_private(path)

    def run_main(self, *, arguments=(), prompt=None, tty=True, verify_error=None):
        output = io.StringIO()
        with patch.object(tool.os, 'geteuid', return_value=0), \
             patch.object(tool.platform, 'machine', return_value='aarch64'), \
             patch.object(tool.sys.stdin, 'isatty', return_value=tty), \
             patch.object(tool, 'read_private', return_value=ORIGINAL) as read, \
             patch.object(tool, 'save_private') as save, \
             patch.object(tool.getpass, 'getpass', side_effect=prompt or [*KEYS['match'], *KEYS['development']]), \
             patch.object(tool, 'verify', return_value={'incarnation': 'synthetic-uuid'}, side_effect=verify_error) as verify, \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = tool.main(list(arguments))
        for pair in KEYS.values():
            for secret in pair:
                self.assertNotIn(secret, output.getvalue())
        return result, output.getvalue(), read, save, verify

    def test_default_no_network_and_explicit_verify_reuses_v2(self):
        result, output, read, save, verify = self.run_main()
        self.assertEqual(result, 0)
        save.assert_called_once()
        verify.assert_not_called()
        self.assertEqual(tool.parse_config(save.call_args.args[2])['BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED'], '0')
        result, output, read, save, verify = self.run_main(arguments=['--verify'])
        self.assertEqual(result, 0)
        self.assertEqual(verify.call_count, 2)
        self.assertEqual([c.args for c in verify.call_args_list],
                         [(tool.URLS[w], w, *KEYS[w]) for w in ('match', 'development')])

    def test_no_terminal_or_fourth_prompt_failure_no_write(self):
        result, output, read, save, verify = self.run_main(tty=False)
        self.assertEqual(result, 1)
        read.assert_not_called()
        save.assert_not_called()
        for failure in (EOFError(), getpass.GetPassWarning('Hidden input unavailable')):
            result, output, read, save, verify = self.run_main(prompt=[*KEYS['match'], KEYS['development'][0], failure])
            self.assertEqual(result, 1)
            save.assert_not_called()
            verify.assert_not_called()

    def test_failed_post_save_verification_reports_saved_state_and_sanitizes(self):
        error = tool.VerificationError('HTTP 401 reason_code=runtime_key_header_missing ' + KEYS['match'][1])
        result, output, read, save, verify = self.run_main(arguments=['--verify'], verify_error=error)
        self.assertEqual(result, 1)
        save.assert_called_once()
        self.assertIn('配置已保存', output)
        self.assertIn('runtime_key_header_missing', output)


if __name__ == '__main__':
    unittest.main()
