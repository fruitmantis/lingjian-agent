"""Real PG recovery/retry races; only model responses and scheduling are controlled."""
import inspect
import json
import threading
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
import pytest

from backend.app import development_model
from backend.app.database import get_db, recover_stale_tasks
from backend.app.postgres_storage import Connection
from backend.app.routers import match
from .conftest import make_partner, make_user, recommendation
from .support.model_test_boundary import require_test_database


def direct(*, readonly=True):
    url = require_test_database()
    return psycopg.connect(host=url.host, port=url.port or 5432, dbname=url.database,
        user=url.username, password=url.password, row_factory=dict_row,
        options=url.query['options'] + (' -cdefault_transaction_read_only=on' if readonly else ''),
        application_name='match_late_write_regression', connect_timeout=5)


def state(task_id):
    # Independent connection, raw persisted rows including progress/errors and counts.
    with direct() as conn:
        return {
            'task': conn.execute('SELECT * FROM match_records WHERE id=%s', (task_id,)).fetchone(),
            'snapshot': json.loads(conn.execute('SELECT value FROM app_metadata WHERE key=%s',
                ('match_understanding:' + task_id,)).fetchone()['value']),
            'demand': conn.execute('SELECT * FROM demand_profiles WHERE match_record_id=%s ORDER BY id', (task_id,)).fetchall(),
            'opportunity': conn.execute('SELECT * FROM project_opportunities WHERE match_record_id=%s ORDER BY id', (task_id,)).fetchall(),
            'tags': conn.execute('SELECT * FROM capability_tag_suggestions ORDER BY id').fetchall(),
        }


def expire(task_id):
    with direct(readonly=False) as conn:
        conn.execute("UPDATE match_records SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=%s", (task_id,))
    assert recover_stale_tasks(record_id=task_id, stale_after_seconds=1) == 1
    assert state(task_id)['task']['task_status'] == 'failed'


@pytest.fixture
def scenario(client, monkeypatch):
    user = make_user('late-write-owner')
    make_partner()
    current = {'marker': 'OLD'}
    calls = []

    def complete(config, messages, schema):
        marker = current['marker']
        calls.append((marker, schema['title']))
        # Model waiting must never own the schema writer lock.
        with direct() as probe:
            assert probe.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(current_database() || '.' || current_schema(),179183912)) AS ok").fetchone()['ok']
        if schema['title'] == 'MatchUnderstanding':
            value = {'in_scope': True, 'facts': {'technicalNeeds': marker}, 'tag_suggestions': [
                {'suggestedName': '合成迟到标签_' + marker, 'description': marker, 'evidenceText': '合成'}]}
        elif schema['title'] == 'InitialSelection':
            value = {'candidates': [{'partnerId': 'partner-1', 'verificationFocus': '核实数据库迁移'}]}
        else:
            assert schema['title'] == 'MatchAnswer'
            value = {'answer': '合成答复_' + marker, 'gapAnalysis': marker, 'supplyStatus': 'partial',
                'recommendations': [{**recommendation(), 'evidenceCases': [], 'evidenceDeliverables': []}]}
        return json.dumps(value, ensure_ascii=False)

    monkeypatch.setattr(development_model, 'completion', complete)
    return user, current, calls


POINTS = ('demand_profiles', 'project_opportunities', 'capability_tag_suggestions')


@pytest.mark.parametrize('point', POINTS)
@pytest.mark.parametrize('ending', ('retry', 'recovered_only', 'late_error'))
def test_old_enrichment_cannot_write_after_recovery(scenario, monkeypatch, point, ending, record_property):
    user, current, calls = scenario
    entered, release = threading.Event(), threading.Event()
    guard = match._require_match_run
    execute = Connection.execute
    old_thread = []
    reached, after_release_writes, checked = [], [], []

    def guarded(conn, task_id, run_id, allowed_statuses=('matching', 'enriching')):
        caller = inspect.currentframe().f_back
        location = (caller.f_locals['table'] if caller.f_code.co_name == '_save_derivative'
            else 'capability_tag_suggestions' if caller.f_code.co_name == '_generate_tag_suggestions' else None)
        del caller
        if location == point and not entered.is_set():
            old_thread.append(threading.get_ident())
            reached.append((location, run_id))
            # This is the actual save boundary, after extraction but BEFORE taking the lock.
            assert not conn.locked and not conn.connection.in_transaction()
            entered.set()
            assert release.wait(20), 'test did not release the old execution'
            if ending == 'late_error':
                raise RuntimeError('synthetic late extraction/save error')
        result = guard(conn, task_id, run_id, allowed_statuses)
        assert conn.locked
        actual = conn.connection.exec_driver_sql('SELECT current_database(),current_schema(),pg_backend_pid()').one()
        expected = require_test_database()
        assert actual[:2] == (expected.database, expected.query['options'].removeprefix('-csearch_path='))
        checked.append({'point': location, 'run_id': run_id, 'database': actual[0], 'schema': actual[1], 'pid': actual[2]})
        return result

    def observed(conn, sql, parameters=()):
        if old_thread and threading.get_ident() == old_thread[0] and release.is_set() and sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')):
            after_release_writes.append(sql)
        return execute(conn, sql, parameters)

    monkeypatch.setattr(match, '_require_match_run', guarded)
    monkeypatch.setattr(Connection, 'execute', observed)
    request = match.TaskCreateRequest(requestId=uuid4(), requirement='合成数据库迁移，验证迟到写入')
    accepted = match.create_task(request, user)
    try:
        assert entered.wait(8), 'old execution never reached the requested save boundary'
        assert reached == [(point, accepted.runId)]
        expire(accepted.recordId)
        if ending != 'recovered_only':
            # Change synthetic inputs through PG so real retry invalidates both
            # understanding and candidate snapshots (opportunity/tags use facts).
            with direct(readonly=False) as conn:
                conn.execute("UPDATE partners SET intro='合成更新：数据库迁移和回退经验' WHERE id='partner-1'")
                assert conn.execute("UPDATE capability_tags SET name='数据库（合成字典更新）' WHERE name='数据库'").rowcount == 1
            current['marker'] = 'NEW'
            retried = match.retry_match_record(accepted.recordId, user)
            assert retried.taskStatus == 'ready'
        before = state(accepted.recordId)
        run_id = before['snapshot']['progress']['run_id']
        if ending == 'recovered_only':
            assert run_id == accepted.runId
            assert before['task']['last_error_stage'] == 'interrupted'
        else:
            assert run_id != accepted.runId
            assert len(before['demand']) == len(before['opportunity']) == 1
            assert before['demand'][0]['gap_analysis'] == 'NEW'
            assert before['opportunity'][0]['technical_needs'] == 'NEW'
            assert sum(t['suggested_name'] == '合成迟到标签_NEW' for t in before['tags']) == 1
            assert all(t['occurrence_count'] == 1 for t in before['tags'])
            assert before['task']['task_status'] == 'ready'
            assert before['task']['last_error_stage'] is before['task']['last_error_details'] is None
            assert ('NEW', 'MatchUnderstanding') in calls and ('NEW', 'MatchAnswer') in calls
    finally:
        release.set()
        match.executor.shutdown(wait=True)
    assert state(accepted.recordId) == before
    assert after_release_writes == []
    record_property('independent_pg_evidence', json.dumps({'point': point, 'ending': ending,
        'reached_old_run': reached, 'final_run': run_id, 'connections': checked,
        'old_writes_after_release': len(after_release_writes), 'model_calls': calls,
        'counts': {k: len(before[k]) for k in ('demand', 'opportunity', 'tags')}}, ensure_ascii=False))


