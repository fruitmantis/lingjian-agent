"""Private import evidence contract. No new product tables or network operations."""
import json
import re
from datetime import datetime
from pathlib import Path

PREFIX = 'pilot_import:'


def package_identity(package_id):
    if not isinstance(package_id,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', package_id):
        raise ValueError('INVALID_PACKAGE_ID')
    return PREFIX + package_id


def fingerprints(manifest_path):
    from scripts import validate_pilot_data as v
    manifest = v.safe_path(manifest_path, Path(manifest_path).absolute().parent)
    files = {}
    # Cover signoff and every other input evidence file, not just referenced JSON.
    # Outputs must live in the pilot DB directory, never inside this immutable package.
    for path in sorted(manifest.parent.rglob('*')):
        if path.is_symlink(): raise ValueError('SYMLINK_REJECTED')
        if path.is_file():
            v.safe_path(path, manifest.parent)
            files[str(path.relative_to(manifest.parent))] = v.digest(path.read_bytes())
    return {'package_sha256':v.digest(json.dumps(files,sort_keys=True,separators=(',',':')).encode()),
        'manifest_sha256':v.digest(manifest.read_bytes()),'input_files':files}


def bound_records(conn, manifest_path, records, transaction):
    """Resolve immutable inputs through a DB-authenticated transaction ledger."""
    from scripts import validate_pilot_data as v
    stored = conn.execute('SELECT value FROM app_metadata WHERE key=?', (package_identity(transaction['package_id']),)).fetchone()
    if not stored or json.loads(stored[0]) != transaction: raise ValueError('UNTRUSTED_IMPORT_LEDGER')
    identity = fingerprints(manifest_path)
    if any(transaction[k] != identity[k] for k in identity): raise ValueError('INPUT_PACKAGE_CHANGED')
    items=transaction['items']
    if len(items)!=len(records): raise ValueError('LEDGER_RECORD_COUNT_MISMATCH')
    result=[]
    for i,(record,item) in enumerate(zip(records,items)):
        if item['index']!=i or item['source_type']!=record.source_type: raise ValueError('LEDGER_RECORD_MISMATCH')
        if record.source_type=='case' and item['source_id']!=record.source_id: raise ValueError('LEDGER_CASE_MISMATCH')
        result.append(record.model_copy(update={'source_id':item['source_id'],'source_version':item['source_version'],
            'permissions':record.permissions.model_copy(update={'base_revision':item['review']['base_revision']}),
            'review':v.Review.model_validate(item['review'],strict=True),
            'reviewer_id':item['reviewer_id'],'reviewed_at':datetime.fromisoformat(item['reviewed_at'])}))
    return result
