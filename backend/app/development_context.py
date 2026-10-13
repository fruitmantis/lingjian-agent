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


def _model_readable(conn,row):
    from .profile_sources import profile_dependency_valid
    refs=json.loads(row['dependency_json'])
    for ref in refs:
        if ref.get('dependency_kind')=='profile_source':
            if not profile_dependency_valid(conn,ref):return False
            continue
        try:
            resources.resolve_reference(conn,ref['source_type'],ref['source_id'],ref['source_version'],'model')
            if ref['source_type']!='case' and 'authorization_epoch' in ref:
                head=resources.row_for(conn,'resource',ref['source_id'])
                if head['authorization_epoch']!=ref['authorization_epoch']:return False
        except Exception as error:
            from fastapi import HTTPException
            if isinstance(error,HTTPException):return False
            raise
    return True


def load(request, user, *, plan_id=None, base=None, message='', connection=None):
    from . import development_engine as engine
    from .development_views import protected, version_row, REVOKED
    from .enablement_catalog import context
    with (nullcontext(connection) if connection is not None else get_db()) as conn:
        if connection is None:conn.begin_read()
        blocked = engine.blocked_fragments(conn)
        profile = engine.profile_context(conn, request)
        tags = [dict(t) for t in conn.execute('SELECT id,name FROM capability_tags WHERE enabled=1 ORDER BY id')]
        current = None; payload = None; history = []; saved_dependencies=[]
        effective = copy.deepcopy(request)
        if plan_id and base:
            plan = life.authorize(conn, plan_id, user)
            if plan['current_version_id'] != base: life.fail(409, '版本冲突：请重新载入当前建议')
            row = version_row(conn, plan, base)
            if protected(conn, row): life.fail(409, REVOKED)
            payload = identified_payload(conn, row)
            saved_dependencies=json.loads(row['dependency_json'])
            stored = json.loads(conn.execute('SELECT payload_json FROM development_requests WHERE id=?', (plan['request_id'],)).fetchone()[0])
            if not request.get('_explicit_request'):effective.update({k:v for k,v in payload.get('effective_request', {}).items() if k not in ('development_direction','development_goal')})
            # A newer explanation can retain an effective requirement without creating a Version.
            if not request.get('_explicit_request') and stored.get('_effective_version_id') == base:
                effective.update({k:v for k,v in stored.get('_effective_request', {}).items() if k not in ('development_direction','development_goal')})
            current = {'version_id': base, 'answer': '', 'resources': [], 'content_unavailable': not _model_readable(conn, row) or (not request.get('model_input_allowed') and payload.get('effective_request',{}).get('model_input_allowed',False))}
            if not current['content_unavailable']:
                current['answer'] = payload.get('answer') or '\n\n'.join(filter(None, [payload.get('understanding',payload.get('analysis',{})).get('interpretation'), *[f.get('name','')+'：'+f.get('reason','') for f in payload.get('understanding',payload.get('analysis',{})).get('priorities',[])]]))
                current['presentation'] = {key:copy.deepcopy(payload.get(key,[])) for key in ('resource_gaps','next_steps')}
                type_positions = {}
                for index, item in enumerate(i for s in payload['stages'] for i in s['items']):
                    source = resources.resolve_reference(conn, item['source_type'], item['source_id'], item['source_version'], 'model')
                    kind = item['source_type']
                    type_positions[kind] = type_positions.get(kind, 0)+1
                    current['resources'].append({**source, 'item_id': item['item_id'], 'position': index+1, 'type_position': type_positions[kind], 'reference_label': {'course':'课程','lab':'实验','case':'案例'}[kind]+str(type_positions[kind])+'｜'+source['title'], 'focus': item.get('focus',''), 'reason': item['reason'], 'note': item.get('note','')})
                # Keep one complete authorized pair for ordinary continuation.
                # Stored history stays intact; current Version alone defines item order.
                for exchange in reversed(exchanges(conn, plan, stored)):
                    old = version_row(conn, plan, exchange['version_id'])
                    if _model_readable(conn, {'dependency_json':json.dumps(exchange['dependencies'])} if 'dependencies' in exchange else old):
                        history.append({'message':exchange['message'],'answer_role':'past_assistant',**({'answer_ref':'current.answer'} if exchange['answer']==current['answer'] else {'answer':exchange['answer']})})
                        break
        effective = {k:v for k,v in effective.items() if k in DevelopmentRequest.model_fields}
        # Used only as invalidation fingerprints, never sent to the provider.
        state = {
            'resources': [dict(r) for r in conn.execute('SELECT * FROM enablement_resources ORDER BY id')],
            'cases': [dict(r) for r in conn.execute('SELECT id,visible,updated_at FROM cases ORDER BY id')],
            'partner': dict(conn.execute('SELECT * FROM partners WHERE id=?', (request['target_partner_id'],)).fetchone()) if request['target_partner_id'] is not None else None,
        }
    if request.get('model_input_allowed'):
        source = context(user, request['target_partner_id'], request.get('source_task_id'), request.get('source_case_id'), request.get('source_case_version'))
        if source.get('project'):
            profile['source_project'] = {k:engine.safe_text(source['project'].get(k), blocked) for k in ('requirement','risk_notes','risk_status')}
    data = {'request': engine.request_projection(effective), 'constraints': effective.get('constraints', {}),
            'profile': {k:v for k,v in profile.items() if not k.startswith('_')}, 'formal_tags': tags, 'current': current, 'recent_exchanges': history, 'message': message}
    engine.guard(data, blocked)
    return {'input': data, 'stamp': life.fingerprint({'input':data,'state':state}), 'request':effective,
            'request_stamp':life.fingerprint({'request':effective,'base':base,'message':message}),'dependencies':saved_dependencies,'payload':payload, 'blocked':blocked, 'profile':profile, 'tags':tags}
