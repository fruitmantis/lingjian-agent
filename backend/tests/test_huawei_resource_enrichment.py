"""Signed-in metadata enrichment preserves IDs, permissions and published history."""
import json
import pytest
from backend.app import enablement as service, enablement_catalog
from backend.app.database import get_db
from backend.tests.conftest import make_user
from backend.tests.test_huawei_resource_import import entry, catalog, actor
from scripts import import_huawei_resources as importer, enrich_huawei_resources as enrich


def setup(*entries):
    admin = actor()
    manifest = {'resources': importer.apply_catalog(catalog(*(entries or [entry()])), admin)}
    capture = {'resources': [dict(resource_id=r['resource_id'], resource_type=r['metadata']['resource_type'],
        source_url=r['metadata']['source_url'], status='ok', details={
            'title': r['metadata']['title'], 'summary': '官方完整简介', 'course_goals': '<p>迁移与回退</p>',
            'audience': '运维工程师', 'outline': '第1章 规划\n第2章 迁移',
            'cover_url': 'https://edu-res.hc-cdn.cn/course.jpg'}) for r in manifest['resources']]}
    return admin, manifest, capture


def snapshot():
    with get_db() as conn:
        return {table: [tuple(r) for r in conn.execute('SELECT * FROM ' + table)] for table in
                ('enablement_resources', 'enablement_resource_versions', 'enablement_audit_events')}


def test_same_resource_new_version_with_unchanged_permissions_and_repeat_is_noop():
    admin, manifest, capture = setup(); sid = manifest['resources'][0]['resource_id']
    before = snapshot()
    result = enrich.apply_enrichment(manifest, capture, admin)
    assert result[0]['action'] == 'publish'
    row = service.detail('resource', sid)
    assert row['published_version'] == 2 and row['metadata']['outline'] == '第1章 规划\n第2章 迁移'
    assert row['metadata']['course_goals'] == '迁移与回退'
    assert row['system_visible'] == row['model_allowed'] == 1 and row['partner_allowed'] == 0
    assert row['metadata']['role_ids'] == manifest['resources'][0]['metadata']['role_ids']
    with get_db() as conn:
        assert conn.execute('SELECT count(*) FROM enablement_resources').fetchone()[0] == 1
        assert tuple(conn.execute('SELECT * FROM enablement_resource_versions WHERE source_id=? AND version=1', (sid,)).fetchone()) == before['enablement_resource_versions'][0]
        assert service.resolve_reference(conn, 'course', sid, 2, 'model')['outline'].startswith('第1章')
    assert enablement_catalog.redirect('course', sid, 2, admin)['url'] == capture['resources'][0]['source_url']
    state = snapshot()
    assert enrich.apply_enrichment(manifest, capture, admin)[0]['action'] == 'unchanged'
    assert snapshot() == state


def test_manual_fields_and_unpublished_draft_are_not_published():
    admin, manifest, capture = setup(); sid = manifest['resources'][0]['resource_id']
    row = service.detail('resource', sid)
    service.save('resource', sid, service.ResourceSave(base_revision=row['revision'],
        metadata={**row['metadata'], 'title': '管理员标题'}), admin)
    result = enrich.apply_enrichment(manifest, capture, admin)[0]
    assert result['action'] == 'draft' and result['protected_fields'] == ['title']
    row = service.detail('resource', sid)
    assert row['metadata']['title'] == '管理员标题' and row['metadata']['audience'] == '运维工程师'
    assert row['published_version'] == 1 and row['published_metadata']['title'] != '管理员标题'


def test_empty_detail_fields_do_not_erase_existing_content():
    admin, manifest, capture = setup()
    capture['resources'][0]['details'] = {'title': '', 'summary': '', 'outline': ''}
    state = snapshot()
    assert enrich.apply_enrichment(manifest, capture, admin)[0]['action'] == 'unchanged'
    assert snapshot() == state


@pytest.mark.parametrize('change', ['unpublish', 'source'])
def test_administrator_unpublishing_or_source_change_is_preserved(change):
    admin, manifest, capture = setup(); sid = manifest['resources'][0]['resource_id']
    row = service.detail('resource', sid)
    if change == 'unpublish':
        service.unpublish('resource', sid, service.Unpublish(base_revision=row['revision'], reason='管理员下架'), admin)
    else:
        service.save('resource', sid, service.ResourceSave(base_revision=row['revision'],
            metadata={**row['metadata'], 'source_url': 'https://example.com/edited'}), admin)
    state = snapshot()
    assert enrich.apply_enrichment(manifest, capture, admin)[0]['action'] == 'protected'
    assert snapshot() == state


