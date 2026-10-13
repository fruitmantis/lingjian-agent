"""Original BF-CLOSE business evidence replay; isolated PG, no provider calls.

BF_CLOSE_EVIDENCE_DIR holds the archived business-only fixtures prepared by the
developer handoff. These are input snapshots, never runtime uploads or credentials.
"""
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi import HTTPException
from backend.app import development_context as context, development_engine as engine
from backend.app import development_lifecycle as life, development_model as model
from backend.app import development_views as views, enablement, profile_sources as sources
from backend.app.database import get_db
from backend.app.development_types import AdvicePatch, Conversation
from backend.business import development
from backend.tests.conftest import auth_headers
from backend.tests.test_development_lifecycle import prepared


@pytest.fixture
def evidence():
    location = os.environ.get('BF_CLOSE_EVIDENCE_DIR')
    if not location:
        pytest.skip('Original BF-CLOSE archived fixtures require BF_CLOSE_EVIDENCE_DIR; see the developer handoff.')
    root = Path(location)
    return root, json.loads((root / 'ORIGINAL-FIXTURES.json').read_text())


def insert(conn, table, row):
    columns = ','.join(row)
    conn.execute(f'INSERT INTO {table} ({columns}) VALUES ({",".join("?" for _ in row)})', tuple(row.values()))


def seed_plan(conn, before, request, version_rows, user):
    plan = before['plan']; pid = plan['id']; stamp = plan['created_at']
    insert(conn, 'development_requests', {'id': plan['request_id'], 'owner_user_id': user['id'],
        'target_partner_id': None, 'payload_json': json.dumps(request, ensure_ascii=False),
        'created_at': stamp, 'created_by': user['id']})
    insert(conn, 'development_plans', {'id': pid, 'request_id': plan['request_id'],
        'owner_user_id': user['id'], 'target_partner_id': None, 'status': 'active',
        'current_version_id': None, 'active_run_id': None, 'created_at': stamp, 'updated_at': stamp})
    for row in version_rows:
        insert(conn, 'development_versions', {'id': row['id'], 'plan_id': pid,
            'version_no': row.get('version_no', 1), 'based_on_version_id': row.get('based_on_version_id'),
            'run_id': None, 'payload_json': row['payload_json'], 'dependency_json': row['dependency_json'],
            'created_by': user['id'], 'created_at': row.get('created_at', stamp)})
        for index, item in enumerate(i for stage in json.loads(row['payload_json'])['stages'] for i in stage['items']):
            insert(conn, 'development_version_items', {'id': life.uid(), 'version_id': row['id'],
                'ordinal': index, 'payload_json': json.dumps(item, ensure_ascii=False)})
    conn.execute('UPDATE development_plans SET current_version_id=? WHERE id=?', (version_rows[-1]['id'], pid))
    return pid, version_rows[-1]['id']


def record(root, name, value):
    (root / name).write_text(json.dumps(value, ensure_ascii=False, indent=2))


