"""Synthetic-only importer tests in /tmp. No production authenticity bypass exists.

Transaction tests replace ONLY the synthetic-origin rejection in the validator to
exercise persistence. Public/CLI validation still rejects this exact same package.
All other schema, permission, publication and imported checks run unchanged.
"""
import hashlib
import json
import os
import socket
import sqlite3
from pathlib import Path

import pytest
from backend.app.database import DATABASE_PATH,get_db
from backend.tests.conftest import make_partner,make_user
from scripts import import_pilot_data as imp
from scripts import validate_pilot_data as v
from scripts.pilot_import_contract import fingerprints,package_identity


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*a,**k):raise AssertionError('Network or model invocation forbidden')
    monkeypatch.setattr(socket.socket,'connect',denied)
    monkeypatch.setattr('backend.app.development_model.completion',denied)
    connect=sqlite3.connect
    def protected_connect(database,*a,**k):
        text=str(database)
        assert str(v.STABLE)+'/' not in text
        assert str(v.ROOT/'.isolation/runtime/app.db') not in text
        return connect(database,*a,**k)
    monkeypatch.setattr(sqlite3,'connect',protected_connect)


@pytest.fixture
def env(client,tmp_path):
    source_reviewer=make_user('source-reviewer',role='admin')
    actor=make_user('import-operator',role='admin')
    user=make_user('ordinary-import-user')
    make_partner()
    with get_db() as conn:
        conn.execute("UPDATE partners SET name='离线事务校验对象' WHERE id='partner-1'")
        conn.execute("INSERT INTO cases VALUES ('atomic-case','partner-1','内部记录',?,'2026-01-01')",(v.CANARY,))
        tag=conn.execute('SELECT id FROM capability_tags WHERE enabled=1 LIMIT 1').fetchone()[0]
    # Explicit legacy-data fault injection, only into this pytest disposable DB.
    with sqlite3.connect(DATABASE_PATH) as conn:
        for i in (1,2):conn.execute('INSERT INTO cases VALUES (?,?,?,?,?)',(f'legacy-orphan-{i}','absent-owner','旧异常','旧异常','2026-01-01'))
    package=tmp_path/'synthetic-package';package.mkdir()
    for kind in ('course','lab','case'):
        meta={'title':'离线事务资源','summary':'公开可用的内容','source_platform':'来源平台',
            'source_url':'https://training.vendor.edu/catalog','capability_tag_ids':[tag]}
        if kind=='case':meta.update(methods='分阶段实践方法',contributor_role='实施职责')
        else:meta.update(resource_type=kind,target_capability='数据库迁移',audience='工程师',product_direction='数据库',
            difficulty='beginner',language='中文',site='全球',prerequisites='基础操作',duration_minutes=60,
            cost='unknown',account_requirement='未知',environment_requirement='浏览器')
        entry={'source_type':kind,'source_id':'atomic-case' if kind=='case' else None,'source_version':None,
            'contributor_id':'partner-1' if kind=='case' else None,'status':'published','metadata':meta,
            'permissions':{'base_revision':7,'system_visible':True,'model_allowed':True,'partner_allowed':True,'reason':'业务来源授权证据'},
            'review':{'base_revision':7,'link_status':'available','content_checked':True,'authorization_checked':True,'note':'业务原始核验说明'},
            'reviewer_id':source_reviewer['id'],'reviewed_at':'2026-01-01T00:00:00+00:00'}
        (package/(kind+'.json')).write_text(json.dumps(entry,ensure_ascii=False))
    request=v.DevelopmentRequest(target_partner_id='partner-1',raw_demand='完成数据库迁移交付',development_goal='迁移交付',
        trainee_role='工程师',trainee_count=2,known_baseline='基础操作',duration_weeks=4,hours_per_week=2,
        constraints={k:'无要求' for k in ('language','site','account','network','environment','cost','budget')},
        targets=[{'capability_tag_id':tag,'requirement':'迁移交付'}],model_input_allowed=True).model_dump()
    body={'package_kind':'synthetic','target_partner_name':'离线事务校验对象','allowed_diagnostic_scope':['仅离线结构化内容'],
        'request':request,'resources':['course.json','lab.json'],'shared_cases':['case.json'],
        'resource_gaps':{'reviewed':True,'items':[],'no_known_gaps_reason':'格式路径完整'}}
    manifest=package/'manifest.json';manifest.write_text(json.dumps(body,ensure_ascii=False))
    (package/'business-signoff.md').write_text('SYNTHETIC FIXTURE. No real business approval.\n')
    runtime=tmp_path/'runtime'/'app.db';runtime.parent.mkdir()
    imp.backup(DATABASE_PATH,runtime)
    pilot=tmp_path/'pilot'/'atomic'/'app.db'
    imp.prepare(runtime,pilot)
    protected=imp.sha(runtime)
    yield {'manifest':manifest,'db':pilot,'runtime':runtime,'actor':actor['id'],'reviewer':source_reviewer['id'],'user':user['id'],'tag':tag}
    assert imp.sha(runtime)==protected


