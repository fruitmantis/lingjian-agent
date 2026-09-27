"""The same bounded, authorized task context for understanding and generation."""
from contextlib import nullcontext
import copy
import json
from .database import get_db
from . import development_lifecycle as life, enablement as resources
from .development_types import DevelopmentRequest


def identified_payload(conn, row):
    payload = json.loads(row['payload_json'])
    ids = [r['id'] for r in conn.execute('SELECT id FROM development_version_items WHERE version_id=? ORDER BY ordinal', (row['id'],))]
    for index, item in enumerate(i for stage in payload['stages'] for i in stage['items']):
        item.setdefault('item_id', ids[index])
    return payload


def exchanges(conn, plan, stored):
    history = copy.deepcopy(stored.get('_conversation', []))
    for row in conn.execute("SELECT r.submission_id,r.input_snapshot,r.created_at,v.id,v.payload_json FROM development_runs r JOIN development_versions v ON v.run_id=r.id WHERE r.plan_id=? AND r.run_type='revise' ORDER BY r.created_at,r.id", (plan['id'],)):
        snapshot = json.loads(row['input_snapshot'])
        payload = json.loads(row['payload_json'])
        history.append({'submission_id': row['submission_id'], 'version_id': row['id'], 'message': snapshot.get('instruction',''),
                        'answer': payload.get('revision_answer') or payload.get('answer',''), 'created_at': row['created_at']})
    return sorted(history, key=lambda item: item['created_at'])


def _model_readable(conn, row):
    for ref in json.loads(row['dependency_json']):
        try: resources.resolve_reference(conn, ref['source_type'], ref['source_id'], ref['source_version'], 'model')
        except Exception as error:
            from fastapi import HTTPException
            if isinstance(error, HTTPException): return False
            raise
    return True


def load(request, user, *, plan_id=None, base=None, message='', connection=None):
    from . import development_engine as engine
    from .development_views import protected, version_row, REVOKED
    from .enablement_catalog import context
    with (nullcontext(connection) if connection is not None else get_db()) as conn:
        if connection is None:conn.execute('BEGIN')
        blocked = engine.blocked_fragments(conn)
        profile = engine.profile_context(conn, request)
        tags = [dict(t) for t in conn.execute('SELECT id,name FROM capability_tags WHERE enabled=1 ORDER BY id')]
        current = None; payload = None; history = []
        effective = copy.deepcopy(request)
        if plan_id and base:
            plan = life.authorize(conn, plan_id, user)
            if plan['current_version_id'] != base: life.fail(409, '版本冲突：请重新载入当前建议')
            row = version_row(conn, plan, base)
            if protected(conn, row): life.fail(409, REVOKED)
            payload = identified_payload(conn, row)
            stored = json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?', (plan['request_id'],)).fetchone()[0])
            if not request.get('_explicit_request'):effective.update(payload.get('effective_request', {}))
            # A newer explanation can retain an effective requirement without creating a Version.
            if not request.get('_explicit_request') and stored.get('_effective_version_id') == base:
                effective.update(stored.get('_effective_request', {}))
            current = {'version_id': base, 'answer': '', 'resources': [], 'content_unavailable': not _model_readable(conn, row) or (not request.get('model_input_allowed') and payload.get('effective_request',{}).get('model_input_allowed',False))}
            if not current['content_unavailable']:
                current['answer'] = payload.get('answer') or '\n\n'.join(filter(None, [payload.get('analysis',{}).get('interpretation'), *[f.get('name','')+'：'+f.get('reason','') for f in payload.get('analysis',{}).get('priorities',[])]]))
                for index, item in enumerate(i for s in payload['stages'] for i in s['items']):
                    source = resources.resolve_reference(conn, item['source_type'], item['source_id'], item['source_version'], 'model')
                    current['resources'].append({**source, 'item_id': item['item_id'], 'position': index+1, 'focus': item.get('focus',''), 'reason': item['reason']})
                for exchange in exchanges(conn, plan, stored):
                    old = version_row(conn, plan, exchange['version_id'])
                    if _model_readable(conn, old):
                        history.append({k:exchange[k] for k in ('message','answer')})
                history = history[-3:]  # Complete pairs; never cut an answer midway.
        effective = {k:v for k,v in effective.items() if k in DevelopmentRequest.model_fields}
        # Used only as invalidation fingerprints, never sent to the provider.
        state = {
            'resources': [dict(r) for r in conn.execute('SELECT * FROM enablement_resources ORDER BY id')],
            'cases': [dict(r) for r in conn.execute('SELECT id,visible,updated_at FROM cases ORDER BY id')],
            'partner': dict(conn.execute('SELECT * FROM partners WHERE id=?', (request['target_partner_id'],)).fetchone()),
        }
    if request.get('model_input_allowed'):
        source = context(user, request['target_partner_id'], request.get('source_task_id'), request.get('source_case_id'), request.get('source_case_version'))
        if source.get('project'):
            profile['source_project'] = {k:engine.safe_text(source['project'].get(k), blocked) for k in ('requirement','risk_notes','risk_status')}
    data = {'request': engine.request_projection(effective), 'constraints': effective.get('constraints', {}),
            'profile': profile, 'formal_tags': tags, 'current': current, 'recent_exchanges': history, 'message': message or effective['development_direction']}
    engine.guard(data, blocked)
    if len(life.dump(data)) > 60000: life.fail(422, '当前任务上下文过长，请缩小本次讨论范围。')
    return {'input': data, 'stamp': life.fingerprint({'input':data,'state':state}), 'request':effective,
            'payload':payload, 'blocked':blocked, 'profile':profile, 'tags':tags}
