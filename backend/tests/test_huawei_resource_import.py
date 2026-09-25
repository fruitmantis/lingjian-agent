"""Import contract and transaction regressions; dedicated validation database only."""
from copy import deepcopy
import json
import pytest
from fastapi import HTTPException
from backend.app import enablement as service, enablement_catalog, resource_categories, development_engine
from backend.app.database import get_db
from backend.tests.conftest import make_user
from scripts import import_huawei_resources as importer


def entry(kind='course', identifier='C123', **extra):
    return {'resource_type': kind, 'title': '公开课程' if kind == 'course' else '公开实验',
            'summary': '学习迁移校验及回退', 'roles': ['迁移工程师'], 'zones': [], 'source_level': '基础',
            'source_page': 'https://www.huaweicloud.com/partners/training/course.html',
            'source_url': f'https://connect.huaweicloud.com/courses/learn/{identifier}/about' if kind == 'course'
            else f'https://edu.huaweicloud.com/lab/experiment-detail_{identifier}', **extra}


def catalog(*entries): return {'entries': list(entries)}


def actor(): return make_user('catalog-import-admin', role='admin')['id']


def test_merge_path_occurrences_into_one_resource_and_keep_dynamic_categories():
    a = entry(); b = entry(roles=['数据库工程师'], zones=['DataArts'], source_level='通用')
    b['source_url'] += '?utm_source=path#intro'
    plan = importer.apply_catalog(catalog(a, b, deepcopy(a)), actor())
    assert len(plan) == 1 and plan[0]['action'] == 'publish'
    sid = plan[0]['resource_id']
    for role in ['role-1', 'role-4']:
        result = enablement_catalog.catalog(source_type='course', role_id=role)
        assert result['total'] == 1 and result['items'][0]['source_id'] == sid
    with get_db() as conn:
        data = service.resolve_reference(conn, 'course', sid, 1, 'model')
        assert set(data['role_ids']) == {'role-1', 'role-4'}
        assert data['zone_ids'] == ['zone-3'] and data['level'] == 'basic'
        assert data['duration_minutes'] is None and data['outline'] == ''
        assert 'source_url' not in data
        with pytest.raises(HTTPException): service.resolve_reference(conn, 'course', sid, 1, 'partner')
        candidates = development_engine.candidates(conn, {'development_direction': '迁移'}, {'priorities': [{'name': '迁移', 'search_terms': ['迁移']}]})
        assert candidates[0]['source_id'] == sid
        assert conn.execute('SELECT count(*) FROM enablement_resources').fetchone()[0] == 1
        assert conn.execute('SELECT count(*) FROM enablement_resource_versions').fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM enablement_audit_events WHERE action='import'").fetchone()[0] == 1


def test_lab_details_override_catalog_and_remove_markup():
    value = entry('lab', '123', source_level='初级', duration_text='1.5小时', detail={
        'verified': True, 'title': '核对后的实验', 'summary': '<p>迁移简介</p><script>bad()</script>',
        'source_level': '中级', 'duration_seconds': 3660, 'lab_goals': '<ul><li>校验</li><li>回退</li></ul>'})
    plan = importer.apply_catalog(catalog(value), actor())
    assert plan[0]['metadata']['title'] == '核对后的实验'
    assert plan[0]['metadata']['summary'] == '迁移简介'
    assert plan[0]['metadata']['duration_minutes'] == 61
    assert plan[0]['metadata']['level'] == 'advanced'
    assert plan[0]['metadata']['lab_goals'] == '校验\n回退'
    sid = plan[0]['resource_id']
    redirect = enablement_catalog.redirect('lab', sid, 1, make_user('reader')['id'])
    assert redirect['url'] == value['source_url']


@pytest.mark.parametrize('difference', [{'title': '另一名称'}, {'source_level': '进阶'}])
def test_ambiguous_source_kept_as_draft(difference):
    plan = importer.apply_catalog(catalog(entry(), entry(**difference)), actor())
    assert plan[0]['action'] == 'draft' and plan[0]['issues']
    assert enablement_catalog.catalog(source_type='course')['total'] == 0
    with get_db() as conn: assert conn.execute('SELECT count(*) FROM enablement_resource_versions').fetchone()[0] == 0