def test_current_run_saves_all_derivatives_and_replay_is_idempotent(scenario):
    user, current, calls = scenario
    request = match.TaskCreateRequest(requestId=uuid4(), requirement='合成当前执行幂等验证')
    accepted = match.create_task(request, user)
    match.executor.shutdown(wait=True)
    first = state(accepted.recordId)
    assert first['task']['task_status'] == 'ready'
    assert first['snapshot']['progress']['run_id'] == accepted.runId
    assert len(first['demand']) == len(first['opportunity']) == len(first['tags']) == 1
    assert first['demand'][0]['gap_analysis'] == first['opportunity'][0]['technical_needs'] == 'OLD'
    assert first['tags'][0]['occurrence_count'] == 1
    count = len(calls)
    assert match.create_task(request, user).runId == accepted.runId
    with pytest.raises(match._MatchExecutionLost):
        match._execute_match(accepted.recordId, request.requirement, first['task']['created_at'], accepted.runId)
    assert len(calls) == count
    assert state(accepted.recordId) == first


def test_queued_old_worker_keeps_original_run_identity(scenario, monkeypatch):
    user, current, calls = scenario
    queued = []
    monkeypatch.setattr(match.executor, 'submit', lambda fn, *args: queued.append((fn, args)))
    accepted = match.create_task(match.TaskCreateRequest(requestId=uuid4(), requirement='合成排队旧执行'), user)
    expire(accepted.recordId)
    current['marker'] = 'NEW'
    assert match.retry_match_record(accepted.recordId, user).taskStatus == 'ready'
    before = state(accepted.recordId)
    count = len(calls)
    assert len(queued) == 1 and queued[0][1][-1] == accepted.runId
    queued[0][0](*queued[0][1])
    assert len(calls) == count and state(accepted.recordId) == before


def test_late_model_error_cannot_fail_completed_retry(scenario, monkeypatch):
    user, current, calls = scenario
    entered, release = threading.Event(), threading.Event()
    complete = development_model.completion

    def delayed(config, messages, schema):
        if current['marker'] == 'OLD' and schema['title'] == 'MatchAnswer':
            entered.set()
            assert release.wait(20)
            raise RuntimeError('synthetic late provider failure')
        return complete(config, messages, schema)

    monkeypatch.setattr(development_model, 'completion', delayed)
    accepted = match.create_task(match.TaskCreateRequest(requestId=uuid4(), requirement='合成迟到模型错误'), user)
    try:
        assert entered.wait(8)
        expire(accepted.recordId)
        current['marker'] = 'NEW'
        assert match.retry_match_record(accepted.recordId, user).taskStatus == 'ready'
        before = state(accepted.recordId)
        assert before['demand'][0]['gap_analysis'] == 'NEW'
        assert before['snapshot']['progress']['run_id'] != accepted.runId
    finally:
        release.set()
        match.executor.shutdown(wait=True)
    assert state(accepted.recordId) == before


def test_retry_claim_rolls_back_state_when_new_run_cannot_be_saved(scenario, monkeypatch):
    from sqlalchemy.exc import IntegrityError
    from .postgres_support import install_failure
    user, _, _ = scenario
    monkeypatch.setattr(match.executor, 'submit', lambda *args: None)
    accepted = match.create_task(match.TaskCreateRequest(requestId=uuid4(), requirement='合成重试原子切换'), user)
    expire(accepted.recordId)
    before = state(accepted.recordId)
    with get_db() as conn:
        install_failure(conn, 'app_metadata', 'UPDATE', when="WHEN (NEW.key LIKE 'match_understanding:%')")
    with pytest.raises(IntegrityError, match='synthetic failure'):
        match.retry_match_record(accepted.recordId, user)
    assert state(accepted.recordId) == before
