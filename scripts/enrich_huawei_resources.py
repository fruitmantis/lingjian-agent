"""Enrich the existing Huawei import from signed-in detail captures; preview by default."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import import_huawei_resources as importer
from backend.app import enablement as service
from backend.app.database import get_db, get_readonly_db


def referenced_ids(conn, identifiers):
    """Do not supersede a version already captured in a plan or a running request."""
    found = set()
    def walk(value):
        if isinstance(value, str):
            if value in identifiers: found.add(value)
        elif isinstance(value, dict):
            for child in value.values(): walk(child)
        elif isinstance(value, list):
            for child in value: walk(child)
    for table, columns in (
        ('development_requests', 'payload_json'),
        ('development_runs', 'input_snapshot'),
        ('development_versions', 'payload_json,dependency_json'),
        ('development_version_items', 'payload_json'),
    ):
        for row in conn.execute(f'SELECT {columns} FROM {table}'):
            for raw in row: walk(json.loads(raw))
    return found


def clean_details(details, kind):
    fields = ['title', 'summary'] + (['course_goals', 'audience', 'outline', 'cover_url']
                                    if kind == 'course' else ['lab_goals', 'lab_requirements'])
    result = {field: importer.plain(details[field]) for field in fields if details.get(field)}
    if result.get('cover_url'):
        url = urlsplit(result['cover_url'])
        if (url.scheme != 'https' or url.hostname not in ('edu-res.hc-cdn.cn', 'communityfile.developer.myhuaweicloud.com')
                or url.query or url.fragment or url.username or url.password):
            raise ValueError('Unexpected cover URL')
    if details.get('duration_minutes') is not None:
        result['duration_minutes'] = details['duration_minutes']
    return result


def plan_enrichment(conn, manifest, capture):
    originals = {r['resource_id']: r for r in manifest['resources']}
    details = {r['resource_id']: r for r in capture['resources']}
    if len(originals) != len(manifest['resources']) or len(details) != len(capture['resources']):
        raise ValueError('Duplicate resource identifiers')
    if set(details) - set(originals): raise ValueError('Capture is outside the original import')
    refs = referenced_ids(conn, set(originals))
    result = []
    for sid, original in originals.items():
        record = {'resource_id': sid, 'resource_type': original['metadata']['resource_type'],
                  'action': 'unavailable', 'changed_fields': [], 'protected_fields': [], 'notes': []}
        detail = details.get(sid)
        if not detail or detail['status'] != 'ok':
            result.append(record); continue
        kind = record['resource_type']
        identity, canonical = importer.source_identity(detail['source_url'], detail['resource_type'])
        original_identity, original_url = importer.source_identity(original['metadata']['source_url'], kind)
        if (detail['resource_type'] != kind or identity != original_identity or canonical != original_url
                or detail['source_url'] != canonical):
            raise ValueError('Source mismatch')
        row = conn.execute('SELECT * FROM enablement_resources WHERE id=?', (sid,)).fetchone()
        if row is None: raise ValueError('Original resource no longer exists')
        current = service.resource_metadata(json.loads(row['draft_json']))
        if current['source_url'] != original_url or current['resource_type'] != kind:
            record.update(action='protected', notes=['administrator_changed_source'])
            result.append(record); continue
        if row['status'] in ('unpublished', 'revoked'):
            record.update(action='protected', notes=['administrator_unpublished'])
            result.append(record); continue
        candidate = dict(current)
        for field, value in clean_details(detail['details'], kind).items():
            if current[field] == value: continue
            if current[field] != original['metadata'][field]:
                record['protected_fields'].append(field)
            else:
                candidate[field] = value
                record['changed_fields'].append(field)
        candidate = service.ResourceMetadata.model_validate(candidate).model_dump()
        record.update(metadata=candidate, base_revision=row['revision'])
        if not record['changed_fields']:
            record['action'] = 'unchanged'
            result.append(record); continue
        if sid in refs: record['notes'].append('historical_or_running_reference')
        if row['published_version']:
            published = conn.execute('SELECT payload_json FROM enablement_resource_versions WHERE source_id=? AND version=?',
                                     (sid, row['published_version'])).fetchone()
            if service.resource_metadata(json.loads(published[0])) != current:
                record['notes'].append('pending_administrator_draft')
        elif (original['action'] != 'draft' or not original['issues']
              or set(original['issues']) - {'source_title_conflict'}
              or current != original['metadata']):
            record['notes'].append('unresolved_original_draft')
        # Signed-in official detail resolves only a catalog title conflict, not level or availability.
        if not candidate['level']: record['notes'].append('missing_level')
        record['action'] = 'draft' if record['notes'] else 'publish'
        result.append(record)
    return result


def apply_enrichment(manifest, capture, actor):
    with get_db() as conn:
        conn.lock_writer()
        if not conn.execute("SELECT id FROM users WHERE id=? AND role='admin' AND status='active'", (actor,)).fetchone():
            raise ValueError('An active administrator is required')
        plan = plan_enrichment(conn, manifest, capture)
        for record in plan:
            if record['action'] not in ('publish', 'draft'): continue
            sid = record['resource_id']
            row = service.save('resource', sid, service.ResourceSave(base_revision=record['base_revision'],
                               metadata=record['metadata']), actor, connection=conn)
            if record['action'] == 'publish':
                row = service.publish('resource', sid, service.Revision(base_revision=row['revision']), actor, connection=conn)
            service.audit(conn, 'resource', sid, 'enrich', actor, row,
                          'Huawei detail: ' + ','.join(record['changed_fields']))
        return plan


def summary(plan):
    return {kind: dict(Counter(r['action'] for r in plan if r['resource_type'] == kind))
            for kind in ('course', 'lab')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--config', type=Path, default=ROOT / '.isolation/runtime/dev/environment.json')
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--actor')
    parser.add_argument('--backup-dir', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    config = json.loads(args.config.read_text())
    os.environ['DATABASE_URL'] = config['DATABASE_URL']
    from sqlalchemy.engine import make_url
    url = make_url(os.environ['DATABASE_URL'])
    if (not url.drivername.startswith('postgresql') or url.database != 'banfei_agent'
            or url.host not in ('localhost', '127.0.0.1') or url.query):
        raise ValueError('Only local runtime banfei_agent with its default schema is allowed')
    manifest = json.loads(args.manifest.read_text())
    capture = json.loads(args.capture.read_text())
    with get_readonly_db() as conn:
        if conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] != '16':
            raise ValueError('Expected existing schema 16')
        plan = plan_enrichment(conn, manifest, capture)
        admins = [r[0] for r in conn.execute("SELECT id FROM users WHERE role='admin' AND status='active'")]
    if args.apply:
        if args.actor not in admins: raise ValueError('Specify an existing active administrator')
        if not args.backup_dir: raise ValueError('--backup-dir is required')
        args.backup_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
        env = dict(os.environ, PGHOST=url.host, PGPORT=str(url.port or 5432), PGDATABASE=url.database,
                   PGUSER=url.username or '', PGPASSWORD=url.password or '')
        with (args.backup_dir / 'before.pgdump').open('xb') as output:
            subprocess.run(['pg_dump', '--format=custom', '--no-owner', '--no-acl'], env=env,
                           stdout=output, stderr=subprocess.PIPE, check=True)
        plan = apply_enrichment(manifest, capture, args.actor)
    report = {'applied': args.apply, 'time': datetime.now(timezone.utc).isoformat(),
              'summary': summary(plan), 'resources': plan}
    args.report.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'applied': args.apply, **summary(plan)}, ensure_ascii=False))


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('Enrichment failed: ' + type(error).__name__ + '; inspect private source/configuration.', file=sys.stderr)
        sys.exit(1)
