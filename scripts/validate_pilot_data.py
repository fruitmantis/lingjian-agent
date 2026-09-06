#!/usr/bin/env python3
"""Offline intake checks. No API login, model request, import or database write.

Run with the worktree's Python environment. PASS means structural checks only;
real provenance, suitability and permission attestations still require humans.
"""
import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi import HTTPException
from pydantic import Field, ValidationError
from backend.app.enablement import (StrictModel, ResourceMetadata, ShareMetadata,
    Permissions, Review, check_case, check_tags, resolve_reference, row_for)
from backend.app.development_types import DevelopmentRequest
from backend.app.development_lifecycle import clarify
from backend.app.development_engine import request_projection, guard, blocked_fragments, constraint_state, candidates

STABLE = Path('/home/yuan/project/lingjian-agent')
CANARY = 'INTERNAL_SECRET_PHASE_B_DO_NOT_SHARE'
FLAGS = ('system_visible', 'model_allowed', 'partner_allowed')
MARKERS = re.compile(r'synthetic|fixture|example\.(?:com|org|net)|验证伙伴|A-ready|INTERNAL_SECRET_|合成(?:课程|实验|案例|伙伴|数据)|测试(?:课程|实验|案例|伙伴)|占位|待填写', re.I)
SECRETS = re.compile(r'Bearer\s+|\bsk-[A-Za-z0-9_-]{12,}|(?:api[_-]?key|access[_-]?token|cookie|session|password)\s*[:=]\s*\S+', re.I)

class Gap(StrictModel):
    capability_tag_id: str = Field(min_length=1)
    source_type: Literal['course', 'lab', 'case']
    detail: str = Field(min_length=1)

class Gaps(StrictModel):
    reviewed: bool
    items: list[Gap]
    no_known_gaps_reason: str

class Manifest(StrictModel):
    package_kind: Literal['real', 'synthetic', 'template']
    target_partner_name: str = Field(min_length=1)
    allowed_diagnostic_scope: list[str] = Field(min_length=1)
    request: DevelopmentRequest
    resources: list[str]
    shared_cases: list[str]
    resource_gaps: Gaps

class Record(StrictModel):
    source_type: Literal['course', 'lab', 'case']
    source_id: str | None
    source_version: int | None = Field(ge=1)
    contributor_id: str | None
    status: Literal['published']
    metadata: dict
    permissions: Permissions
    review: Review
    reviewer_id: str = Field(min_length=1)
    reviewed_at: datetime


def digest(value):
    return hashlib.sha256(value).hexdigest()


def no_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value: raise ValueError('DUPLICATE_JSON_KEY')
        value[key] = item
    return value


def read_json(path):
    if path.stat().st_size > 4_000_000: raise ValueError('INPUT_TOO_LARGE')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=no_duplicate_keys)


def safe_path(path, root):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in [path, *path.parents]): raise ValueError('SYMLINK_REJECTED')
    if not path.resolve().is_relative_to(root.resolve()): raise ValueError('PATH_OUTSIDE_PACKAGE')
    if not path.is_file() or path.stat().st_nlink != 1: raise ValueError('REGULAR_PRIVATE_FILE_REQUIRED')
    return path


@contextmanager
def readonly_database(path):
    path = Path(path).absolute()
    if path.resolve().is_relative_to(STABLE): raise ValueError('STABLE_DATABASE_FORBIDDEN')
    if not any(path.resolve().is_relative_to(p) for p in (ROOT, Path('/tmp'))):
        raise ValueError('INDEPENDENT_DATABASE_REQUIRED')
    safe_path(path, path.parent)
    conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        version = conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()
        if not version or version[0] != '12': raise ValueError('EXPECTED_SCHEMA_12')
        yield conn
    finally:
        conn.close()