@pytest.mark.parametrize('reverse_pair', [False, True])
def test_original_bq22_recorded_pair_reaches_saved_version(prepared, evidence, monkeypatch, client, reverse_pair):
    root, fixture = evidence; user, _, admin, _ = prepared
    for sid, kind, title, summary in fixture['bq22_resources']:
        metadata = {'resource_type': kind, 'title': title, 'summary': summary,
            'level': 'advanced' if sid.endswith('advanced') else 'basic', 'source_url': 'https://example.invalid/' + sid}
        metadata['course_goals' if kind == 'course' else 'lab_goals'] = summary
        row = enablement.save('resource', sid, enablement.ResourceSave(base_revision=0, metadata=metadata), admin['id'])
        row = enablement.permissions('resource', sid, enablement.Permissions(base_revision=row['revision'],
            system_visible=True, model_allowed=True, partner_allowed=True, reason='Original BQ22 isolated fixture'), admin['id'])
        enablement.publish('resource', sid, enablement.Revision(base_revision=row['revision']), admin['id'])
    before = fixture['bq22_before']; version = fixture['bq22_version']
    with get_db() as conn:
        pid, base = seed_plan(conn, before, before['request'], [version], user)
        assert conn.execute('SELECT payload_json FROM development_versions WHERE id=?', (base,)).fetchone()[0] == version['payload_json']
        assert conn.execute('SELECT dependency_json FROM development_versions WHERE id=?', (base,)).fetchone()[0] == version['dependency_json']
    original = copy.deepcopy(before['payload']); calls = []
    responses = copy.deepcopy(fixture['bq22_responses'])
    if reverse_pair: responses[1]['changes'][1:] = reversed(responses[1]['changes'][1:])
    def complete(config, messages, schema):
        calls.append({'schema': schema['title'], 'input': json.loads(messages[-1]['content'])})
        return json.dumps(responses[len(calls)-1], ensure_ascii=False)
    monkeypatch.setattr(model, 'completion', complete)
    run = views.converse(pid, Conversation(submission_id='bfclose-bq22-'+str(reverse_pair),
        based_on_version_id=base, message=fixture['bq22_message']), user)
    engine.execute(run['run_id'])
    after = client.get('/development/plans/' + pid, headers=auth_headers(user)).json()
    assert after['runs'][0]['status'] == 'ready', after['runs']
    assert after['plan']['current_version_id'] != base and len(after['versions']) == 2
    assert [row['schema'] for row in calls] == ['Understanding', 'AdvicePatch']
    items = [item for stage in after['payload']['stages'] for item in stage['items']]
    previous = [item for stage in original['stages'] for item in stage['items']]
    assert [i['source_id'] for i in items] == ['bq22-rag-lab', 'bq22-rag-advanced', 'bq22-migration-lab']
    assert items[0]['item_id'] == previous[1]['item_id']
    assert items[1]['item_id'] not in {i['item_id'] for i in previous}
    assert items[2] == previous[2]
    answer = after['payload']['answer']
    assert answer == '团队已会Python并做过API集成，但尚未做过RAG，可直接开展RAG实践，并逐步提升到企业级Agent与RAG应用。保留数据库迁移回滚验证安排。'
    active = answer + json.dumps(items + after['payload']['next_steps'], ensure_ascii=False)
    assert '尚不会Python' not in active and '没有API集成经验' not in active and '先补Python' not in active
    assert after['request']['known_baseline'] == responses[0]['effective_baseline']
    assert after['request']['development_direction'] == before['request']['development_direction']
    assert after['payload']['limitations'] == original['limitations']  # Legacy read contract unchanged.
    with get_db() as conn:
        deps = json.loads(conn.execute('SELECT dependency_json FROM development_versions WHERE id=?',
            (after['plan']['current_version_id'],)).fetchone()[0])
        old_deps = json.loads(version['dependency_json'])
        assert all(ref in deps for ref in old_deps if ref.get('source_id') == 'bq22-migration-lab')
    with pytest.raises(HTTPException) as stale:
        views.converse(pid, Conversation(submission_id='bfclose-stale', based_on_version_id=base, message='调整'), user)
    assert stale.value.status_code == 409
    with pytest.raises(HTTPException) as forbidden:
        views.converse(pid, Conversation(submission_id='bfclose-owner', based_on_version_id=after['plan']['current_version_id'], message='调整'), prepared[1])
    assert forbidden.value.status_code == 404
    record(root, 'BQ22-SAVED-'+str(reverse_pair)+'.json', {'original_version_id': base,
        'original_payload_sha256': hashlib.sha256(version['payload_json'].encode()).hexdigest(),
        'actual_inputs': calls, 'saved_api': after, 'saved_dependencies': deps, 'provider_calls': 0})


