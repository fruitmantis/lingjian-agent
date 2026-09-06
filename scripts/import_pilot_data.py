#!/usr/bin/env python3
"""Offline create-only atomic Pilot Package importer. No model calls or product API.

prepare clones an independent source through SQLite backup; dry-run is read-only;
apply requires a pilot path, schema 12, an active admin and full intake validation.
"""
import argparse
import fcntl
import hashlib
import json
import os
import sqlite3
import sys
import types
import uuid
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi import HTTPException
from backend.app import enablement as service
from scripts import validate_pilot_data as v
from scripts.pilot_import_contract import package_identity, fingerprints, bound_records


def now():return datetime.now(timezone.utc).isoformat()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def database_hashes(path):
    # WAL is part of committed database state; SHM is coordination, not business data.
    return {suffix or 'main':sha(str(path)+suffix) for suffix in ('','-wal') if Path(str(path)+suffix).exists()}
def dump(data):return json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'))

class ImportFailure(ValueError):
    """Only these safe codes are printed by the CLI, never underlying exceptions."""


def pilot_path(database, existing=True):
    path=Path(database).absolute()
    resolved=path.resolve()
    if resolved.is_relative_to(v.STABLE): raise ImportFailure('STABLE_DATABASE_FORBIDDEN')
    if any(p.is_symlink() for p in [path,*path.parents]): raise ImportFailure('SYMLINK_REJECTED')
    allowed=(resolved.is_relative_to(ROOT/'.isolation/pilot') and len(resolved.relative_to(ROOT/'.isolation/pilot').parts)==2) or (
        resolved.is_relative_to(Path('/tmp')) and len(path.parts)>=4 and path.parent.parent.name=='pilot')
    if not allowed or path.name!='app.db': raise ImportFailure('PILOT_DATABASE_REQUIRED_RUNTIME_FORBIDDEN')
    if existing:
        v.safe_path(path,path.parent)
    elif path.exists(): raise ImportFailure('TARGET_ALREADY_EXISTS')
    return path


def schema(conn):
    row=conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()
    if not row or row[0]!='12': raise ImportFailure('EXPECTED_SCHEMA_12')


def state(conn):
    integrity=[r[0] for r in conn.execute('PRAGMA integrity_check')]
    if integrity!=['ok']: raise ImportFailure('INTEGRITY_CHECK_FAILED')
    tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    counts={name:conn.execute('SELECT COUNT(*) FROM "'+name.replace('"','""')+'"').fetchone()[0] for name in tables}
    fk=sorted([list(r) for r in conn.execute('PRAGMA foreign_key_check')],key=repr)
    return {'counts':counts,'foreign_key_violations':fk,'integrity_check':integrity}


def admin(conn,actor):
    row=conn.execute("SELECT id,role,status,locked_until FROM users WHERE id=?",(actor,)).fetchone()
    if not row or row['role']!='admin' or row['status']!='active': raise ImportFailure('ACTIVE_ADMIN_ACTOR_REQUIRED')
    if row['locked_until'] and datetime.fromisoformat(row['locked_until'])>datetime.now(timezone.utc):
        raise ImportFailure('ACTIVE_ADMIN_ACTOR_REQUIRED')


def exclusive_file(path):
    # Fail rather than overwrite any pre-existing snapshot/evidence, including links.
    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.close(fd)


def backup(source, target):
    target=Path(target)
    exclusive_file(target)
    with v.readonly_database(source) as origin:
        destination=sqlite3.connect(target)
        try:
            origin.backup(destination)
            # Only the newly created snapshot is normalized to a standalone DB.
            destination.execute('PRAGMA journal_mode=DELETE')
        finally:destination.close()
    with v.readonly_database(target) as snapshot: return state(snapshot)


def prepare(source,database):
    target=pilot_path(database,existing=False)
    with v.readonly_database(source) as conn: before=state(conn)
    target.parent.mkdir(parents=True,exist_ok=True)
    # Recheck links after creating directories.
    pilot_path(target,existing=False)
    after=backup(source,target)
    if before!=after: raise ImportFailure('SOURCE_CHANGED_DURING_PREPARE')
    return {'status':'PREPARED','schema_version':12,'source_hash':sha(source),'target_hash':sha(target),
        'real_model_calls':0,'business_signoff_status':'NOT RUN'}