def load_package(manifest_path):
    path = safe_path(Path(manifest_path), Path(manifest_path).absolute().parent)
    raw = read_json(path)
    if not isinstance(raw.get('request'), dict) or set(raw['request']) != set(DevelopmentRequest.model_fields):
        raise ValueError('EXPLICIT_PRODUCT_FIELDS_REQUIRED')
    manifest = Manifest.model_validate(raw, strict=True)
    files = {path.name: digest(path.read_bytes())}
    records = []
    seen = set()
    for kind, names in [('resource', manifest.resources), ('case', manifest.shared_cases)]:
        for name in names:
            child = safe_path(path.parent / name, path.parent)
            if child.suffix != '.json' or child == path or child in seen: raise ValueError('DUPLICATE_OR_INVALID_RECORD_FILE')
            seen.add(child)
            entry = read_json(child)
            # Exact model fields are required even when product schema has UI defaults.
            cls = ShareMetadata if kind == 'case' else ResourceMetadata
            for key, model in [('metadata', cls), ('permissions', Permissions), ('review', Review)]:
                if not isinstance(entry.get(key), dict) or set(entry[key]) != set(model.model_fields):
                    raise ValueError('EXPLICIT_PRODUCT_FIELDS_REQUIRED')
            cls.model_validate(entry['metadata'], strict=True)
            # JSON timestamps are explicitly parsed; no numeric or boolean coercion.
            date = entry.get('reviewed_at')
            if not isinstance(date, str): raise ValueError('REVIEW_TIMESTAMP_REQUIRED')
            record = Record.model_validate({**entry, 'reviewed_at': datetime.fromisoformat(date.replace('Z', '+00:00'))}, strict=True)
            if (record.source_type == 'case') != (kind == 'case'): raise ValueError('RECORD_TYPE_MISMATCH')
            if kind == 'resource' and record.source_type != record.metadata['resource_type']: raise ValueError('RECORD_TYPE_MISMATCH')
            records.append(record)
            files[name] = digest(child.read_bytes())
    fingerprint = digest(json.dumps(files, sort_keys=True, separators=(',', ':')).encode())
    return manifest, records, fingerprint