@pytest.fixture
def structural_only(monkeypatch):
    original=v.inspect_package
    def test_inspect(*a,**k):
        result=original(*a,**k)
        result['errors']=[e for e in result['errors'] if e['code'] not in {'REAL_PACKAGE_REQUIRED','TEST_DATA_FORBIDDEN'}]
        result['machine_status']='FAIL' if result['errors'] else 'PASS'
        return result
    monkeypatch.setattr(v,'inspect_package',test_inspect)


def apply(e,**kw):return imp.apply(e['manifest'],e['db'],'atomic',e['actor'],**kw)
def state(e):
    with v.readonly_database(e['db']) as conn:return imp.state(conn)
def change(e,file,fn):
    path=e['manifest'].parent/file;data=json.loads(path.read_text());fn(data);path.write_text(json.dumps(data,ensure_ascii=False))


def test_public_gate_rejects_synthetic(env):
    before=state(env);filehash=imp.sha(env['db'])
    assert imp.dry_run(env['manifest'],env['db'],'atomic')['status']=='INVALID'
    with pytest.raises(imp.ImportFailure,match='PACKAGE_PRECHECK_FAILED'):apply(env)
    assert v.validate(env['manifest'],env['db'])['machine_status']=='FAIL'
    assert state(env)==before and imp.sha(env['db'])==filehash
    assert not (env['db'].parent/'imports').exists()


def test_dry_run_readonly(env,structural_only):
    before=state(env);filehash=imp.sha(env['db']);inputs=fingerprints(env['manifest'])
    assert imp.dry_run(env['manifest'],env['db'],'atomic')['status']=='VALID'
    assert state(env)==before and imp.sha(env['db'])==filehash and fingerprints(env['manifest'])==inputs
    assert not (env['db'].parent/'imports').exists()


def test_atomic_success_immutable_ledger_and_real_actor(env,structural_only):
    before=state(env);original=fingerprints(env['manifest'])
    result=apply(env);assert result['machine_import_status']=='PASS'
    ledger=json.loads(Path(result['ledger']).read_text());txn=ledger['transaction']
    assert fingerprints(env['manifest'])==original
    assert txn['package_sha256']==original['package_sha256'] and txn['manifest_sha256']==original['manifest_sha256']
    assert len(txn['items'])==3 and txn['business_signoff_status']=='NOT RUN'
    assert ledger['business_signoff_status']=='NOT RUN'
    with v.readonly_database(env['db']) as conn:
        assert conn.execute('SELECT COUNT(*) FROM enablement_resources').fetchone()[0]==2
        assert conn.execute('SELECT COUNT(*) FROM enablement_resource_versions').fetchone()[0]==2
        assert conn.execute('SELECT COUNT(*) FROM resource_capability_map').fetchone()[0]==2
        assert conn.execute('SELECT COUNT(*) FROM case_share_configs').fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM case_share_versions').fetchone()[0]==1
        assert conn.execute('SELECT COUNT(*) FROM enablement_reviews').fetchone()[0]==3
        assert conn.execute('SELECT COUNT(*) FROM enablement_audit_events').fetchone()[0]==12
        assert {r[0] for r in conn.execute('SELECT actor_id FROM enablement_audit_events')}=={env['actor']}
        for item in txn['items']:
            assert item['reviewer_id']==env['actor'] and item['source_review_evidence']['reviewer_id']==env['reviewer']
            assert item['reviewed_at']!=item['source_review_evidence']['reviewed_at']
            assert item['source_version']==1 and item['authorization_epoch']==1 and item['revision']==3
            assert item['capability_tag_ids']==[env['tag']] and item['review_id']
        assert imp.state(conn)['foreign_key_violations']==before['foreign_key_violations']
        assert imp.state(conn)['counts']==txn['after']['counts']
        meta=json.loads(conn.execute('SELECT payload_json FROM enablement_resource_versions LIMIT 1').fetchone()[0])
        assert meta['cost']=='unknown' and meta['account_requirement']=='未知'
    assert v.validate(env['manifest'],env['db'],True,import_ledger=Path(result['ledger']))['machine_status']=='PASS'
    assert imp.sha(txn['snapshot']['path'])==txn['snapshot']['sha256']
    with v.readonly_database(txn['snapshot']['path']) as conn:assert imp.state(conn)==before
    # Restore rehearsal creates a NEW private DB from backup, never replaces a live one.
    restored=env['db'].parents[1]/'restored'/'app.db';imp.prepare(txn['snapshot']['path'],restored)
    with v.readonly_database(restored) as conn:assert imp.state(conn)==before


