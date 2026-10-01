"""Stage timestamps stored inside the existing task/Run snapshots."""
from datetime import datetime, timezone

STAGES = {
    'partner_match': [('understanding', '理解项目需求'), ('initial_selection', '寻找合适伙伴'),
                      ('detailed_review', '形成伙伴推荐'), ('enrichment', '完善项目分析')],
    'development_plan': [('understanding', '分析发展方向'), ('retrieval', '查找学习资源'),
                         ('generation', '形成发展建议')],
}


def now():
    return datetime.now(timezone.utc).isoformat()


def new(kind, run_id, started_at=None):
    return {'run_id': run_id, 'started_at': started_at or now(), 'finished_at': None,
            'stages': [{'key': key, 'label': label, 'status': 'pending',
                        'started_at': None, 'finished_at': None} for key, label in STAGES[kind]]}


def stage(progress, key, status):
    if not progress:
        return
    item = next(item for item in progress['stages'] if item['key'] == key)
    stamp = now()
    if status == 'running':
        item['started_at'] = item['started_at'] or stamp
    elif item['started_at']:
        item['finished_at'] = stamp
    item['status'] = status


def finish(progress, failed=False, finished_at=None):
    if not progress or progress.get('finished_at'):
        return
    stamp = finished_at or now()
    progress['finished_at'] = stamp
    for item in progress['stages']:
        if item['status'] == 'running':
            item.update(status='failed' if failed else 'completed', finished_at=stamp)
        elif item['status'] == 'pending':
            item['status'] = 'skipped'