def test_unavailable_source_makes_no_changes():
    admin, manifest, capture = setup(); capture['resources'][0] = {**capture['resources'][0], 'status': 'unavailable'}
    state = snapshot()
    assert enrich.apply_enrichment(manifest, capture, admin)[0]['action'] == 'unavailable'
    assert snapshot() == state


@pytest.mark.parametrize('change', ['resource_id', 'source_url', 'token', 'cover', 'oversized'])
def test_invalid_capture_rolls_back_without_writes(change):
    admin, manifest, capture = setup(); r = capture['resources'][0]
    if change == 'resource_id': r['resource_id'] = 'unrelated'
    if change == 'source_url': r['source_url'] = r['source_url'].replace('C123', 'C999')
    if change == 'token': r['source_url'] += '?ticket=do-not-store'
    if change == 'cover': r['details']['cover_url'] += '?token=do-not-store'
    if change == 'oversized': r['details']['outline'] = 'a' * 12001
    state = snapshot()
    with pytest.raises(ValueError): enrich.apply_enrichment(manifest, capture, admin)
    assert snapshot() == state


def test_official_detail_resolves_catalog_title_conflict_without_new_resource():
    admin, manifest, capture = setup(entry(), entry(title='另一路径标题'))
    assert manifest['resources'][0]['action'] == 'draft'
    capture['resources'][0]['details']['title'] = '官方详情标题'
    assert enrich.apply_enrichment(manifest, capture, admin)[0]['action'] == 'publish'
    row = service.detail('resource', manifest['resources'][0]['resource_id'])
    assert row['published_version'] == 1 and row['metadata']['title'] == '官方详情标题'


def test_historical_reference_enriches_draft_only(monkeypatch):
    admin, manifest, capture = setup(); sid = manifest['resources'][0]['resource_id']
    # Each supported persisted JSON location is tested separately below.
    monkeypatch.setattr(enrich, 'referenced_ids', lambda conn, identifiers: {sid})
    result = enrich.apply_enrichment(manifest, capture, admin)[0]
    assert result['action'] == 'draft' and result['notes'] == ['historical_or_running_reference']
    row = service.detail('resource', sid)
    assert row['published_version'] == 1 and row['published_metadata']['outline'] == ''
    with get_db() as conn: assert service.resolve_reference(conn, 'course', sid, 1, 'system')


@pytest.mark.parametrize('location', ['development_requests', 'development_runs', 'development_versions', 'development_version_items'])
def test_reference_scan_covers_snapshots_and_nested_items(location):
    class Connection:
        def execute(self, sql):
            return [(json.dumps({'items': [{'source_id': 'resource-a'}]}),)] if sql.endswith('FROM ' + location) else []
    assert enrich.referenced_ids(Connection(), {'resource-a', 'resource-b'}) == {'resource-a'}


def test_entire_batch_rolls_back_when_publish_fails(monkeypatch):
    admin, manifest, capture = setup(entry(), entry(identifier='C456', title='另一课程'))
    state = snapshot(); original = service.publish; count = 0
    def fail(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2: raise RuntimeError('synthetic failure')
        return original(*args, **kwargs)
    monkeypatch.setattr(service, 'publish', fail)
    with pytest.raises(RuntimeError): enrich.apply_enrichment(manifest, capture, admin)
    assert snapshot() == state


def test_ordinary_actor_cannot_enrich():
    admin, manifest, capture = setup(); state = snapshot()
    with pytest.raises(ValueError): enrich.apply_enrichment(manifest, capture, make_user('reader')['id'])
    assert snapshot() == state


def test_official_cover_hosts_and_lab_goal_sanitization():
    for host in ['edu-res.hc-cdn.cn', 'communityfile.developer.myhuaweicloud.com']:
        assert enrich.clean_details({'cover_url': f'https://{host}/cover.jpg'}, 'course')['cover_url'].endswith('cover.jpg')
    assert enrich.clean_details({'lab_goals': '<p>理解迁移</p><script>bad()</script>',
        'lab_requirements': '<p>了解基础知识</p>', 'duration_minutes': 30, 'price': 100}, 'lab') == {
        'lab_goals': '理解迁移', 'lab_requirements': '了解基础知识', 'duration_minutes': 30}