@pytest.mark.parametrize('stage',['course_created','resource_version','capability_map','review_created','resource_published',
    'lab_import','case_config','case_version','case_published','before_audit_ledger','before_commit'])
def test_fault_rolls_back_every_table(env,structural_only,stage):
    before=state(env);filehash=imp.sha(env['db']);inputs=fingerprints(env['manifest']);fired=[]
    def fault(at,conn):
        if at==stage:fired.append(at);raise RuntimeError('injected')
    with pytest.raises(RuntimeError,match='injected'):apply(env,_fault=fault)
    assert fired and state(env)==before and imp.sha(env['db'])==filehash
    assert fingerprints(env['manifest'])==inputs
    assert not list(env['db'].parent.rglob('import-ledger.json'))


@pytest.mark.parametrize('actor',['missing','user','disabled','locked'])
def test_invalid_actor(env,structural_only,actor):
    selected='does-not-exist' if actor=='missing' else env['user'] if actor=='user' else env['actor']
    with sqlite3.connect(env['db']) as conn:
        if actor=='disabled':conn.execute("UPDATE users SET status='disabled' WHERE id=?",(selected,))
        if actor=='locked':conn.execute("UPDATE users SET locked_until='2099-01-01T00:00:00+00:00' WHERE id=?",(selected,))
    before=state(env)
    with pytest.raises(imp.ImportFailure,match='ACTIVE_ADMIN_ACTOR_REQUIRED'):imp.apply(env['manifest'],env['db'],'atomic',selected)
    assert state(env)==before


@pytest.mark.parametrize('failure',['schema','stable','runtime','symlink','hardlink'])
def test_database_boundaries(env,structural_only,tmp_path,failure):
    path=env['db']
    if failure=='schema':
        with sqlite3.connect(path) as conn:conn.execute("UPDATE app_metadata SET value='9' WHERE key='schema_version'")
    elif failure=='stable':path=v.STABLE/'data/app.db'
    elif failure=='runtime':path=env['runtime']
    else:
        path=tmp_path/'pilot'/failure/'app.db';path.parent.mkdir(parents=True)
        path.symlink_to(env['db']) if failure=='symlink' else os.link(env['db'],path)
    try:
        with pytest.raises(ValueError):imp.apply(env['manifest'],path,'atomic',env['actor'])
    finally:
        if failure=='hardlink':path.unlink()


@pytest.mark.parametrize('failure',['partner','case','orphan','tag','review','secret'])
def test_invalid_input(env,structural_only,failure):
    if failure=='partner':change(env,'manifest.json',lambda p:p['request'].update(target_partner_id='invalid'))
    elif failure=='case':change(env,'case.json',lambda p:p.update(source_id='invalid'))
    elif failure=='orphan':change(env,'case.json',lambda p:p.update(source_id='legacy-orphan-1'))
    elif failure=='tag':change(env,'lab.json',lambda p:p['metadata'].update(capability_tag_ids=['invalid']))
    elif failure=='review':change(env,'course.json',lambda p:p['review'].update(content_checked=False))
    elif failure=='secret':change(env,'case.json',lambda p:p['metadata'].update(summary=v.CANARY))
    before=state(env)
    with pytest.raises(imp.ImportFailure,match='PRECHECK_FAILED'):apply(env)
    assert state(env)==before