@pytest.mark.parametrize('fault', ['duplicate_replace', 'duplicate_add', 'remove_replace', 'missing', 'outside', 'illegal_ref'])
def test_original_anchor_conflicts_and_reference_guards(prepared, evidence, fault):
    _, fixture = evidence
    old = fixture['bq22_before']['payload']; analysis = fixture['bq22_responses'][0]
    patch = development.parse(json.dumps(fixture['bq22_responses'][1]), AdvicePatch, [])
    replacement = copy.deepcopy(patch['changes'][1]); addition = copy.deepcopy(patch['changes'][2])
    pool = [{'source_type': i['source_type'], 'source_id': i['source_id'], 'source_version': i['source_version'],
        'title': i['title'], 'capability_tag_ids': []} for s in old['stages'] for i in s['items']]
    pool.append({'source_type': 'lab', 'source_id': 'bq22-rag-advanced', 'source_version': 1,
        'title': 'RAG混合检索与权限实验', 'capability_tag_ids': []})
    if fault == 'duplicate_replace': patch['changes'] = [replacement, copy.deepcopy(replacement)]
    elif fault == 'duplicate_add': patch['changes'] = [addition, copy.deepcopy(addition)]
    elif fault == 'remove_replace': patch['changes'] = [{'action': 'remove', 'item_id': replacement['item_id'], 'items': []}, replacement]
    elif fault == 'missing':
        replacement['item_id'] = 'not-in-original-version'; analysis = {**analysis, 'edit_item_ids': ['not-in-original-version']}; patch['changes'] = [replacement]
    elif fault == 'outside':
        replacement['item_id'] = old['stages'][0]['items'][2]['item_id']; patch['changes'] = [replacement]
    else:
        replacement['items'][0]['source_version'] = 999; patch['changes'] = [replacement]
    unchanged = copy.deepcopy(old)
    with pytest.raises(engine.InvalidOutput): engine.merge_patch(old, patch, analysis, fixture['bq22_before']['request'], pool, prepared[0]['id'])
    assert old == unchanged


