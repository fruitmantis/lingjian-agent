"""Preview or transactionally add public Huawei courses/labs, preserving existing data."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app import enablement as service, resource_categories as categories
from backend.app.database import get_db, get_readonly_db


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts = []; self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'): self.hidden += 1
        if tag in ('p', 'br', 'li', 'div'): self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'): self.hidden = max(0, self.hidden - 1)
        if tag in ('p', 'li', 'div'): self.parts.append('\n')

    def handle_data(self, value):
        if not self.hidden: self.parts.append(value)


def plain(value):
    if not isinstance(value, str): raise ValueError('Expected source text')
    parser = PlainText(); parser.feed(unescape(value)); parser.close()
    return '\n'.join(line for part in ''.join(parser.parts).splitlines()
                     if (line := re.sub(r'\s+', ' ', part).strip()))


def source_identity(url, kind):
    """Deduplicate official resource identifiers, retaining meaningful course IDs."""
    service.ResourceMetadata.check_url(url)
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.port not in (None, 443): raise ValueError('Unexpected source URL')
    pathname = unquote(parsed.path).rstrip('/')
    if kind == 'course' and parsed.hostname == 'connect.huaweicloud.com':
        match = re.fullmatch(r'/courses/learn/([^/?#]+)/about', pathname)
    elif kind == 'lab' and parsed.hostname == 'edu.huaweicloud.com':
        match = re.fullmatch(r'/lab/experiment-detail_(\d+)', pathname)
    else:
        match = None
    if not match: raise ValueError('Not an official course/lab detail URL')
    return kind + ':' + match[1], 'https://' + parsed.hostname + pathname


LEVELS = {'基础': 'basic', '初级': 'basic', '进阶': 'advanced', '中级': 'advanced', '高级': 'advanced'}


def prepare(catalog, taxonomy):
    entries = catalog['entries']
    if not entries or len(entries) > 2000: raise ValueError('Unexpected catalog size')
    grouped = defaultdict(list)
    for entry in entries:
        identity, url = source_identity(entry['source_url'], entry['resource_type'])
        grouped[identity].append({**entry, 'source_url': url})
    labels = {(row['kind'], row['name']): row['id'] for row in taxonomy}
    result = []
    for identity, occurrences in sorted(grouped.items()):
        first = occurrences[0]; kind = first['resource_type']; issues = []
        titles = sorted({plain(e['title']) for e in occurrences})
        levels = {LEVELS[e['source_level']] for e in occurrences if e.get('source_level') in LEVELS}
        detail = next((e['detail'] for e in occurrences if e.get('detail', {}).get('verified')), {})
        title = plain(detail.get('title') or first['title'])
        summary = plain(detail.get('summary') or max((e['summary'] for e in occurrences), key=len))
        if len(titles) > 1 and not detail: issues.append('source_title_conflict')
        if kind == 'lab' and any(e.get('detail', {}).get('verified') is False for e in occurrences):
            issues.append('public_detail_unavailable')
        if detail.get('source_level') in LEVELS: levels = {LEVELS[detail['source_level']]}
        if len(levels) > 1: issues.append('source_level_conflict')
        level = next(iter(levels)) if len(levels) == 1 else None
        # The source's general zone track maps to the existing introductory tier.
        if not levels and any(e.get('source_level') == '通用' for e in occurrences):
            explicit = re.search(r'(初级|中级|高级)(?:工程师|课程)', title)
            level = LEVELS[explicit[1]] if explicit else 'basic'
        if not level: issues.append('missing_level')
        duration = None
        if detail.get('duration_seconds'):
            duration = math.ceil(float(detail['duration_seconds']) / 60)
        elif first.get('duration_text'):
            match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(小时|分钟|h|min)\s*', first['duration_text'])
            if match: duration = math.ceil(float(match[1]) * (60 if match[2] in ('小时', 'h') else 1))
        metadata = dict(resource_type=kind, title=title, summary=summary,
                        source_url=first['source_url'], level=level, duration_minutes=duration)
        for names, field, category_kind in [('roles', 'role_ids', 'role'), ('zones', 'zone_ids', 'zone')]:
            values = sorted({plain(n) for e in occurrences for n in e.get(names, [])})
            unknown = [n for n in values if (category_kind, n) not in labels]
            if unknown: raise ValueError('Unknown categories: ' + ', '.join(unknown))
            metadata[field] = [labels[(category_kind, n)] for n in values]
        if kind == 'lab': metadata['lab_goals'] = plain(detail.get('lab_goals', ''))
        clean = service.ResourceMetadata.model_validate(metadata).model_dump()
        result.append({'identity': identity, 'metadata': clean, 'issues': issues,
                       'source_titles': titles,
                       'source_levels': sorted({e.get('source_level', '') for e in occurrences}),
                       'source_pages': sorted({e['source_page'] for e in occurrences}),
                       'detail_verified': bool(detail)})
    return result


def plan_import(conn, records):
    identities = {}; titles = defaultdict(set); ids = set()
    existing = conn.execute('SELECT id,draft_json FROM enablement_resources').fetchall()
    snapshots = [(r['id'], r['draft_json']) for r in existing]
    snapshots += [(r[0], r[1]) for r in conn.execute('SELECT source_id,payload_json FROM enablement_resource_versions')]
    for resource_id, raw in snapshots:
        ids.add(resource_id); data = json.loads(raw)
        titles[(data['resource_type'], plain(data['title']).casefold())].add(resource_id)
        try: key, _ = source_identity(data['source_url'], data['resource_type'])
        except (ValueError, KeyError): continue
        identities.setdefault(key, resource_id)
    result = []
    for record in records:
        metadata = record['metadata']; key = record['identity']
        resource_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'banfei:huawei:' + key))
        if key in identities:
            result.append({**record, 'resource_id': identities[key], 'action': 'skip_existing'})
            continue
        if resource_id in ids: raise ValueError('Import resource ID collision')
        issues = list(record['issues'])
        if titles.get((metadata['resource_type'], metadata['title'].casefold())):
            issues.append('existing_title_different_source')
        result.append({**record, 'resource_id': resource_id, 'issues': issues,
                       'action': 'draft' if issues else 'publish'})
        titles[(metadata['resource_type'], metadata['title'].casefold())].add(resource_id)
    return result


def apply_catalog(catalog, actor):
    with get_db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        admin = conn.execute("SELECT id FROM users WHERE id=? AND role='admin' AND status='active'", (actor,)).fetchone()
        if not admin: raise ValueError('An active administrator is required')
        plan = plan_import(conn, prepare(catalog, categories.read(conn)))
        for record in plan:
            if record['action'] == 'skip_existing': continue
            source_id = record['resource_id']
            row = service.save('resource', source_id, service.ResourceSave(base_revision=0, metadata=record['metadata']), actor, connection=conn)
            row = service.permissions('resource', source_id, service.Permissions(base_revision=row['revision'],
                system_visible=True, model_allowed=True, partner_allowed=False,
                reason='华为云公开课程/实验信息及链接预置；供系统浏览和模型推荐；未授权伙伴外发'), actor, connection=conn)
            if record['action'] == 'publish':
                row = service.publish('resource', source_id, service.Revision(base_revision=row['revision']), actor, connection=conn)
            service.audit(conn, 'resource', source_id, 'import', actor, row,
                          'Huawei public catalog: ' + record['identity'])
        return plan


def summary(plan):
    return {action: {kind: sum(r['action'] == action and r['metadata']['resource_type'] == kind for r in plan)
                     for kind in ('course', 'lab')} for action in ('publish', 'draft', 'skip_existing')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('catalog', type=Path)
    parser.add_argument('--config', type=Path, default=ROOT / '.isolation/runtime/dev/environment.json')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--backup-dir', type=Path)
    parser.add_argument('--actor')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    os.environ['DATABASE_URL'] = config['DATABASE_URL']
    from sqlalchemy.engine import make_url
    url = make_url(os.environ['DATABASE_URL'])
    if not url.drivername.startswith('postgresql') or url.database != 'banfei_agent' or url.host not in ('localhost', '127.0.0.1') or url.query:
        raise ValueError('Only local runtime banfei_agent with its default schema is allowed')
    catalog = json.loads(args.catalog.read_text())
    with get_readonly_db() as conn:
        if conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] != '16':
            raise ValueError('Expected existing schema 16')
        plan = plan_import(conn, prepare(catalog, categories.read(conn)))
        admins = [r[0] for r in conn.execute("SELECT id FROM users WHERE role='admin' AND status='active'")]
    if args.apply:
        actor = args.actor or (admins[0] if len(admins) == 1 else None)
        if actor not in admins: raise ValueError('Specify one existing active administrator with --actor')
        if not args.backup_dir: raise ValueError('--backup-dir is required before writing')
        os.umask(0o077)
        args.backup_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        env = dict(os.environ, PGHOST=url.host, PGPORT=str(url.port or 5432), PGDATABASE=url.database,
                   PGUSER=url.username or '', PGPASSWORD=url.password or '')
        with (args.backup_dir / 'before.pgdump').open('xb') as output:
            subprocess.run(['pg_dump', '--format=custom', '--no-owner', '--no-acl'], env=env,
                           stdout=output, stderr=subprocess.PIPE, check=True)
        plan = apply_catalog(catalog, actor)
    report = {'applied': args.apply, 'time': datetime.now(timezone.utc).isoformat(),
              'summary': summary(plan), 'resources': plan, 'skipped_source_links': catalog.get('skipped', [])}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'applied': args.apply, **summary(plan)}, ensure_ascii=False))


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('Import failed: ' + type(error).__name__ + '; inspect the private input/configuration.', file=sys.stderr)
        sys.exit(1)
