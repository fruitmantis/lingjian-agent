"""Offline private-setup failure tests. Synthetic files/keys only; no PG or network."""
import copy
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import contextlib

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('private_setup_test', ROOT/'deploy/agentarts/arm/configure_private.py')
setup = importlib.util.module_from_spec(spec); spec.loader.exec_module(setup)


def state(admin=False):
    users = [{'id':u,'role':'user','status':'disabled','password_null':True} for u in sorted(setup.AUTHORS)]
    if admin: users.append({'id':'existing-admin','role':'admin','status':'active','password_null':False})
    return {'database':'banfei_agentarts','port':'55432','data':'/var/lib/banfei-agentarts-pg/data','schema':'19',
        'role':[False,False,False,False,True],'users':users,'identity_rows':0,'history_rows':0}


def values():
    return {'BANFEI_DEPLOYMENT_PROFILE':'agentarts','BANFEI_RUNTIME_MANAGER':'systemd',
        'BANFEI_IDENTITY_ORIGIN':'http://banfei-agentarts.test','CORS_ORIGINS':'http://banfei-agentarts.test',
        'BANFEI_API_PROXY_TARGET':'http://127.0.0.1:8001','NEXT_PUBLIC_API_BASE_URL':'/api',
        'DATABASE_URL':'postgresql+psycopg://banfei_agentarts_app:synthetic@127.0.0.1:55432/banfei_agentarts',
        'JWT_SECRET_KEY':'synthetic-signing-'+('x'*32),'BANFEI_IDENTITY_ENCRYPTION_KEY':base64.urlsafe_b64encode(b'0'*32).decode(),
        'BANFEI_MATCH_EXECUTOR':'runtime','BANFEI_DEVELOPMENT_EXECUTOR':'runtime',
        'LINGJIAN_UPLOADS_DIR':'/var/lib/banfei-agentarts/uploads','TMPDIR':'/var/lib/banfei-agentarts/tmp',
        'BANFEI_ERROR_LOG_PATH':'/var/log/banfei-agentarts/errors.jsonl','BANFEI_RUNTIME_URL':setup.URL,
        'BANFEI_AGENTARTS_BEARER':'synthetic-platform','BANFEI_RUNTIME_SHARED_KEY':'synthetic-shared-'+('x'*32),
        'BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED':'1'}


class FakePeer:
    def __init__(self, failure=None, initial=None):
        self.failure=failure; self.state=copy.deepcopy(initial or state()); self.marker=None
        self.staged=None; self.password=None; self.calls=[]
    def request(self, action, **payload):
        self.calls.append(action)
        if action=='marker': return {'settled':True,'marker':self.marker}
        if action=='prepare':
            if self.failure=='prepare': raise RuntimeError('synthetic failure')
            if payload['expected']!=self.state: raise RuntimeError('stale state')
            setup.validate_state(self.state)
            self.staged=copy.deepcopy(payload); return True
        if action=='rollback': self.staged=None; return True
        if action=='commit':
            if self.failure=='commit_before': raise RuntimeError('synthetic failure')
            self.marker=self.staged['setup_id']; self.password=self.staged['password']
            if self.staged['admin']:
                if any(u['role']=='admin' for u in self.state['users']): raise RuntimeError('must not overwrite admin')
                self.state['users'].append({'id':self.staged['admin']['id'],'role':'admin','status':'active','password_null':False})
            self.staged=None
            if self.failure=='commit_after': raise RuntimeError('lost acknowledgement')
            return True
        raise AssertionError(action)
    def invalidate(self):
        self.staged=None
    def fresh(self):
        other=FakePeer(initial=self.state); other.marker=self.marker; other.password=self.password
        return other