class TransactionConnection:
    """Reuse service methods while their BEGIN requests join our one outer txn.

    Only this isolated tool receives the adapter. No global monkeypatch, service
    source rewrite or weakening of product validation takes place.
    """
    def __init__(self,conn,hook):self.conn,self.hook=conn,hook
    def execute(self,sql,params=()):
        normalized=' '.join(sql.upper().split())
        if normalized=='BEGIN IMMEDIATE':
            if not self.conn.in_transaction:raise ImportFailure('OUTER_TRANSACTION_REQUIRED')
            return self
        if normalized.startswith(('COMMIT','ROLLBACK','END','SAVEPOINT','RELEASE','BEGIN')):
            raise ImportFailure('NESTED_TRANSACTION_CONTROL_FORBIDDEN')
        result=self.conn.execute(sql,params)
        checkpoint=None
        if normalized.startswith('INSERT INTO ENABLEMENT_RESOURCES '):checkpoint='course_created'
        elif normalized.startswith('INSERT INTO ENABLEMENT_RESOURCE_VERSIONS '):checkpoint='resource_version'
        elif normalized.startswith('INSERT INTO ENABLEMENT_REVIEWS '):checkpoint='review_created'
        elif normalized.startswith('INSERT INTO CASE_SHARE_CONFIGS '):checkpoint='case_config'
        elif normalized.startswith('INSERT INTO CASE_SHARE_VERSIONS '):checkpoint='case_version'
        elif normalized.startswith('UPDATE ENABLEMENT_RESOURCES SET STATUS='):checkpoint='resource_published'
        elif normalized.startswith('UPDATE CASE_SHARE_CONFIGS SET STATUS='):checkpoint='case_published'
        if checkpoint:self.hook(checkpoint)
        return result
    def executemany(self,sql,params):
        result=self.conn.executemany(sql,params)
        if 'INSERT INTO resource_capability_map' in sql:self.hook('capability_map')
        return result


def transaction_service(conn,hook):
    adapter=TransactionConnection(conn,hook)
    @contextmanager
    def get_db():yield adapter
    namespace=dict(vars(service));namespace['get_db']=get_db
    # Functions retain their bytecode and all real product helpers and schemas.
    # Rebind only their module namespace so nested helpers use the same adapter.
    for name,fn in vars(service).items():
        if isinstance(fn,types.FunctionType) and fn.__module__==service.__name__:
            namespace[name]=types.FunctionType(fn.__code__,namespace,fn.__name__,fn.__defaults__,fn.__closure__)
    return types.SimpleNamespace(**namespace)


def create_only(conn,records):
    for rec in records:
        if rec.source_type!='case' and (rec.source_id is not None or rec.source_version is not None):
            raise ImportFailure('EXISTING_RESOURCE_UPDATE_NOT_SUPPORTED')
        if rec.source_type=='case':
            if rec.source_version is not None or conn.execute('SELECT case_id FROM case_share_configs WHERE case_id=?',(rec.source_id,)).fetchone():
                raise ImportFailure('CASE_SHARING_ALREADY_EXISTS_UPDATE_NOT_SUPPORTED')


def dry_run(manifest,database,package_id):
    package_identity(package_id);pilot_path(database)
    result=v.validate(manifest,database)
    if result['machine_status']=='PASS':
        _,records,_=v.load_package(manifest)
        with v.readonly_database(database) as conn:create_only(conn,records)
    return {'status':'VALID' if result['machine_status']=='PASS' else 'INVALID','validation':result,
        'business_signoff_status':'NOT RUN','real_model_calls':0}