def test_original_bq21_latest_pair_and_current_twelve_identity(prepared, evidence, monkeypatch, client):
    root, fixture = evidence; user, _, admin, _ = prepared; snapshot = fixture['bq21_snapshot']
    with get_db() as conn:
        for table, rows in snapshot['catalog'].items():
            for original in rows:
                row = copy.deepcopy(original)
                for field in ('created_by','updated_by','published_by'):
                    if field in row and row[field]: row[field] = admin['id']
                insert(conn, table, row)
        request = json.loads(snapshot['request']['payload_json'])
        allowed = {row['submission_id'] for row in fixture['bq21_before']['conversation']}
        stored_history = {row['submission_id']: row for row in request.get('_conversation', []) if row['submission_id'] in allowed}
        # Original revise pairs normally come from the Version/Run join. Preserve
        # their exact archived business message/answer in this owned fixture too.
        history = [copy.deepcopy(stored_history.get(row['submission_id'], {k:v for k,v in row.items() if k != 'resources'}))
            for row in fixture['bq21_before']['conversation']]
        request = {k:v for k,v in request.items() if not k.startswith('_')}
        request['_conversation'] = history
        pid, base = seed_plan(conn, {'plan': snapshot['plan']}, request, snapshot['versions'], user)
    before = views.detail(pid, user); old = copy.deepcopy(before['payload'])
    original_items = [item for stage in old['stages'] for item in stage['items']]
    assert len(original_items) == 12 and original_items[3]['item_id'] == '8db8cb18-179d-41d9-928b-e0c9ca782bf1'
    frame = context.load(request, user, plan_id=pid, base=base, message='只解释为什么推荐第二个实验，不要改方案。')['input']
    assert [row['item_id'] for row in frame['current']['resources']] == [row['item_id'] for row in original_items]
    assert frame['current']['resources'][3]['reference_label'] == '实验2｜ModelArts实践-部署Qwen3-8B模型并进行调用'
    assert len(frame['recent_exchanges']) == 1 and frame['recent_exchanges'][0]['message'] == before['conversation'][-1]['message']
    assert 'earlier_user_messages' not in frame
    assert all(row['message'] != before['conversation'][0]['message'] for row in frame['recent_exchanges'])
    assert frame['request']['development_direction'] == request['development_direction']
    assert old['effective_request']['development_direction'] != request['development_direction']
    calls = []
    def complete(config, messages, schema):
        data = json.loads(messages[-1]['content']); calls.append(data)
        recent = data['recent_exchanges']
        if '刚才那段' in data['message']:
            assert len(recent) == 1 and recent[0]['answer'] == '第二个实验是ModelArts实践-部署Qwen3-8B模型并进行调用；先练习模型部署与调用。'
        return json.dumps({'target_partner_id': None, 'in_scope': True, 'intent': 'development', 'interpretation': '解释当前第二个实验并继续近期讨论。', 'action': 'answer',
            'effective_direction': data['request']['development_direction'], 'effective_baseline': data['request']['known_baseline'],
            'effective_constraints': data['constraints'], 'answer': '第二个实验是ModelArts实践-部署Qwen3-8B模型并进行调用；先练习模型部署与调用。',
            'edit_item_ids': [], 'edit_answer_spans': [], 'used_refs': [], 'used_profile_chapters': []}, ensure_ascii=False)
    monkeypatch.setattr(model, 'completion', complete)
    for index, message in enumerate(('只解释为什么推荐第二个实验，不要改方案。', '刚才那段说的模型调用具体是什么？方案不改。')):
        run = views.converse(pid, Conversation(submission_id='bfclose-bq21-'+str(index), based_on_version_id=base, message=message), user)
        engine.execute(run['run_id'])
        after = client.get('/development/plans/'+pid, headers=auth_headers(user)).json()
        assert after['runs'][0]['status'] == 'ready', after['runs']
        assert after['plan']['current_version_id'] == base and len(after['versions']) == 2
        assert after['payload'] == old
        assert [row['message'] for row in after['conversation'][:len(before['conversation'])]] == [row['message'] for row in before['conversation']]
    explain_after = copy.deepcopy(after)
    replacement_id = '233ed896-481d-5bb2-92b5-28f3d0f89f1b'  # Original stage-0015 catalog candidate.
    target = original_items[3]['item_id']; patch_inputs = []
    def patch_complete(config, messages, schema):
        data = json.loads(messages[-1]['content']); patch_inputs.append({'schema':schema['title'], 'input':data})
        if schema['title'] == 'Understanding':
            return json.dumps({'target_partner_id':None, 'in_scope':True, 'intent':'development',
                'interpretation':'仅替换当前第二个实验，其余保持。', 'action':'patch', 'answer':'',
                'effective_direction':'更进阶的Agent智能助手搭建实践', 'effective_baseline':data['request']['known_baseline'],
                'effective_constraints':data['constraints'], 'priorities':[{'name':'Agent智能助手', 'reason':'本次更进阶的实践', 'search_terms':['Agent']}],
                'edit_item_ids':[target], 'edit_answer_spans':[], 'used_refs':[], 'used_profile_chapters':[]}, ensure_ascii=False)
        assert any(row['source_id'] == replacement_id for row in data['candidates'])
        return json.dumps({'target_partner_id':None, 'answer':'已将第二个实验替换为进阶Agent实践，其余不变。',
            'changes':[{'action':'replace', 'item_id':target, 'items':[{'source_type':'lab', 'source_id':replacement_id,
                'source_version':1, 'focus':'Agent智能助手', 'reason':'第二个实验更进阶的Agent实践'}]}],
            'answer_changes':[], 'used_refs':[], 'used_profile_chapters':[]}, ensure_ascii=False)
    monkeypatch.setattr(model, 'completion', patch_complete)
    with get_db() as conn:
        old_deps = json.loads(conn.execute('SELECT dependency_json FROM development_versions WHERE id=?',(base,)).fetchone()[0])
    run = views.converse(pid, Conversation(submission_id='bfclose-bq21-patch', based_on_version_id=base,
        message='只将第二个实验换成更进阶的，其他不变。'), user)
    engine.execute(run['run_id'])
    patched = client.get('/development/plans/'+pid, headers=auth_headers(user)).json()
    assert patched['runs'][0]['status'] == 'ready', patched['runs']
    assert len(patched['versions']) == 3 and patched['plan']['current_version_id'] != base
    changed_items = [item for stage in patched['payload']['stages'] for item in stage['items']]
    assert len(changed_items) == 12 and [item['item_id'] for item in changed_items] == [item['item_id'] for item in original_items]
    assert changed_items[3]['source_id'] == replacement_id
    assert all(changed_items[index] == item for index,item in enumerate(original_items) if index != 3)
    assert patched['payload']['answer'] == old['answer']
    with get_db() as conn:
        new_deps = json.loads(conn.execute('SELECT dependency_json FROM development_versions WHERE id=?',
            (patched['plan']['current_version_id'],)).fetchone()[0])
    assert all(ref in new_deps for ref in old_deps if ref.get('source_id') != original_items[3]['source_id'])
    record(root, 'BQ21-ACTUAL-INPUTS.json', {'initial_input': frame, 'actual_inputs': calls, 'patch_inputs':patch_inputs,
        'original_history_count': len(before['conversation']), 'saved_history_count': len(after['conversation']),
        'explain_api':explain_after, 'patched_api':patched, 'new_dependencies':new_deps,
        'current_version_id_before': base, 'item_ids': [i['item_id'] for i in original_items], 'provider_calls': 0,
        'limit': 'Mock asserts the projection/save contract; actual model semantic selection belongs to QA.'})