@pytest.mark.parametrize('flags',[(a,b,c) for a in (False,True) for b in (False,True) for c in (False,True)])
def test_permission_matrix_no_inference(env,structural_only,flags):
    path=env['manifest'].parent/'extra.json';record=json.loads((path.parent/'course.json').read_text())
    record['permissions'].update(dict(zip(v.FLAGS,flags)));path.write_text(json.dumps(record))
    change(env,'manifest.json',lambda p:p['resources'].append('extra.json'))
    result=apply(env);ledger=json.loads(Path(result['ledger']).read_text());extra=ledger['transaction']['items'][2]
    with v.readonly_database(env['db']) as conn:
        row=conn.execute('SELECT * FROM enablement_resources WHERE id=?',(extra['source_id'],)).fetchone()
        assert tuple(bool(row[f]) for f in v.FLAGS)==flags
    assert v.validate(env['manifest'],env['db'],True,import_ledger=Path(result['ledger']))['machine_status']=='PASS'


def test_idempotency_and_revision_conflict(env,structural_only):
    first=apply(env);before=state(env);second=apply(env)
    assert second['status']=='already_imported' and second['import_id']==first['import_id']
    assert state(env)==before
    # Signoff is also part of immutable package identity.
    (env['manifest'].parent/'business-signoff.md').write_text('Changed synthetic signoff')
    with pytest.raises(imp.ImportFailure,match='PACKAGE_ID_HASH_CONFLICT'):apply(env)
    assert state(env)==before


def test_different_package_cannot_overwrite_existing(env,structural_only):
    result=apply(env);before=state(env)
    with pytest.raises(imp.ImportFailure,match='CASE_SHARING_ALREADY_EXISTS'):imp.apply(env['manifest'],env['db'],'second',env['actor'])
    ledger=json.loads(Path(result['ledger']).read_text());item=ledger['transaction']['items'][0]
    change(env,'course.json',lambda p:p.update(source_id=item['source_id'],source_version=1))
    with pytest.raises(imp.ImportFailure,match='EXISTING_RESOURCE_UPDATE_NOT_SUPPORTED'):imp.apply(env['manifest'],env['db'],'third',env['actor'])
    assert state(env)==before


def test_input_change_and_new_fk_fail_before_commit(env,structural_only):
    before=state(env)
    def change_input(stage,conn):
        if stage=='before_audit_ledger':(env['manifest'].parent/'business-signoff.md').write_text('changed')
    with pytest.raises(imp.ImportFailure,match='INPUT_PACKAGE_CHANGED'):apply(env,_fault=change_input)
    assert state(env)==before


def test_ledger_write_failure_recovers_without_duplicate(env,structural_only,monkeypatch):
    original=imp.write_ledger
    def broken(*a):raise OSError('disk full')
    monkeypatch.setattr(imp,'write_ledger',broken)
    with pytest.raises(imp.ImportFailure,match='COMMITTED_REQUIRES'):apply(env)
    before=state(env)
    assert before['counts']['enablement_resources']==2
    monkeypatch.setattr(imp,'write_ledger',original)
    recovered=apply(env)
    assert recovered['status']=='already_imported' and Path(recovered['ledger']).exists()
    assert state(env)==before


def test_ledger_tamper_and_no_model_unlock(env,structural_only):
    result=apply(env);path=Path(result['ledger']);record=json.loads(path.read_text())
    checked=v.validate(env['manifest'],env['db'],True,import_ledger=path)
    gate=v.real_model_precheck(checked,env['db'])
    assert gate['status']=='BLOCKED' and gate['real_model_calls']==0
    record['transaction']['items'][0]['source_id']='invented';path.write_text(json.dumps(record))
    assert v.validate(env['manifest'],env['db'],True,import_ledger=path)['machine_status']=='FAIL'


