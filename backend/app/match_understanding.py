"""One facts extraction shared by matching and its existing derivative records."""
import json
from time import perf_counter
from backend.business import matching
from backend.business.matching_types import (
    ProjectFacts, TagSuggestion, MatchUnderstanding, Candidate, MatchAnswer, InitialCandidate, InitialSelection,
)
from .database import get_db
from .business_taxonomy import taxonomy_prompt
from .model_resolver import resolve_model_record, configuration_stamp
from . import development_model
from . import partner_match_context as match_context
from .ai_client import last_retry_count, reset_retry_count
from .development_lifecycle import fingerprint
from .error_diagnostics import bind_context
from .task_failures import PublicTaskError
from .scope_gate import MESSAGES
from fastapi import HTTPException


def load(conn, task_id):
    row=conn.execute('SELECT value FROM app_metadata WHERE key=?',('match_understanding:'+task_id,)).fetchone()
    return json.loads(row[0]) if row else None


def save(conn, task_id, snapshot):
    conn.execute('INSERT INTO app_metadata(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                 ('match_understanding:'+task_id,json.dumps(snapshot,ensure_ascii=False)))


def prepare(requirement, cached=None):
    start=perf_counter()
    config=resolve_model_record('partner_match');model=configuration_stamp(config)
    with get_db() as conn:
        tags=[r['name'] for r in conn.execute('SELECT name FROM capability_tags WHERE enabled=1 ORDER BY name')]
    stamp=fingerprint({'requirement':requirement,'tags':tags})
    if cached and cached.get('stamp')==stamp and cached.get('model')==model:
        return cached
    bind_context(stage='understanding')
    try:
        messages=matching.understanding_messages(requirement,tags,taxonomy_prompt())
        schema=MatchUnderstanding.model_json_schema()
        chars,tokens=match_context.input_metrics(config,messages,schema)
        prepared=round((perf_counter()-start)*1000)
        call_start=perf_counter()
        reset_retry_count()
        try:
            from .runtime_bridge import execute_stage
            raw=execute_stage('match','understanding',{'requirement':requirement,'standard_tags':tags},{**config,'_runtime_preflight':lambda: _tags_current(tags)},lambda: development_model.completion({**config, '_match_request': True},messages,schema))
        finally:
            match_context.log_stage('understanding',0,chars,tokens,prepared,
                                    round((perf_counter()-call_start)*1000),last_retry_count())
        result=MatchUnderstanding.model_validate_json(raw).model_dump()
        if not result['in_scope']:
            return {'stamp':stamp,'model':model,'understanding':result,'scope_message':MESSAGES['partner_match']}
        matching.validate_understanding(result,requirement,tags)
        return {'stamp':stamp,'model':model,'understanding':result}
    except HTTPException:raise
    except Exception as error:raise PublicTaskError(error) from error


def _tags_current(tags):
    with get_db() as conn:
        return tags==[r['name'] for r in conn.execute('SELECT name FROM capability_tags WHERE enabled=1 ORDER BY name')]