def test_original_s5_literal_body_boundary_and_normal_business_control(evidence):
    root, fixture = evidence; text = fixture['s5_text']
    assert hashlib.sha256(text.encode()).hexdigest() == fixture['s5_sha256']
    source = {'kind': 'document', 'id': 'archived-original-native', 'text': text}
    blocks, mapping = sources.source_blocks(source)
    delivered = '\n'.join(row['text'] for row in blocks)
    assert delivered.startswith('# 神州数码DC·AI')
    assert '信息提供⽇期：2025-01-20 11:26' in delivered
    for marker in ('证据边界：', '图⽂限制：', '原⽂实际读取时间：', '分享到：', '打印本⻚', '关于我们', '原⽂存档结束'):
        assert marker not in delivered
    for fact in ('AI for Process', '魔⽅智脑', '企业', '⾼仙', '未来'):
        assert fact in delivered
    assert source['text'] == text
    for block in blocks:
        location = mapping[block['id']]
        assert text[location['start']:location['end']] == block['text']
    normal = '业务验收尚未完成。项目计划升级，撤销旧接口；信息来源：客户，未来将开展交付。分享到：团队内部。\n正常产品说明。'
    ordinary = sources.source_blocks({'kind': 'document', 'id': 'normal', 'text': normal})[0]
    assert '\n'.join(row['text'] for row in ordinary) == normal
    record(root, 'S5-LITERAL-PROJECTION.json', {'native_sha256': fixture['s5_sha256'], 'native_length': len(text),
        'blocks': blocks, 'mapping': mapping, 'normal_control': ordinary, 'provider_calls': 0})


