"""Safe diagnostics for the exact pre-CREATE ADMIN failure; synthetic input only."""
import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.tests.test_agentarts_private_setup import setup,state,values


class DiagnosticTests(unittest.TestCase):
    def test_password_failure_branches_have_safe_distinct_codes(self):
        samples=[('Synthetic-pass-123','Different-pass-456','ADMIN_PASSWORD_MISMATCH'),
                 ('Abc123','Abc123','ADMIN_PASSWORD_REQUIREMENTS'),
                 ('abcdefghijklmnop','abcdefghijklmnop','ADMIN_PASSWORD_REQUIREMENTS'),
                 ('1234567890123456','1234567890123456','ADMIN_PASSWORD_REQUIREMENTS'),
                 ('Ab1'+'x'*70,'Ab1'+'x'*70,'ADMIN_PASSWORD_TOO_LONG'),
                 ('界'*24+'A1','界'*24+'A1','ADMIN_PASSWORD_TOO_LONG'),
                 ('Ab1234567890'+chr(0xdcff),'Ab1234567890'+chr(0xdcff),'ADMIN_PASSWORD_ENCODING')]
        for password,confirmation,code in samples:
            with self.subTest(code=code):
                with self.assertRaises(setup.SetupError) as error: setup.validate_admin_password(password,confirmation)
                self.assertIn('['+code+']',str(error.exception))
                self.assertNotIn(password,str(error.exception)); self.assertNotIn(confirmation,str(error.exception))

    def test_initial_admin_password_minimum_is_eight_characters(self):
        with self.assertRaisesRegex(setup.SetupError, 'ADMIN_PASSWORD_REQUIREMENTS'):
            setup.validate_admin_password('Abc1234', 'Abc1234')
        setup.validate_admin_password('Abcd1234', 'Abcd1234')

    def test_existing_policy_accepts_ascii_and_utf8_boundaries(self):
        for password in ['Synthetic-123','Ab1'+'x'*69,'界'*20+'A1']:
            with self.subTest(bytes=len(password.encode())): setup.validate_admin_password(password,password)

    def test_password_retry_does_not_regenerate_or_write(self):
        out=io.StringIO(); bad='Synthetic-first-123'; good='Synthetic-good-456'
        with patch.object(setup,'hidden',side_effect=[bad,'Mismatch-789',good,good]) as prompt, patch.object(setup.secrets,'token_urlsafe') as generate, patch.object(setup,'private_write') as write, contextlib.redirect_stderr(out):
            self.assertEqual(setup.read_admin_password(),good)
            self.assertEqual(prompt.call_count,4); generate.assert_not_called(); write.assert_not_called()
        self.assertIn('[ADMIN_PASSWORD_MISMATCH]',out.getvalue())
        for value in [bad,good,'Mismatch-789']: self.assertNotIn(value,out.getvalue())

    def test_full_collect_retries_only_password_and_reaches_admin_approval(self):
        stderr=io.StringIO(); stdout=io.StringIO(); good='Synthetic-good-123'
        inputs=['synthetic-platform','synthetic-shared-'+('x'*32),'Synthetic-wrong-123','Mismatch-456',good,good]
        with patch('builtins.input',side_effect=['CONFIGURE AGENTARTS','admin','CREATE ADMIN']) as visible, patch.object(setup,'hidden',side_effect=inputs) as hidden, patch.object(setup.secrets,'token_urlsafe') as generate, patch('bcrypt.gensalt',return_value=b'synthetic-salt'), patch('bcrypt.hashpw',return_value=b'synthetic-hash'), contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result,password,admin=setup.collect(values(),state())
        self.assertEqual(hidden.call_count,6); self.assertEqual(visible.call_count,3); generate.assert_not_called()
        self.assertEqual(admin['username'],'admin'); self.assertEqual(admin['hash'],'synthetic-hash')
        self.assertIn('CREATE ADMIN',visible.call_args.args[0]); self.assertIn('[ADMIN_PASSWORD_MISMATCH]',stderr.getvalue())
        for secret in inputs: self.assertNotIn(secret,stdout.getvalue()+stderr.getvalue())

    def test_interrupts_and_unknown_technical_errors_never_echo_exception(self):
        cases=[(EOFError('synthetic-secret'),'interactive_input','INPUT_EOF'),
               (KeyboardInterrupt('synthetic-secret'),'interactive_input','INPUT_CANCELLED'),
               (RuntimeError('synthetic-secret'),'database_connection','DB_UNAVAILABLE'),
               (RuntimeError('synthetic-secret'),'runtime_verification','RUNTIME_UNAVAILABLE'),
               (ValueError('synthetic-secret'),'configuration_validation','CONFIG_INVALID')]
        for error,stage,code in cases:
            with self.subTest(code=code), patch.object(setup,'main',side_effect=error), patch.object(setup,'DIAGNOSTIC_STAGE',stage), contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(setup.run_cli(),1)
                self.assertIn('['+code+']',output.getvalue()); self.assertNotIn('synthetic-secret',output.getvalue())

    def test_runtime_401_reports_only_status_not_body_or_credentials(self):
        import httpx
        with patch.object(httpx,'Client') as client:
            client.return_value.__enter__.return_value.get.return_value=httpx.Response(401,text='synthetic-secret-response')
            with self.assertRaises(setup.SetupError) as error: setup.verify_runtime(values())
        self.assertIn('[RUNTIME_HTTP_401]',str(error.exception)); self.assertNotIn('synthetic-secret',str(error.exception))


if __name__=='__main__': unittest.main()