def write_ledger(path,data):
    path=Path(path)
    pilot_path(path.parents[2]/'app.db')
    if any(p.is_symlink() for p in [path,*path.parents]):raise ImportFailure('SYMLINK_REJECTED')
    if path.exists():
        v.safe_path(path,path.parent)
        if v.read_json(path).get('transaction')!=data['transaction']: raise ImportFailure('LEDGER_FILE_CONFLICT')
        return
    temp=path.parent/('ledger-'+uuid.uuid4().hex+'.tmp')
    fd=os.open(temp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as stream:
        stream.write(json.dumps(data,ensure_ascii=False,indent=2)+'\n');stream.flush();os.fsync(stream.fileno())
    os.replace(temp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)


def postcheck(manifest,database,transaction,ledger_path):
    # A readonly connection rebinds only system-generated identities/audit from the
    # trusted DB ledger; business inputs remain byte-for-byte unchanged.
    result=v.validate(manifest,database,True,import_transaction=transaction)
    if result['machine_status']!='PASS': raise ImportFailure('POSTCOMMIT_VALIDATION_FAILED')
    with v.readonly_database(database) as conn:
        after=state(conn)
        if after['foreign_key_violations']!=transaction['before']['foreign_key_violations']:
            raise ImportFailure('POSTCOMMIT_FK_CHANGED')
    ledger={'transaction':transaction,'machine_import_status':'PASS','business_signoff_status':'NOT RUN',
        'postcommit_imported_validation':'PASS','postcommit_database_sha256':sha(database),'postcommit_database_files':database_hashes(database),
        'postcommit_state':after,'real_model_calls':0}
    write_ledger(ledger_path,ledger)
    return ledger


def apply(manifest,database,package_id,actor_user_id,*,_fault=None):
    """_fault is an internal test callback, never exposed as a CLI switch."""
    key=package_identity(package_id)
    path=pilot_path(database)
    if path.is_relative_to(Path(manifest).absolute().parent): raise ImportFailure('OUTPUT_INSIDE_INPUT_PACKAGE')
    identity=fingerprints(manifest)
    conn=None;committed=False;transaction=None
    # Cooperating executors serialize backup, DB commit and external ledger writing.
    with path.open('rb') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ImportFailure('PILOT_IMPORT_BUSY') from None
        inode=(path.stat().st_dev,path.stat().st_ino)
        try:
            conn=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=10,isolation_level=None)
            conn.row_factory=sqlite3.Row;conn.execute('PRAGMA foreign_keys=ON');schema(conn)
            conn.execute('BEGIN IMMEDIATE');admin(conn,actor_user_id)
            old=conn.execute('SELECT value FROM app_metadata WHERE key=?',(key,)).fetchone()
            ledger_path=path.parent/'imports'/package_id/'import-ledger.json'
            if old:
                transaction=json.loads(old[0])
                if transaction['package_sha256']!=identity['package_sha256']:raise ImportFailure('PACKAGE_ID_HASH_CONFLICT')
                conn.rollback();conn.close();conn=None
                postcheck(manifest,path,transaction,ledger_path)
                return {'status':'already_imported','import_id':transaction['import_id'],'ledger':str(ledger_path),
                    'business_signoff_status':'NOT RUN','real_model_calls':0}
            pre=v.validate(manifest,path)
            if pre['machine_status']!='PASS':raise ImportFailure('PACKAGE_PRECHECK_FAILED')
            model,records,_=v.load_package(manifest)
            if fingerprints(manifest)!=identity:raise ImportFailure('INPUT_PACKAGE_CHANGED')
            check=v.inspect_package(conn,model,records)
            if check['machine_status']!='PASS':raise ImportFailure('TRANSACTION_PRECHECK_FAILED')
            create_only(conn,records)
            before=state(conn)
            evidence_dir=ledger_path.parent
            if any(p.is_symlink() for p in [evidence_dir,*evidence_dir.parents]):raise ImportFailure('SYMLINK_REJECTED')
            evidence_dir.mkdir(parents=True,exist_ok=True)
            if any(p.is_symlink() for p in [evidence_dir,*evidence_dir.parents]):raise ImportFailure('SYMLINK_REJECTED')
            if ledger_path.exists():raise ImportFailure('ORPHAN_LEDGER_REQUIRES_REVIEW')
            import_id=uuid.uuid4().hex
            snapshot=evidence_dir/(import_id+'-before.sqlite')
            baseline_hash=sha(path);baseline_files=database_hashes(path)
            # A second readonly connection backs up the committed pre-state while
            # our write reservation prevents another writer changing that baseline.
            if backup(path,snapshot)!=before:raise ImportFailure('BACKUP_BASELINE_MISMATCH')
            def hook(stage):
                if _fault:_fault(stage,conn)
            svc=transaction_service(conn,hook)
            items=[]
            for i,record in enumerate(records):
                kind='case' if record.source_type=='case' else 'resource'
                source_id=record.source_id if kind=='case' else str(uuid.uuid4())
                save=service.ShareSave if kind=='case' else service.ResourceSave
                row=svc.save(kind,source_id,save(base_revision=0,metadata=record.metadata),actor_user_id)
                if record.source_type=='lab':hook('lab_import')
                permissions=record.permissions.model_copy(update={'base_revision':row['revision']})
                row=svc.permissions(kind,source_id,permissions,actor_user_id)
                review=record.review.model_copy(update={'base_revision':row['revision'],
                    'note':f'Pilot import {package_id}; original review evidence retained in import ledger'})
                row=svc.review(kind,source_id,review,actor_user_id)
                row=svc.publish(kind,source_id,service.Revision(base_revision=row['revision']),actor_user_id)
                actual=row['reviews'][0]
                items.append({'index':i,'source_type':record.source_type,'source_id':source_id,
                    'source_version':row['published_version'],'review_id':actual['id'],'reviewer_id':actual['reviewer_id'],
                    'reviewed_at':actual['reviewed_at'],'review':review.model_dump(),
                    'revision':row['revision'],'authorization_epoch':row['authorization_epoch'],
                    'permissions':{f:bool(row[f]) for f in v.FLAGS},
                    'capability_tag_ids':record.metadata['capability_tag_ids'],
                    'contributor_id':record.contributor_id,
                    'source_review_evidence':{'reviewer_id':record.reviewer_id,'reviewed_at':record.reviewed_at.isoformat(),'review':record.review.model_dump()}})
            hook('before_audit_ledger')
            if fingerprints(manifest)!=identity:raise ImportFailure('INPUT_PACKAGE_CHANGED')
            after=state(conn)
            if before['foreign_key_violations']!=after['foreign_key_violations']:raise ImportFailure('NEW_FK_ANOMALY')
            transaction={'package_id':package_id,**identity,'import_id':import_id,'actor_user_id':actor_user_id,
                'imported_at':now(),'database_identity':{'path':str(path),'device':inode[0],'inode':inode[1],'before_sha256':baseline_hash,'before_files':baseline_files},
                'snapshot':{'path':str(snapshot),'sha256':sha(snapshot)},'items':items,'before':before,
                'after':{**after,'counts':{**after['counts'],'app_metadata':after['counts']['app_metadata']+1}},
                'transaction_result':'COMMITTED','machine_import_status':'TRANSACTION_VALIDATED','business_signoff_status':'NOT RUN'}
            conn.execute('INSERT INTO app_metadata(key,value) VALUES (?,?)',(key,dump(transaction)))
            bound=bound_records(conn,manifest,records,transaction)
            checked=v.inspect_package(conn,model,bound,True)
            if checked['machine_status']!='PASS':raise ImportFailure('PRECOMMIT_IMPORTED_VALIDATION_FAILED')
            # No business data or half-ledger may survive failures up to this point.
            hook('before_commit')
            if fingerprints(manifest)!=identity:raise ImportFailure('INPUT_PACKAGE_CHANGED')
            if inode!=(path.stat().st_dev,path.stat().st_ino):raise ImportFailure('DATABASE_IDENTITY_CHANGED')
            conn.commit();committed=True;conn.close();conn=None
            postcheck(manifest,path,transaction,ledger_path)
            return {'status':'imported','import_id':import_id,'ledger':str(ledger_path),
                'machine_import_status':'PASS','business_signoff_status':'NOT RUN','real_model_calls':0}
        except Exception:
            if conn is not None:
                conn.rollback();conn.close()
            if committed:raise ImportFailure('COMMITTED_REQUIRES_LEDGER_RECOVERY_OR_POSTCHECK_REVIEW') from None
            raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='mode',required=True)
    p=sub.add_parser('prepare');p.add_argument('--source-db',type=Path,required=True);p.add_argument('--database',type=Path,required=True)
    for command in ('dry-run','apply'):
        p=sub.add_parser(command);p.add_argument('manifest',type=Path);p.add_argument('--database',type=Path,required=True)
        p.add_argument('--package-id',required=True)
        if command=='apply':p.add_argument('--actor-user-id',required=True)
    args=parser.parse_args()
    try:
        if args.mode=='prepare':result=prepare(args.source_db,args.database)
        elif args.mode=='dry-run':result=dry_run(args.manifest,args.database,args.package_id)
        else:result=apply(args.manifest,args.database,args.package_id,args.actor_user_id)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 2 if result['status']=='INVALID' else 0
    except Exception as exc:
        code=str(exc) if isinstance(exc,ImportFailure) else 'IMPORT_INPUT_OR_STORAGE_ERROR'
        print(json.dumps({'status':'INVALID' if args.mode=='dry-run' else 'FAILED','error_code':code,
            'machine_import_status':'FAIL','business_signoff_status':'NOT RUN','real_model_calls':0}))
        return 2

if __name__=='__main__':sys.exit(main())