def inspect_package(conn, manifest, records, imported=False):
    errors, warnings = [], []
    def error(code, location='package'): errors.append({'code': code, 'location': location})
    def marker(value, location):
        text = json.dumps(value, ensure_ascii=False, default=str)
        if MARKERS.search(text): error('TEST_DATA_FORBIDDEN', location)
        if SECRETS.search(text): error('CREDENTIAL_LIKE_CONTENT_FORBIDDEN', location)
    marker(manifest.model_dump(), 'manifest')
    if manifest.package_kind != 'real': error('REAL_PACKAGE_REQUIRED')
    if not all(s.strip() for s in manifest.allowed_diagnostic_scope): error('DIAGNOSTIC_SCOPE_REQUIRED')
    request = manifest.request.model_dump()
    partner = conn.execute('SELECT id,name,status FROM partners WHERE id=?', (request['target_partner_id'],)).fetchone()
    if not partner or partner['status'] != 'active': error('INVALID_TARGET_PARTNER')
    elif partner['name'] != manifest.target_partner_name: error('PARTNER_NAME_MISMATCH')
    else: marker(partner['name'], 'target_partner')
    try:
        clarified = clarify(manifest.request)
        # model_input_allowed is a separate gate, not mandatory for system-only intake.
        missing = [f for f in clarified['missing_fields'] if f != 'model_input_allowed']
        if missing: error('REQUEST_CLARIFICATION_REQUIRED')
        else: request = clarified['request']
    except HTTPException: error('INVALID_REQUEST_CONSTRAINTS')
    tags = [t['capability_tag_id'] for t in request['targets']]
    try: check_tags(conn, tags, required=True)
    except HTTPException: error('INVALID_TARGET_CAPABILITY_TAG')
    if request['source_task_id']:
        # This offline tool cannot infer ownership of a business task; no extra context intake.
        error('SOURCE_TASK_REQUIRES_AUTHENTICATED_CONTEXT_CHECK')
    if request['source_case_id']:
        try: resolve_reference(conn, 'case', request['source_case_id'], request['source_case_version'], 'system')
        except HTTPException: error('INVALID_REQUEST_CASE_REFERENCE')
    projection = request_projection(request)
    blocked = blocked_fragments(conn)
    projection_ok = True
    projected_items = []
    try: guard(projection, blocked)
    except ValueError:
        projection_ok = False
        error('UNSAFE_REQUEST_MODEL_PROJECTION')
    sets = {'system': [], 'model': [], 'partner': []}
    coverage = {p: {tag: set() for tag in tags} for p in sets}
    identities = set()
    for index, rec in enumerate(records):
        loc = f'record[{index}]'
        start = len(errors)
        marker(rec.model_dump(mode='json'), loc)
        try: guard(rec.metadata, blocked, allow_urls=True)
        except ValueError: error('INTERNAL_CONTENT_IN_RESOURCE_METADATA', loc)
        if rec.reviewed_at.tzinfo is None or rec.reviewed_at > datetime.now(timezone.utc): error('INVALID_REVIEW_TIME', loc)
        if rec.review.link_status != 'available' or not rec.review.content_checked or not rec.review.authorization_checked:
            error('INCOMPLETE_HUMAN_REVIEW', loc)
        if rec.review.base_revision != rec.permissions.base_revision: error('REVIEW_REVISION_MISMATCH', loc)
        reviewer = conn.execute("SELECT id FROM users WHERE id=? AND role='admin' AND status='active'", (rec.reviewer_id,)).fetchone()
        if not reviewer: error('INVALID_REVIEWER', loc)
        try: check_tags(conn, rec.metadata['capability_tag_ids'], required=True)
        except HTTPException: error('INVALID_RESOURCE_CAPABILITY_TAG', loc)
        if rec.source_type == 'case':
            try:
                owner = check_case(conn, rec.source_id)
                if owner['id'] != rec.contributor_id: error('CASE_OWNER_MISMATCH', loc)
                marker(owner['name'], loc)
            except HTTPException: error('INVALID_OR_ORPHAN_CASE', loc)
        elif rec.contributor_id is not None: error('RESOURCE_HAS_NO_CONTRIBUTOR_FIELD', loc)
        if rec.source_id:
            identity = (rec.source_type == 'case', rec.source_id)
            if identity in identities: error('DUPLICATE_SOURCE_ID', loc)
            identities.add(identity)
        if rec.source_type != 'case' and rec.source_id and not conn.execute('SELECT id FROM enablement_resources WHERE id=?', (rec.source_id,)).fetchone():
            error('INVALID_EXISTING_RESOURCE_ID', loc)
        flags = rec.permissions.model_dump(include=set(FLAGS))
        if not flags['system_visible']: warnings.append({'code': 'NOT_SYSTEM_VISIBLE', 'location': loc})
        if not flags['model_allowed']: warnings.append({'code': 'EXCLUDED_FROM_MODEL', 'location': loc})
        if not flags['partner_allowed']: warnings.append({'code': 'EXCLUDED_FROM_PARTNER', 'location': loc})
        unknown = [k for k, v in rec.metadata.items() if v in (None, '', '未知', 'unknown')]
        if unknown: warnings.append({'code': 'UNKNOWN_PRESERVED', 'location': loc, 'fields': unknown})
        if imported:
            kind = 'case' if rec.source_type == 'case' else 'resource'
            table = 'case_share_versions' if kind == 'case' else 'enablement_resource_versions'
            if not rec.source_id or rec.source_version is None:
                error('IMPORTED_REFERENCE_REQUIRED', loc)
            else:
                try:
                    try:
                        resolve_reference(conn, rec.source_type, rec.source_id, rec.source_version, 'system')
                    except HTTPException as exc:
                        # Admin import evidence can include hidden resources. The product
                        # resolver has already checked publication, version, owner and epoch
                        # before denying system visibility; never grant public access here.
                        if exc.status_code != 403 or flags['system_visible']: raise
                    if kind == 'resource':
                        mapped = {r[0] for r in conn.execute('SELECT capability_tag_id FROM resource_capability_map WHERE resource_id=?',(rec.source_id,))}
                        if mapped != set(rec.metadata['capability_tag_ids']): error('IMPORTED_CAPABILITY_MAP_MISMATCH',loc)
                    head = row_for(conn, kind, rec.source_id)
                    if any(bool(head[f]) != flags[f] for f in FLAGS): error('IMPORTED_CURRENT_PERMISSIONS_MISMATCH', loc)
                    stored = conn.execute(f'SELECT * FROM {table} WHERE source_id=? AND version=?', (rec.source_id, rec.source_version)).fetchone()
                    payload = json.loads(stored['payload_json'])
                    if {k: payload.get(k) for k in rec.metadata} != rec.metadata or payload.get('_permissions') != flags:
                        error('IMPORTED_SNAPSHOT_MISMATCH', loc)
                    review = conn.execute('SELECT * FROM enablement_reviews WHERE source_kind=? AND source_id=? AND revision=? ORDER BY reviewed_at DESC LIMIT 1',
                        (kind, rec.source_id, stored['reviewed_revision'])).fetchone()
                    if not review or any(review[k] != v for k, v in {
                        'reviewer_id': rec.reviewer_id, 'revision': rec.review.base_revision,
                        'link_status': rec.review.link_status, 'content_checked': int(rec.review.content_checked),
                        'authorization_checked': int(rec.review.authorization_checked), 'note': rec.review.note}.items()):
                        error('IMPORTED_REVIEW_MISMATCH', loc)
                    elif datetime.fromisoformat(review['reviewed_at']) != rec.reviewed_at: error('IMPORTED_REVIEW_TIME_MISMATCH', loc)
                except (HTTPException, TypeError, KeyError): error('IMPORTED_REFERENCE_UNAVAILABLE', loc)
        for purpose in sets:
            allowed = flags['system_visible'] and (purpose == 'system' or flags['model_allowed' if purpose == 'model' else 'partner_allowed'])
            if not allowed: continue
            if purpose == 'model':
                # Reuse the actual product whitelist; URLs, review notes and internal evidence are excluded.
                if imported and rec.source_id and rec.source_version:
                    try: item = resolve_reference(conn, rec.source_type, rec.source_id, rec.source_version, 'model')
                    except HTTPException:
                        error('MODEL_REFERENCE_NOT_CURRENTLY_AUTHORIZED', loc); continue
                else:
                    item = {k: v for k, v in rec.metadata.items() if k != 'source_url'}
                try: guard(item, blocked)
                except ValueError:
                    projection_ok = False
                    error('UNSAFE_RESOURCE_MODEL_PROJECTION', loc); continue
                projected_items.append(item)
                condition = constraint_state(item, request)
                if condition['state'] == 'conflicts':
                    warnings.append({'code': 'MODEL_CONSTRAINT_CONFLICT', 'location': loc}); continue
                if condition['state'] == 'unknown': warnings.append({'code': 'MODEL_CONSTRAINT_UNKNOWN', 'location': loc})
            if imported and purpose == 'partner':
                try: resolve_reference(conn, rec.source_type, rec.source_id, rec.source_version, 'partner')
                except HTTPException:
                    error('PARTNER_REFERENCE_NOT_CURRENTLY_AUTHORIZED', loc); continue
            if len(errors) == start:
                sets[purpose].append(index)
                for tag in set(tags).intersection(rec.metadata['capability_tag_ids']): coverage[purpose][tag].add(rec.source_type)
    complete = {p: [tag for tag, types in cov.items() if types == {'course','lab','case'}] for p, cov in coverage.items()}
    if not complete['system']: error('REAL_RESOURCE_PATH_INCOMPLETE')
    gaps = manifest.resource_gaps
    if not gaps.reviewed or (not gaps.items and not gaps.no_known_gaps_reason.strip()): error('RESOURCE_GAPS_NOT_REVIEWED')
    for gap in gaps.items:
        if gap.capability_tag_id not in tags: error('GAP_OUTSIDE_TARGETS')
    for tag, types in coverage['system'].items():
        for missing in {'course', 'lab', 'case'} - types:
            if not any(g.capability_tag_id == tag and g.source_type == missing for g in gaps.items): error('UNREGISTERED_RESOURCE_GAP')
    model_pool_scoped = False
    if imported and not errors:
        actual_candidates = candidates(conn, request, [{'capability_tag_id': t, 'problem_type':'trainable_gap'} for t in tags])
        approved = {(r.source_type,r.source_id,r.source_version) for r in records if r.permissions.model_allowed}
        model_pool_scoped = all((r['source_type'],r['source_id'],r['source_version']) in approved for r in actual_candidates)
    return {'machine_status': 'FAIL' if errors else 'PASS', 'mode': 'imported' if imported else 'intake',
        'errors': errors, 'warnings': warnings, 'eligible_record_indexes': sets,
        'complete_path_counts': {p: len(v) for p, v in complete.items()},
        'model_projection_sha256': digest(json.dumps({'request':projection,'resources':projected_items},sort_keys=True,ensure_ascii=False).encode()),
        'model_pool_scoped': model_pool_scoped, 'model_projection_safe': projection_ok, 'model_input_allowed': request['model_input_allowed'],
        'DATA_01_business_signoff': 'NOT RUN', 'DATA_02': 'BLOCKED', 'real_model_calls': 0,
        'authenticity': 'Machine checks do not establish real provenance or business suitability'}