class SetupTests(unittest.TestCase):
    def test_non_tty_refuses_before_file_or_secret_access(self):
        for stdin,stderr in [(False,True),(True,False),(False,False)]:
            with self.subTest(stdin=stdin,stderr=stderr), patch.object(setup.sys,'argv',['setup']), patch.object(setup.os,'geteuid',return_value=0), patch.object(setup.sys.stdin,'isatty',return_value=stdin), patch.object(setup.sys.stderr,'isatty',return_value=stderr), patch.object(setup,'Store') as store, patch.object(setup,'hidden') as hidden, patch.object(setup.secrets,'token_urlsafe') as generate:
                with self.assertRaises(RuntimeError): setup.main()
                store.assert_not_called(); hidden.assert_not_called(); generate.assert_not_called()

    def test_hidden_warning_never_consumes_fallback_input(self):
        with patch.object(setup.getpass,'getpass',side_effect=setup.getpass.fallback_getpass), patch.object(setup.getpass,'_raw_input') as consume:
            with self.assertRaises(RuntimeError): setup.hidden('synthetic prompt')
            consume.assert_not_called()

    def test_permissions_symlinks_hardlinks_and_lock_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d); path=folder/'backend.env'; path.write_bytes(b'A=synthetic\n'); path.chmod(0o644)
            with self.assertRaises(RuntimeError): setup.private_read(path)
            path.chmod(0o600); link=folder/'linked'; link.symlink_to(path)
            with self.assertRaises(OSError): setup.private_read(link)
            link.unlink(); os.link(path,link)
            with self.assertRaises(RuntimeError): setup.private_read(path)
            link.unlink(); folder.chmod(0o777)
            with self.assertRaises(RuntimeError): setup.Store(folder)
            folder.chmod(0o700); lock=folder/'private-setup.lock'; lock.write_text(''); lock.chmod(0o644)
            with self.assertRaises(RuntimeError):
                with setup.Store(folder): pass

    def test_explicit_approval_precedes_prompt_and_generation(self):
        with patch('builtins.input',return_value='no'), patch.object(setup,'hidden') as hidden, patch.object(setup.secrets,'token_urlsafe') as generate, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError): setup.collect({},state())
            hidden.assert_not_called(); generate.assert_not_called()

    def test_existing_admin_and_local_keys_are_preserved(self):
        original=values(); out=io.StringIO()
        with patch('builtins.input',return_value='CONFIGURE AGENTARTS') as visible, patch.object(setup,'hidden',return_value=''), patch.object(setup.secrets,'token_urlsafe') as generate, contextlib.redirect_stdout(out):
            result,password,admin=setup.collect(original,state(admin=True))
        self.assertEqual(result,original); self.assertIsNone(password); self.assertIsNone(admin)
        generate.assert_not_called(); self.assertEqual(visible.call_count,1)
        self.assertNotIn(original['JWT_SECRET_KEY'],out.getvalue())
        partial=dict(original); del partial['JWT_SECRET_KEY']
        with patch.object(setup,'hidden') as hidden:
            with self.assertRaises(RuntimeError): setup.collect(partial,state(admin=True))
            hidden.assert_not_called()

    def test_valid_underscore_credentials_are_not_template_placeholders(self):
        good=values(); good['BANFEI_AGENTARTS_BEARER']='synthetic__lowercase__token'
        good['BANFEI_RUNTIME_SHARED_KEY']='synthetic__lowercase__shared'+('x'*32)
        setup.configured(setup.parse(setup.render(b'',good)))
        bad=dict(good); bad['BANFEI_AGENTARTS_BEARER']='__USER_PRIVATE_PLATFORM_API_KEY__'
        with self.assertRaises(ValueError): setup.configured(bad)

    def test_first_setup_requires_explicit_admin_and_never_stores_plain_password(self):
        original=values()
        for key in setup.LOCAL_KEYS + setup.RUNTIME_KEYS: del original[key]
        admin_password='Synthetic-test-only-123'
        with patch('builtins.input',side_effect=['CONFIGURE AGENTARTS','independent-admin','CREATE ADMIN']), patch.object(setup,'hidden',side_effect=['synthetic-platform','synthetic-shared-'+('x'*32),admin_password,admin_password]), patch.object(setup.secrets,'token_urlsafe',side_effect=['synthetic-db-password','synthetic-signing-'+('x'*32)]) as generate, patch('cryptography.fernet.Fernet.generate_key',return_value=base64.urlsafe_b64encode(b'0'*32)), patch('bcrypt.gensalt',return_value=b'synthetic-salt'), patch('bcrypt.hashpw',return_value=b'synthetic-hash'), contextlib.redirect_stdout(io.StringIO()):
            result,password,admin=setup.collect(original,state())
        self.assertEqual(generate.call_count,2); self.assertEqual(password,'synthetic-db-password')
        self.assertEqual(admin['hash'],'synthetic-hash'); self.assertEqual(admin['username'],'independent-admin')
        payload=setup.render(b'OTHER=preserved\n',result)
        self.assertNotIn(admin_password.encode(),payload); self.assertNotIn(b'BOOTSTRAP_ADMIN_PASSWORD',payload)

    def test_second_hidden_prompt_failure_precedes_generation_or_saving(self):
        with patch('builtins.input',return_value='CONFIGURE AGENTARTS'), patch.object(setup,'hidden',side_effect=['synthetic-platform',RuntimeError('no hidden input')]), patch.object(setup.secrets,'token_urlsafe') as generate, patch.object(setup,'private_write') as write, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError): setup.collect({},state())
            generate.assert_not_called(); write.assert_not_called()

    def test_admin_creation_not_approved_creates_nothing(self):
        with patch('builtins.input',side_effect=['CONFIGURE AGENTARTS','independent-admin','no']), patch.object(setup,'hidden',side_effect=['synthetic-platform','synthetic-shared-'+('x'*32),'Synthetic-only-123','Synthetic-only-123']), patch.object(setup.secrets,'token_urlsafe') as generate, patch('bcrypt.hashpw') as hash_password, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError): setup.collect({},state())
            generate.assert_not_called(); hash_password.assert_not_called()

    def test_author_credentials_status_and_existing_history_fail_closed(self):
        for field,value in [('status','active'),('role','admin'),('password_null',False)]:
            s=state(); s['users'][0][field]=value
            with self.subTest(field=field), self.assertRaises(RuntimeError): setup.validate_state(s)
        for field in ['identity_rows','history_rows']:
            s=state(); s[field]=1
            with self.subTest(field=field), self.assertRaises(RuntimeError): setup.validate_state(s)

    def fixture(self, folder):
        path=folder/'backend.env'; original=b'OTHER=preserved\n'; path.write_bytes(original); path.chmod(0o600)
        return setup.Store(folder),original,setup.render(original,values())

    def assert_clean(self,folder):
        self.assertEqual(sorted(p.name for p in folder.iterdir()),['backend.env'])
        self.assertEqual((folder/'backend.env').stat().st_mode & 0o777,0o600)

    def test_transaction_success_preserves_authors_and_never_opens_gate(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d); store,old,new=self.fixture(f); peer=FakePeer(); authors=copy.deepcopy(peer.state['users'])
            store.commit(peer,old,new,state(),'synthetic-db',{'id':'new-synthetic-admin'})
            self.assertEqual((f/'backend.env').read_bytes(),new); self.assertEqual(peer.password,'synthetic-db')
            self.assertEqual(peer.state['users'][:2],authors); self.assertEqual(len(peer.state['users']),3)
            self.assertFalse((f/'private-config-ready').exists()); self.assert_clean(f)

    def test_prepare_and_commit_failures_rollback_both_sides(self):
        for failure in ['prepare','commit_before']:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as d:
                f=Path(d); store,old,new=self.fixture(f); peer=FakePeer(failure)
                with self.assertRaises(RuntimeError): store.commit(peer,old,new,state(),'synthetic-db',{'id':'synthetic-admin'})
                self.assertTrue(store.pending.exists()); self.assertEqual(peer.state,state())
                self.assertIsNone(peer.password); self.assertIsNone(peer.marker)
                self.assertEqual(store.recover(peer.fresh()),'rolled_back')
                self.assertEqual((f/'backend.env').read_bytes(),old); self.assert_clean(f)

    def test_replace_failure_does_not_commit_database(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d); store,old,new=self.fixture(f); peer=FakePeer(); actual=setup.os.replace
            def replace(src,dst):
                if str(src).endswith('-candidate'): raise OSError('synthetic filesystem error')
                return actual(src,dst)
            with patch.object(setup.os,'replace',side_effect=replace):
                with self.assertRaises(RuntimeError): store.commit(peer,old,new,state(),'synthetic-db',{'id':'synthetic-admin'})
            self.assertTrue(store.pending.exists()); self.assertIsNone(peer.password)
            self.assertEqual(store.recover(peer.fresh()),'rolled_back')
            self.assertEqual((f/'backend.env').read_bytes(),old); self.assert_clean(f)

    def test_lost_commit_acknowledgement_is_reconciled_as_committed(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d); store,old,new=self.fixture(f); peer=FakePeer('commit_after')
            with self.assertRaisesRegex(RuntimeError,'outcome unknown'):
                store.commit(peer,old,new,state(),'synthetic-db',{'id':'synthetic-admin'})
            self.assertTrue(store.pending.exists()); self.assertEqual((f/'backend.env').read_bytes(),new)
            self.assertEqual(store.recover(peer.fresh()),'committed')
            self.assertEqual(peer.password,'synthetic-db'); self.assert_clean(f)

    def test_crash_journal_recovers_using_database_marker(self):
        for committed in [False,True]:
            with self.subTest(committed=committed), tempfile.TemporaryDirectory() as d:
                f=Path(d); store,old,new=self.fixture(f); peer=FakePeer(); ident='a'*32
                info={'id':ident,'old':setup.digest(old),'new':setup.digest(new),'candidate':'.private-setup-'+ident+'-candidate','rollback':'.private-setup-'+ident+'-rollback'}
                setup.private_write(f/info['rollback'],old); setup.private_write(store.pending,json.dumps(info).encode())
                (f/'backend.env').write_bytes(new); peer.marker=ident if committed else None
                self.assertEqual(store.recover(peer),'committed' if committed else 'rolled_back')
                self.assertEqual((f/'backend.env').read_bytes(),new if committed else old); self.assert_clean(f)

    def test_crash_before_snapshot_or_after_rollback_is_recoverable(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d); store,old,new=self.fixture(f); peer=FakePeer(); ident='b'*32
            info={'id':ident,'old':setup.digest(old),'new':setup.digest(new),'candidate':'.private-setup-'+ident+'-candidate','rollback':'.private-setup-'+ident+'-rollback'}
            setup.private_write(store.pending,json.dumps(info).encode())
            self.assertEqual(store.recover(peer),'rolled_back'); self.assert_clean(f)
            self.assertEqual((f/'backend.env').read_bytes(),old)

    def test_staging_write_failure_leaves_no_partial_private_files(self):
        for suffix in ['-rollback','-candidate']:
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as d:
                f=Path(d); store,old,new=self.fixture(f); peer=FakePeer(); actual=setup.private_write
                def write(path,content):
                    if str(path).endswith(suffix): raise OSError('synthetic full filesystem')
                    actual(path,content)
                with patch.object(setup,'private_write',side_effect=write):
                    with self.assertRaises(OSError): store.commit(peer,old,new,state(),None,None)
                self.assertEqual((f/'backend.env').read_bytes(),old); self.assertEqual(peer.calls,[]); self.assert_clean(f)

    def test_changed_file_and_missing_fields_refuse_before_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d); store,old,new=self.fixture(f); peer=FakePeer()
            for field in ['DATABASE_URL','JWT_SECRET_KEY','BANFEI_IDENTITY_ENCRYPTION_KEY','BANFEI_AGENTARTS_BEARER','BANFEI_RUNTIME_SHARED_KEY']:
                bad=values(); del bad[field]
                with self.subTest(field=field), self.assertRaises(ValueError): store.commit(peer,old,setup.render(old,bad),state(),None,None)
                self.assertEqual((f/'backend.env').read_bytes(),old); self.assertEqual(peer.calls,[]); self.assert_clean(f)
            changed=b'OTHER=changed\n'; (f/'backend.env').write_bytes(changed)
            with self.assertRaises(RuntimeError): store.commit(peer,old,new,state(),None,None)
            self.assertEqual((f/'backend.env').read_bytes(),changed); self.assertEqual(peer.calls,[])

    def test_invalid_runtime_response_causes_no_configuration_write(self):
        import httpx
        for response in [httpx.Response(401),httpx.Response(200,json={'protocol':'wrong'})]:
            with self.subTest(status=response.status_code), patch.object(httpx,'Client') as client:
                client.return_value.__enter__.return_value.get.return_value=response
                with self.assertRaises(RuntimeError): setup.verify_runtime(values())
                args=client.return_value.__enter__.return_value.get.call_args
                self.assertIn('/invocations/runtime-info?endpoint=Latest',args.args[0])
                self.assertEqual(client.call_args.kwargs['follow_redirects'],False)


if __name__=='__main__': unittest.main()