def test_original_six_cache_only_s5_retry_then_merge_repeat_zero(prepared, evidence, monkeypatch, client):
    from backend.app.storage_models import metadata
    from backend.tests.test_profile_report import merge_result
    root, fixture = evidence; user, _, admin, _ = prepared; original = fixture['six_cache']
    pid = original['partner']['id']; sid = original['s5_id']; calls = []
    def allowed_insert(conn, table, value):
        row = {key:copy.deepcopy(val) for key,val in value.items() if key in metadata.tables[table].columns}
        for field in ('created_by','updated_by','published_by'):
            if row.get(field): row[field] = admin['id']
        insert(conn, table, row)
    with get_db() as conn:
        partner = {**original['partner'], 'ai_profile': '', 'profile_chapter_meta': '{}'}
        allowed_insert(conn, 'partners', partner)
        for row in original['cases']: allowed_insert(conn, 'cases', {**row, 'description': ''})
        for row in original['natives']: allowed_insert(conn, 'deliverables', row)
        for row in original['sources']: allowed_insert(conn, 'partner_profile_sources', row)
        for row in original['sources']:
            native = sources.source(conn, pid, 'attachment', row['source_id'])
            assert sources.stamp(native) == row['source_fingerprint']
        before = {r['source_id']:dict(r) for r in conn.execute("SELECT * FROM partner_profile_sources WHERE partner_id=? AND source_kind='attachment'", (pid,))}
        selected = sources.source(conn, pid, 'attachment', sid)
        fingerprint = sources.stamp(selected)
        assert selected['text'] == fixture['s5_text']
    def complete(config, messages, schema):
        data = json.loads(messages[-1]['content']); calls.append(copy.deepcopy(data))
        if 'blocks' not in data: return json.dumps(merge_result(data), ensure_ascii=False)
        body = '\n'.join(block['text'] for block in data['blocks'])
        assert '证据边界：' not in body and '图⽂限制：' not in body
        assert '魔⽅智脑' in body and 'AI for Process' in body and '未来' in body
        ids = [block['id'] for block in data['blocks']]
        return json.dumps({'sections': [
            {'chapter': 5, 'summary': 'DC·AI创新中心以魔方智脑统一驱动，提供基础设施、模型和应用平台的全栈方案；AI for Process为其流程再造规划。', 'block_ids': ids},
            {'chapter': 6, 'summary': '生态中心已汇聚教育、汽车、办公、仓储、物流等场景，首批企业签约入驻；未来扩展应用属于计划。', 'block_ids': ids}]}, ensure_ascii=False)
    monkeypatch.setattr(model, 'completion', complete)
    monkeypatch.setattr(sources, 'resolve_model_record', lambda _: {'api_key': 'synthetic-only', 'base_url': 'http://127.0.0.1:1/v1'})
    sources.process_source(pid, 'attachment', sid, fingerprint, retry=True)
    with get_db() as conn:
        selected_after = sources.source(conn, pid, 'attachment', sid)
        assert selected_after['text'] == selected['text'] and sources.stamp(selected_after) == fingerprint
        after = {r['source_id']:dict(r) for r in conn.execute("SELECT * FROM partner_profile_sources WHERE partner_id=? AND source_kind='attachment'", (pid,))}
        assert len(after) == 6 and after[sid]['state'] == 'ready'
        assert all(after[key] == before[key] for key in before if key != sid)
        assert after[sid]['source_fingerprint'] == before[sid]['source_fingerprint']
        for unit in json.loads(after[sid]['sections_json']):
            assert all(quote in selected['text'] and '证据边界：' not in quote for quote in unit['quotes'])
    headers = auth_headers(admin)
    merged = client.post(f'/partners/{pid}/profile', headers=headers)
    assert merged.status_code == 200, merged.text
    assert len(calls) == 2 and 'blocks' not in calls[-1]
    with get_db() as conn:
        saved = dict(conn.execute('SELECT ai_profile,profile_chapter_meta FROM partners WHERE id=?', (pid,)).fetchone())
    repeat = client.post(f'/partners/{pid}/profile', headers=headers)
    assert repeat.status_code == 200 and len(calls) == 2
    with get_db() as conn:
        assert dict(conn.execute('SELECT ai_profile,profile_chapter_meta FROM partners WHERE id=?', (pid,)).fetchone()) == saved
    record(root, 'SIX-CACHE-RETRY-MERGE.json', {'source_count': 6, 's5_native_sha256': fixture['s5_sha256'],
        's5_source_fingerprint': fingerprint, 'other_sources_unchanged': True, 'actual_inputs': calls,
        'saved': saved, 'logical_mock_stages': 2, 'repeat_stages': 0, 'provider_calls': 0,
        'scope': 'Exact archived native/source rows and fingerprints in owned test schema. Formal uploads are not restored.'})