def validate(manifest_path, database, imported=False, *, import_ledger=None, import_transaction=None):
    try:
        manifest, records, fingerprint = load_package(manifest_path)
        with readonly_database(database) as conn:
            if import_ledger is not None:
                ledger_path = safe_path(import_ledger, Path(database).absolute().parent / 'imports')
                import_transaction = read_json(ledger_path)['transaction']
            if import_transaction is not None:
                if not imported: raise ValueError('IMPORTED_MODE_REQUIRED')
                from scripts.pilot_import_contract import bound_records
                records = bound_records(conn, manifest_path, records, import_transaction)
            result = inspect_package(conn, manifest, records, imported)
        result['package_sha256'] = import_transaction['package_sha256'] if import_transaction is not None else fingerprint
        if import_transaction is not None: result['input_manifest_files_sha256'] = fingerprint
        return result
    except ValidationError as exc:
        known = set(Manifest.model_fields) | set(Record.model_fields) | set(ResourceMetadata.model_fields) | set(ShareMetadata.model_fields) | set(DevelopmentRequest.model_fields) | set(Permissions.model_fields) | set(Review.model_fields)
        issues = [{'code': 'SCHEMA_' + e['type'].upper(), 'location': '.'.join(str(x) if isinstance(x,int) or x in known else 'unrecognized_field' for x in e['loc'])} for e in exc.errors(include_input=False,include_context=False)]
        return {'machine_status':'FAIL','mode':'imported' if imported else 'intake','errors':issues,
            'DATA_01_business_signoff':'NOT RUN','DATA_02':'BLOCKED','real_model_calls':0}
    except (ValueError, OSError, sqlite3.Error, TypeError, KeyError) as exc:
        # Never echo raw validation inputs, SQLite errors, paths or exception stacks.
        allowed = {'DUPLICATE_JSON_KEY','PATH_OUTSIDE_PACKAGE','SYMLINK_REJECTED','REGULAR_PRIVATE_FILE_REQUIRED',
            'STABLE_DATABASE_FORBIDDEN','INDEPENDENT_DATABASE_REQUIRED','EXPECTED_SCHEMA_12',
            'EXPLICIT_PRODUCT_FIELDS_REQUIRED','REVIEW_TIMESTAMP_REQUIRED','RECORD_TYPE_MISMATCH',
            'DUPLICATE_OR_INVALID_RECORD_FILE','INPUT_TOO_LARGE','IMPORTED_MODE_REQUIRED','UNTRUSTED_IMPORT_LEDGER',
            'INPUT_PACKAGE_CHANGED','LEDGER_RECORD_COUNT_MISMATCH','LEDGER_RECORD_MISMATCH','LEDGER_CASE_MISMATCH'}
        code = str(exc) if type(exc) is ValueError and str(exc) in allowed else 'INPUT_OR_DATABASE_INVALID'
        return {'machine_status':'FAIL','mode':'imported' if imported else 'intake','errors':[{'code':code,'location':'input'}],
            'DATA_01_business_signoff':'NOT RUN','DATA_02':'BLOCKED','real_model_calls':0}


