"""Exact delayed-response regressions, with real Peer/Store and synthetic transport."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.tests.test_agentarts_private_setup import setup,state,values


class Wire:
    def __init__(self, *, timeout=None, broken=None, marker=None, reply_override=None):
        self.timeout=timeout; self.broken=broken; self.marker=marker; self.reply_override=reply_override
        self.sent=[]; self.queue=[]; self.closed=False; self.received=0; self.prepared=None
    def send(self, request):
        if self.closed: raise BrokenPipeError('synthetic closed channel')
        self.sent.append(request)
        action=request['action']
        if action==self.broken: raise BrokenPipeError('synthetic broken transport')
        if action=='prepare': self.prepared=request; result=True
        elif action=='commit':
            # DB COMMIT HAS SUCCEEDED; only the response is delayed.
            self.marker=self.prepared['setup_id']; result=True
        elif action=='rollback': result=True
        elif action=='marker': result={'settled':True,'marker':self.marker}
        else: result={}
        reply={'id':request['id'],'action':action,'ok':True,'result':result}
        self.queue.append(self.reply_override(reply) if self.reply_override else reply)
    def poll(self, _): return self.sent[-1]['action'] != self.timeout
    def recv(self):
        if self.closed: raise EOFError('closed')
        self.received+=1; return self.queue.pop(0)
    def close(self): self.closed=True


def channel(wire):
    peer=setup.Peer(); peer.pipe=wire
    return peer


def fixture(folder):
    original=b'OTHER=preserved\n'; (folder/'backend.env').write_bytes(original); (folder/'backend.env').chmod(0o600)
    return setup.Store(folder),original,setup.render(original,values())


def journal(store,old,new,ident='a'*32):
    info={'id':ident,'old':setup.digest(old),'new':setup.digest(new),
          'candidate':'.private-setup-'+ident+'-candidate','rollback':'.private-setup-'+ident+'-rollback'}
    setup.private_write(store.directory/info['rollback'],old)
    setup.private_write(store.pending,json.dumps(info).encode())
    store.config.write_bytes(new)
    return info


class ProtocolTests(unittest.TestCase):
    def test_exact_late_commit_never_becomes_rollback_or_marker(self):
        with tempfile.TemporaryDirectory() as d:
            store,old,new=fixture(Path(d)); wire=Wire(timeout='commit'); peer=channel(wire)
            with self.assertRaisesRegex(RuntimeError,'outcome unknown'):
                store.commit(peer,old,new,state(),'synthetic-password',{'id':'synthetic-admin'})
            self.assertEqual([x['action'] for x in wire.sent],['prepare','commit'])
            self.assertEqual(wire.received,1); self.assertEqual(wire.queue[0]['action'],'commit')
            self.assertTrue(peer.poisoned); self.assertTrue(wire.closed)
            info=json.loads(setup.private_read(store.pending))
            self.assertEqual(wire.marker,info['id']); self.assertEqual(setup.private_read(store.config),new)
            self.assertEqual(setup.private_read(store.directory/info['rollback']),old)
            for action in ['rollback','marker']:
                with self.assertRaises(RuntimeError): peer.request(action)
            self.assertEqual(wire.received,1)
            fresh=channel(Wire(marker=wire.marker))
            self.assertEqual(store.recover(fresh),'committed')
            self.assertEqual(setup.private_read(store.config),new); self.assertFalse(store.pending.exists())

    def test_late_rollback_response_cannot_be_read_as_marker(self):
        with tempfile.TemporaryDirectory() as d:
            store,old,new=fixture(Path(d)); info=journal(store,old,new)
            wire=Wire(timeout='rollback'); peer=channel(wire)
            with self.assertRaises(RuntimeError): peer.request('rollback')
            with self.assertRaises(RuntimeError): store.recover(peer)
            self.assertEqual(wire.received,0); self.assertEqual(len(wire.sent),1)
            self.assertTrue(store.pending.exists()); self.assertEqual(setup.private_read(store.config),new)
            self.assertEqual(store.recover(channel(Wire(marker=None))),'rolled_back')
            self.assertEqual(setup.private_read(store.config),old)

    def test_marker_wrong_type_or_unsettled_never_restores_or_deletes(self):
        bad=[True,False,None,{}, {'settled':False,'marker':None}, {'settled':1,'marker':None},
             {'settled':True,'marker':True}, {'settled':True,'marker':'invalid'},
             {'settled':True,'marker':None,'extra':True}]
        for value in bad:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as d:
                store,old,new=fixture(Path(d)); info=journal(store,old,new)
                wire=Wire(reply_override=lambda reply:{**reply,'result':value}); peer=channel(wire)
                with self.assertRaises(RuntimeError): store.recover(peer)
                self.assertTrue(peer.poisoned); self.assertTrue(store.pending.exists())
                self.assertEqual(setup.private_read(store.config),new)
                self.assertEqual(setup.private_read(store.directory/info['rollback']),old)

    def test_wrong_request_id_action_or_acknowledgement_poisons_channel(self):
        changes=[{'id':99},{'id':True},{'action':'commit'},{'ok':1},{'result':False},{'result':1}]
        for change in changes:
            with self.subTest(change=change):
                wire=Wire(reply_override=lambda reply:{**reply,**change}); peer=channel(wire)
                with self.assertRaises(RuntimeError): peer.request('rollback')
                self.assertTrue(peer.poisoned)
                with self.assertRaises(RuntimeError): peer.request('marker')
                self.assertEqual(len(wire.sent),1)

    def test_broken_commit_pipe_preserves_journal_and_snapshots(self):
        with tempfile.TemporaryDirectory() as d:
            store,old,new=fixture(Path(d)); wire=Wire(broken='commit'); peer=channel(wire)
            with self.assertRaisesRegex(RuntimeError,'outcome unknown'):
                store.commit(peer,old,new,state(),'synthetic-password',{'id':'synthetic-admin'})
            self.assertTrue(peer.poisoned); self.assertTrue(store.pending.exists())
            self.assertEqual(setup.private_read(store.config),new)
            info=json.loads(setup.private_read(store.pending))
            self.assertEqual(setup.private_read(store.directory/info['rollback']),old)
            self.assertEqual([x['action'] for x in wire.sent],['prepare','commit'])

    def test_fresh_recovery_timeout_preserves_everything(self):
        with tempfile.TemporaryDirectory() as d:
            store,old,new=fixture(Path(d)); info=journal(store,old,new)
            peer=channel(Wire(timeout='marker'))
            with self.assertRaises(RuntimeError): store.recover(peer)
            self.assertTrue(store.pending.exists()); self.assertEqual(setup.private_read(store.config),new)
            self.assertEqual(setup.private_read(store.directory/info['rollback']),old)

    def test_marker_requires_a_fresh_connection_even_after_valid_ack(self):
        wire=Wire(); peer=channel(wire); self.assertTrue(peer.request('rollback'))
        with self.assertRaisesRegex(RuntimeError,'fresh'): peer.request('marker')
        self.assertEqual(len(wire.sent),1)

    def test_worker_checks_transaction_settlement_before_reading_marker(self):
        for settled in [False,True]:
            with self.subTest(settled=settled):
                conn=MagicMock(); conn.__enter__.return_value=conn
                conn.execute.side_effect=[None,SimpleNamespace(fetchone=lambda:(settled,)),SimpleNamespace(fetchone=lambda:('b'*32,))]
                pipe=MagicMock(); pipe.recv.side_effect=[{'id':1,'action':'marker'},{'id':2,'action':'close'}]
                parent=MagicMock()
                with patch('psycopg.connect',return_value=conn), patch.object(setup.os,'setgroups'), patch.object(setup.os,'setgid'), patch.object(setup.os,'setuid'), patch.object(setup.os,'close') as close_fd, patch.dict(setup.os.environ,{},clear=True):
                    setup.pg_worker(pipe,123,456,parent,123456)
                parent.close.assert_called_once(); close_fd.assert_called_once_with(123456)
                self.assertEqual(conn.execute.call_args_list[0].args[0],'SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
                self.assertEqual(conn.execute.call_args_list[1].args[0],'SELECT pg_try_advisory_xact_lock(55432,20261002)')
                reply=pipe.send.call_args.args[0]
                if not settled:
                    self.assertEqual(conn.execute.call_count,2); self.assertIs(reply['ok'],False)
                else:
                    self.assertEqual(conn.execute.call_count,3); self.assertEqual(reply['result'],{'settled':True,'marker':'b'*32})
                self.assertEqual(reply['id'],1); self.assertEqual(reply['action'],'marker')


if __name__=='__main__': unittest.main()