@pytest.mark.parametrize('failure',['new_fk','same_count_different_fk','capability_map'])
def test_precommit_relational_validation_failure_rolls_back(env,structural_only,failure):
    before=state(env);filehash=imp.sha(env['db'])
    def corrupt(stage,conn):
        if stage!='before_audit_ledger':return
        if failure=='capability_map':conn.execute('DELETE FROM resource_capability_map')
        else:
            conn.execute('PRAGMA defer_foreign_keys=ON')
            if failure=='same_count_different_fk':conn.execute("DELETE FROM cases WHERE id='legacy-orphan-1'")
            conn.execute("INSERT INTO cases VALUES ('new-orphan','missing','异常','故障注入','2026-01-01')")
    with pytest.raises(imp.ImportFailure,match='NEW_FK_ANOMALY|PRECOMMIT_IMPORTED_VALIDATION_FAILED'):apply(env,_fault=corrupt)
    assert state(env)==before and imp.sha(env['db'])==filehash


def test_output_symlink_and_busy_lock_rejected(env,structural_only,tmp_path):
    import fcntl
    before=state(env);external=tmp_path/'external';external.mkdir()
    link=env['db'].parent/'imports';link.symlink_to(external,target_is_directory=True)
    with pytest.raises(imp.ImportFailure,match='SYMLINK_REJECTED'):apply(env)
    assert list(external.iterdir())==[] and state(env)==before
    link.unlink()
    with env['db'].open('rb') as fd:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with pytest.raises(imp.ImportFailure,match='PILOT_IMPORT_BUSY'):apply(env)
    assert state(env)==before


def test_apply_transaction_trace_and_product_functions_unchanged(env,structural_only,monkeypatch):
    from backend.app import enablement as original
    original_get_db=original.get_db;original_save=original.save
    connect=sqlite3.connect;statements=[]
    def traced(database,*a,**k):
        conn=connect(database,*a,**k)
        if '?mode=rw' in str(database):conn.set_trace_callback(statements.append)
        return conn
    monkeypatch.setattr(sqlite3,'connect',traced)
    apply(env)
    assert statements.count('BEGIN IMMEDIATE')==1 and statements.count('COMMIT')==1
    assert original.get_db is original_get_db and original.save is original_save


def test_real_protected_files_unchanged(env,structural_only):
    frozen=json.loads((v.ROOT/'.isolation/evidence/rc-stable-start.json').read_text())
    runtime=v.ROOT/'.isolation/runtime/app.db';runtime_hash=imp.sha(runtime)
    assert all(imp.sha(v.STABLE/name)==expected for name,expected in frozen.items())
    apply(env)
    assert imp.sha(runtime)==runtime_hash
    assert all(imp.sha(v.STABLE/name)==expected for name,expected in frozen.items())



def test_prepare_captures_committed_wal_without_copying_live_db(env,tmp_path):
    source=tmp_path/'wal-source.db';imp.backup(DATABASE_PATH,source)
    with sqlite3.connect(source) as writer:
        writer.execute('PRAGMA journal_mode=WAL');writer.execute('PRAGMA wal_autocheckpoint=0')
        writer.execute("INSERT INTO app_metadata VALUES ('wal-evidence','committed-only-in-wal')");writer.commit()
        before=imp.database_hashes(source);assert '-wal' in before
        target=tmp_path/'pilot'/'wal-clone'/'app.db'
        imp.prepare(source,target)
        assert imp.database_hashes(source)==before
        with v.readonly_database(target) as conn:
            assert conn.execute("SELECT value FROM app_metadata WHERE key='wal-evidence'").fetchone()[0]=='committed-only-in-wal'
            assert conn.execute('PRAGMA journal_mode').fetchone()[0]=='delete'
    with pytest.raises(imp.ImportFailure,match='TARGET_ALREADY_EXISTS'):imp.prepare(source,target)


@pytest.mark.parametrize('mode',['dry-run','apply'])
def test_cli_rejects_synthetic_without_traceback(env,monkeypatch,capsys,mode):
    args=['import_pilot_data.py',mode,str(env['manifest']),'--database',str(env['db']),'--package-id','atomic']
    if mode=='apply':args+=['--actor-user-id',env['actor']]
    monkeypatch.setattr(imp.sys,'argv',args)
    assert imp.main()==2
    captured=capsys.readouterr();result=json.loads(captured.out)
    assert result['status'] in ('INVALID','FAILED') and result['real_model_calls']==0
    assert 'Traceback' not in captured.err+captured.out and v.CANARY not in captured.err+captured.out