def real_model_precheck(result, database, receipt_path=None):
    """Evidence gate only. Even PASS never performs or authorizes a network call."""
    checks = {'worktree_clean': not subprocess.check_output(['git','-C',str(ROOT),'status','--porcelain'], text=True).strip(),
        'imported_machine_pass': result.get('machine_status') == 'PASS' and result.get('mode') == 'imported',
        'model_path_complete': result.get('complete_path_counts',{}).get('model',0) > 0,
        'safe_projection': result.get('model_projection_safe',False),
        'model_pool_within_approved_package':result.get('model_pool_scoped',False),
        'request_model_permission': result.get('model_input_allowed',False),
        'explicit_user_authorization':False, 'business_data_authorization':False,
        'explicit_approved_test_model':False,'budget_and_audit_ready':False,
        'independent_database':False,'unapproved_attachments_excluded':False}
    try:
        with readonly_database(database) as conn:
            checks['independent_database'] = True
            if receipt_path:
                # Receipt is private local evidence. No credentials are read or emitted.
                receipt = read_json(safe_path(receipt_path, ROOT / '.isolation'))
                matches = receipt['package_sha256'] == result.get('package_sha256')
                def evidence(key):
                    entry = receipt[key]
                    file = safe_path(ROOT / '.isolation' / entry['path'], ROOT / '.isolation')
                    if digest(file.read_bytes()) != entry['sha256']: raise ValueError('EVIDENCE_HASH_MISMATCH')
                    return file
                expires = datetime.fromisoformat(receipt['expires_at'].replace('Z','+00:00'))
                valid = matches and expires.tzinfo is not None and expires > datetime.now(timezone.utc)
                user = read_json(evidence('user_authorization'))
                business = read_json(evidence('business_signoff'))
                def signed(doc):
                    stamp = datetime.fromisoformat(doc['signed_at'].replace('Z','+00:00'))
                    return doc.get('approved') is True and bool(doc.get('signed_by','').strip()) and stamp.tzinfo is not None and stamp <= datetime.now(timezone.utc) and doc.get('package_sha256') == result.get('package_sha256')
                checks['explicit_user_authorization'] = bool(valid and signed(user) and user.get('scope') == 'real_model_test'
                    and user.get('model') == receipt['model'] and user.get('provider_base_url') == receipt['provider_base_url']
                    and user.get('max_calls') == receipt['max_calls'])
                checks['business_data_authorization'] = bool(valid and signed(business) and business.get('scope') == 'data_for_model_test'
                    and business.get('model_projection_sha256') == result.get('model_projection_sha256'))
                selected = conn.execute("SELECT model_config_id FROM model_usage_configs WHERE scene_key='partner_development'").fetchone()
                config = conn.execute('SELECT id,enabled,model_name,base_url FROM model_configs WHERE id=?', (receipt['approved_test_config_id'],)).fetchone()
                checks['explicit_approved_test_model'] = bool(valid and config and config['enabled'] and selected and selected[0] == config['id']
                    and config['model_name'] == receipt['model'] and config['base_url'] == receipt['provider_base_url'])
                audit = read_json(evidence('budget_audit_mock_test'))
                runner = evidence('audit_runner')
                checks['budget_and_audit_ready'] = bool(valid and type(receipt['max_calls']) is int and 0 < receipt['max_calls'] <= 16
                    and audit.get('status') == 'PASS' and audit.get('real_model_calls') == 0
                    and audit.get('runner_sha256') == digest(runner.read_bytes())
                    and audit.get('budget_exhaustion_blocks') is True and audit.get('failed_calls_counted') is True
                    and audit.get('canary_blocked') is True and audit.get('audit_fields_complete') is True)
                checks['unapproved_attachments_excluded'] = valid and receipt['attachments_allowed'] is False
    except (ValueError, OSError, sqlite3.Error, KeyError, TypeError): pass
    return {'status': 'PASS' if all(checks.values()) else 'BLOCKED', 'checks': checks, 'real_model_calls': 0,
        'authorization_note': 'Receipt integrity is checked; a human must attest that approvals and audit runner evidence are authentic. This command never calls a model.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--database', required=True, type=Path)
    parser.add_argument('--imported', action='store_true')
    parser.add_argument('--import-ledger', type=Path, help='Bind immutable input to actual IDs and audit from the trusted DB import ledger')
    parser.add_argument('--real-model-precheck', action='store_true')
    parser.add_argument('--authorization-receipt', type=Path)
    args = parser.parse_args()
    result = validate(args.manifest, args.database, args.imported, import_ledger=args.import_ledger)
    if args.real_model_precheck:
        result['real_model_precheck'] = real_model_precheck(result, args.database, args.authorization_receipt)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['machine_status'] == 'PASS' and result.get('real_model_precheck',{}).get('status','PASS') == 'PASS' else 2

if __name__ == '__main__': sys.exit(main())