def test_repeat_import_preserves_admin_edits_unpublishing_and_versions():
    admin = actor(); payload = catalog(entry())
    first = importer.apply_catalog(payload, admin)[0]; sid = first['resource_id']
    original = service.detail('resource', sid)
    service.unpublish('resource', sid, service.Unpublish(base_revision=original['revision'], reason='管理员下架'), admin)
    row = service.detail('resource', sid); changed = {**row['metadata'], 'title': '管理员维护标题'}
    service.save('resource', sid, service.ResourceSave(base_revision=row['revision'], metadata=changed), admin)
    with get_db() as conn:
        before = {t: [tuple(r) for r in conn.execute('SELECT * FROM ' + t)] for t in
                  ['enablement_resources', 'enablement_resource_versions', 'enablement_audit_events']}
    assert importer.apply_catalog(payload, admin)[0]['action'] == 'skip_existing'
    with get_db() as conn:
        assert before == {t: [tuple(r) for r in conn.execute('SELECT * FROM ' + t)] for t in before}


def test_import_failure_rolls_back_entire_batch(monkeypatch):
    admin = actor(); real = service.publish; count = 0
    def fail_second(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2: raise RuntimeError('synthetic import failure')
        return real(*args, **kwargs)
    monkeypatch.setattr(service, 'publish', fail_second)
    with pytest.raises(RuntimeError):
        importer.apply_catalog(catalog(entry(), entry(identifier='C456', title='第二门课程')), admin)
    with get_db() as conn:
        for table in ['enablement_resources', 'enablement_resource_versions', 'enablement_audit_events']:
            assert conn.execute('SELECT count(*) FROM ' + table).fetchone()[0] == 0


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'https://127.0.0.1/course',
    'https://connect.huaweicloud.com.attacker.example/courses/learn/C123/about',
    'https://connect.huaweicloud.com/courses/exam/C123/about',
    'https://user:password@connect.huaweicloud.com/courses/learn/C123/about'])
def test_unexpected_or_unsafe_links_rejected(url):
    with pytest.raises(ValueError): importer.prepare(catalog(entry(source_url=url)), resource_categories.listing())


def test_unknown_category_and_ordinary_actor_rejected_without_writes():
    with pytest.raises(ValueError): importer.apply_catalog(catalog(entry(roles=['不存在的分类'])), actor())
    with pytest.raises(ValueError): importer.apply_catalog(catalog(entry()), make_user('reader')['id'])
    with get_db() as conn: assert conn.execute('SELECT count(*) FROM enablement_resources').fetchone()[0] == 0


def test_old_source_version_prevents_duplicate_even_if_draft_url_changed():
    admin = actor(); payload = catalog(entry())
    sid = importer.apply_catalog(payload, admin)[0]['resource_id']
    row = service.detail('resource', sid)
    metadata = {**row['metadata'], 'source_url': 'https://example.com/administrator-updated-link'}
    service.save('resource', sid, service.ResourceSave(base_revision=row['revision'], metadata=metadata), admin)
    assert importer.apply_catalog(payload, admin)[0]['action'] == 'skip_existing'


def test_same_title_different_source_kept_for_review():
    plan = importer.apply_catalog(catalog(entry(), entry(identifier='C456')), actor())
    assert [r['action'] for r in plan] == ['publish', 'draft']
    assert plan[1]['issues'] == ['existing_title_different_source']


def test_plain_text_preserves_ampersand_and_line_breaks():
    assert importer.plain('ModelArts介绍&运维') == 'ModelArts介绍&运维'
    assert importer.plain('<p>训练&amp;推理</p><p>交付</p>') == '训练&推理\n交付'


def test_unavailable_lab_is_imported_as_hidden_draft():
    row = entry('lab', '123', duration_text='1.5小时', detail={'verified': False})
    result = importer.apply_catalog(catalog(row), actor())[0]
    assert result['action'] == 'draft'
    assert result['metadata']['duration_minutes'] == 90
    assert enablement_catalog.catalog(source_type='lab')['total'] == 0


def test_source_login_ticket_is_not_stored_or_audited():
    value = entry(source_url='https://connect.huaweicloud.com/courses/learn/C123/about?ticket=example-one-time-ticket&locale=zh-cn')
    importer.apply_catalog(catalog(value), actor())
    with get_db() as conn:
        for table in ['enablement_resources', 'enablement_resource_versions', 'enablement_audit_events']:
            for row in conn.execute('SELECT * FROM ' + table):
                assert 'example-one-time-ticket' not in str(tuple(row))


def test_general_track_respects_explicit_level_in_official_title():
    data = catalog(entry(title='数据治理中心中级工程师', source_level='通用'))
    assert importer.prepare(data, resource_categories.listing())[0]['metadata']['level'] == 'advanced'
