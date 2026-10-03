"""Small, revision-bound matching summaries and local evidence selection."""

import json
import logging
import math
import re
from datetime import datetime, timezone
from time import perf_counter
from urllib.parse import urlsplit

from pydantic import Field

from . import development_model
from .ai_client import completion_payload, last_retry_count, reset_retry_count
from .database import get_db
from .development_engine import terms
from .development_lifecycle import fingerprint
from .business_taxonomy import project_partner
from .enablement import StrictModel
from .error_diagnostics import record_error
from .model_resolver import model_config_from_record, resolve_model_record
from .task_failures import MatchInputBudgetError


SUMMARY_PREFIX = 'partner_match_summary:'
INITIAL_CHAR_LIMIT = 60_000
DETAIL_CHAR_LIMIT = 25_000
SUMMARY_CHAR_LIMIT = 25_000
DETAIL_PARTNER_TARGET = 1_500
# DeepSeek's published Flash context is 1,048,576 tokens. Other providers are
# held to a deliberately smaller local ceiling until their capacity is known.
DEEPSEEK_CONTEXT_TOKENS = 1_048_576
UNKNOWN_CONTEXT_CEILING = 32_768
_LOG = logging.getLogger('uvicorn.error')


class MatchingSummary(StrictModel):
    text: str = Field(min_length=1, max_length=240)


def _source_stamp(partner: dict, cases: list[dict], deliverables: list[dict]) -> str:
    """Use maintained revisions; no all-partner full-text reads on initial selection."""
    fields = ('id', 'name', 'intro', 'capabilities', 'industries', 'service_areas',
              'materials_revision', 'profile_materials_revision', 'profile_updated_at', 'updated_at')
    return fingerprint({
        'partner': {key: partner.get(key) for key in fields},
        'cases': [{key: row.get(key) for key in ('id', 'title', 'updated_at', 'visible')} for row in cases],
        'deliverables': [{key: row.get(key) for key in ('id', 'filename', 'processed_at')} for row in deliverables],
    })


def sources(conn, partner_id: str, *, full_profile: bool = False):
    cols = ('*' if full_profile else 'id,name,intro,capabilities,industries,service_areas,materials_revision,profile_materials_revision,profile_updated_at,updated_at')
    row = conn.execute(f'SELECT {cols} FROM partners WHERE id=?', (partner_id,)).fetchone()
    if row is None:
        return None
    partner = dict(row)
    cases = [dict(r) for r in conn.execute(
        'SELECT id,title,updated_at,visible' + (',description' if full_profile else '') +
        ' FROM cases WHERE partner_id=? AND visible=1 ORDER BY id', (partner_id,))]
    deliverables = [dict(r) for r in conn.execute(
        'SELECT d.id,d.filename,d.processed_at FROM deliverables d JOIN cases c ON c.id=d.case_id '
        'WHERE c.partner_id=? AND c.visible=1 ORDER BY d.id', (partner_id,))]
    return partner, cases, deliverables, _source_stamp(partner, cases, deliverables)


def current_summary(conn, partner_id: str, stamp: str) -> str | None:
    row = conn.execute('SELECT value FROM app_metadata WHERE key=?', (SUMMARY_PREFIX + partner_id,)).fetchone()
    if not row:
        return None
    try:
        value = json.loads(row[0])
    except (TypeError, ValueError):
        return None
    return value.get('text') if value.get('source_fingerprint') == stamp and isinstance(value.get('text'), str) else None


def _passages(value: str, max_chunk: int = 900) -> list[str]:
    # Keep short paragraphs intact so a limitation cannot be detached from its claim.
    chunks = []
    for paragraph in re.split(r'\n+', value or ''):
        paragraph = paragraph.strip()
        if len(paragraph) <= max_chunk:
            if paragraph:
                chunks.append(paragraph)
            continue
        group = ''
        for sentence in re.split(r'(?<=[。！？；;])', paragraph):
            if group and len(group) + len(sentence) > min(650, max_chunk):
                chunks.append(group.strip())
                group = ''
            group += sentence
        if group.strip():
            chunks.append(group.strip())
    return list(dict.fromkeys(chunks))


def select_passages(value: str, query: str, limit: int) -> list[str]:
    chunks = _passages(value, min(900, limit))
    query_terms = terms(query)
    limitation = re.compile(r'但|不支持|未覆盖|尚无|限制|风险|不能|缺少|仅限')
    ranked = []
    for index, passage in enumerate(chunks):
        overlap = query_terms & terms(passage)
        score = sum(min(len(token), 6) for token in overlap)
        if limitation.search(passage):
            score += 4
        if not query_terms:
            score += 4 if re.search(r'能力|经验|交付|限制|风险|不支持|未覆盖|案例', passage) else 0
            score += index / max(len(chunks), 1)  # Include later evidence in generic summaries.
        ranked.append((score, index, passage))
    selected: set[int] = set()
    used = 0
    for _, index, passage in sorted(ranked, key=lambda item: (-item[0], item[1])):
        group = {index}
        if limitation.search(passage) and index:
            group.add(index - 1)
        if index + 1 < len(chunks) and limitation.search(chunks[index + 1]):
            group.add(index + 1)
        new = group - selected
        size = sum(len(chunks[i]) + 1 for i in new)
        if used + size <= limit:
            selected.update(new)
            used += size
    return [chunks[index] for index in sorted(selected)]


def _token_estimate(text: str) -> int:
    """Conservative estimate, not a provider tokenizer or billed token count."""
    chinese = len(re.findall(r'[\u3400-\u9fff]', text))
    return math.ceil(chinese * 1.2 + (len(text) - chinese) * 0.5 + 32)


def input_metrics(config: dict, messages: list[dict], schema: dict) -> tuple[int, int]:
    payload = completion_payload(model_config_from_record(config), messages, schema)
    packed = json.dumps(payload['messages'], ensure_ascii=False, separators=(',', ':'))
    return len(packed), _token_estimate(packed)


def checked_config(config: dict, messages: list[dict], schema: dict, char_limit: int, output_cap: int | None = None):
    resolved = model_config_from_record(config)
    chars, estimated_tokens = input_metrics(config, messages, schema)
    host = urlsplit(resolved.base_url).hostname
    context_ceiling = (DEEPSEEK_CONTEXT_TOKENS if host == 'api.deepseek.com' and
                       resolved.model in ('deepseek-v4-flash', 'deepseek-flash') else UNKNOWN_CONTEXT_CEILING)
    # Thinking and final content share the saved output allowance. Production
    # stages have no hidden caps; retain an explicitly supplied caller limit.
    available = context_ceiling - estimated_tokens
    output_tokens = min(resolved.max_tokens, max(0, available) if output_cap is None else output_cap)
    if chars > char_limit or output_tokens < 1 or estimated_tokens + output_tokens > context_ceiling:
        raise MatchInputBudgetError(f'模型输入超过本阶段预算（字符 {chars}/{char_limit}，估算输入 Token {estimated_tokens} + 输出预留 {output_tokens}/{context_ceiling}），任务已保留，请调整资料后重试')
    from .runtime_bridge import mode, initial_selection_output_limit, stage_output_limit
    runtime_stage = {'InitialSelection':'initial_selection', 'MatchAnswer':'detailed_review'}.get(schema.get('title'))
    if runtime_stage and mode('match') == 'runtime':
        data = json.loads(messages[-1]['content'])
        if runtime_stage == 'initial_selection':
            output_tokens = initial_selection_output_limit(data, output_tokens)
        else:
            try:
                output_tokens = stage_output_limit('match', runtime_stage, data, output_tokens)
            except ValueError as error:
                raise MatchInputBudgetError('详评完整 Runtime 消息超过输入预算，任务已保留') from error
    return {**config, '_match_output_tokens': output_tokens}, chars, estimated_tokens


def log_stage(stage: str, partner_count: int, chars: int, estimated_tokens: int,
              preparation_ms: int, call_ms: int, retries: int):
    # Metadata only; never log the prompt, source text, or partner names.
    _LOG.info('MATCH_STAGE %s', json.dumps({
        'stage': stage, 'partner_count': partner_count, 'input_chars': chars,
        'estimated_input_tokens': estimated_tokens, 'preparation_ms': preparation_ms,
        'call_ms': call_ms, 'retry_count': retries,
    }, separators=(',', ':')))


def compact_candidates(conn) -> list[dict]:
    """Every active partner enters AI initial selection, even without labels or summary."""
    ids = [row['id'] for row in conn.execute("SELECT id FROM partners WHERE status='active' ORDER BY id")]
    result = []
    for partner_id in ids:
        data = sources(conn, partner_id)
        if data is None:
            continue
        partner, cases, deliverables, stamp = data
        projected = project_partner(partner)
        summary = current_summary(conn, partner_id, stamp)
        intro = (partner.get('intro') or '').strip() if not summary else ''
        result.append({
            'partnerId': partner_id, 'name': partner['name'],
            'capabilities': projected.get('capabilities') or '',
            'industries': projected.get('industries') or '',
            'regions': projected.get('service_areas') or '',
            'summary': summary or '', 'intro': intro,
            'evidenceState': '摘要有效' if summary else '资料有限，待核实',
            'visibleCaseCount': len(cases), 'visibleDeliverableCount': len(deliverables),
        })
    return result


def detailed_candidate(conn, partner_id: str, focus: str, requirement: str,
                       profile_budget: int = 900, case_count: int = 3):
    row = conn.execute("SELECT * FROM partners WHERE id=? AND status='active'", (partner_id,)).fetchone()
    if row is None:
        raise ValueError('Selected partner is unavailable')
    partner = project_partner(dict(row))
    cases = [dict(r) for r in conn.execute(
        'SELECT id,partner_id,title,description,created_at FROM cases '
        'WHERE partner_id=? AND visible=1 ORDER BY id', (partner_id,))]
    hidden = conn.execute('SELECT COUNT(*) FROM cases WHERE partner_id=? AND visible=0', (partner_id,)).fetchone()[0]
    query = requirement + ' ' + focus
    query_terms = terms(query)
    def relevance(case):
        overlap = query_terms & terms((case['title'] or '') + ' ' + (case['description'] or ''))
        return sum(min(len(token), 6) for token in overlap)
    selected_cases = sorted(cases, key=lambda case: (-relevance(case), case['id']))[:case_count]
    evidence_cases = []
    evidence_deliverables = []
    for case in selected_cases:
        text = '；'.join(select_passages(case.get('description') or '', query, 250))
        evidence_cases.append({'id': case['id'], 'title': case['title'], 'relevantDescription': text})
        files = [dict(r) for r in conn.execute(
            'SELECT id,filename,? AS case_title FROM deliverables WHERE case_id=? ORDER BY id',
            (case['title'], case['id']))]
        files.sort(key=lambda item: (-sum(min(len(term), 6) for term in query_terms & terms(item['filename'])), item['id']))
        evidence_deliverables += files[:3]
    # A profile can reflect hidden cases, even if the case visibility changed later.
    # Do not send it in that situation; visible cases remain usable independently.
    profile = partner.get('ai_profile') if not hidden and partner.get('materials_revision') == partner.get('profile_materials_revision') else ''
    passages = select_passages(profile or '', query, profile_budget)
    context = {
        'partnerId': partner_id, 'name': partner['name'],
        'intro': ((partner.get('intro') or '').strip() if len((partner.get('intro') or '').strip()) <= 900
                  else '；'.join(select_passages(partner.get('intro') or '', query, 300))),
        'capabilities': partner.get('capabilities') or '',
        'industries': partner.get('industries') or '',
        'regions': partner.get('service_areas') or '',
        'verificationFocus': focus,
        'profilePassages': [{'source': f'partner:{partner_id}:profile:{index}', 'text': passage}
                            for index, passage in enumerate(passages, 1)],
        'visibleCases': evidence_cases,
        'deliverables': [{'id': d['id'], 'filename': d['filename'], 'caseTitle': d['case_title']}
                         for d in evidence_deliverables],
        'evidenceState': '资料有限' if not passages and not evidence_cases else '可核实',
    }
    return partner, context, selected_cases, evidence_deliverables


def generate_summary(partner_id: str) -> bool:
    """Independent best-effort call after a successfully committed profile update."""
    try:
        return _generate_summary(partner_id)
    except Exception as error:
        record_error(error, stage='match_summary')
        return False


def _generate_summary(partner_id: str) -> bool:
    start = perf_counter()
    with get_db() as conn:
        data = sources(conn, partner_id, full_profile=True)
    if data is None:
        return False
    partner, cases, deliverables, source_stamp = data
    with get_db() as conn:
        hidden_cases = conn.execute('SELECT COUNT(*) FROM cases WHERE partner_id=? AND visible=0', (partner_id,)).fetchone()[0]
    profile = (partner.get('ai_profile') or '') if not hidden_cases else ''
    passages = select_passages(profile, '', 18_000)
    if profile and not passages:
        record_error(ValueError('Profile has no complete passage within matching summary budget'), stage='match_summary')
        return False
    context = {
        'name': partner['name'], 'intro': partner.get('intro'),
        'capabilities': partner.get('capabilities'), 'industries': partner.get('industries'),
        'regions': partner.get('service_areas'),
        'profile_passages': passages,
        'visible_cases': [{'id': c['id'], 'title': c['title'],
                           'description': '；'.join(select_passages(c.get('description') or '', '', 250))} for c in cases],
        'deliverables': [d['filename'] for d in deliverables],
    }
    if not any((profile, partner.get('intro'), partner.get('capabilities'), cases, deliverables)):
        return False
    messages = [
        {'role': 'system', 'content': '仅根据给定资料写约200字的伙伴匹配摘要，突出真实能力、代表性经验和必要限制。不得从标签缺失推断无能力，不得编造。不复述资料开头；综合全文各处证据。资料不足要明确说资料有限。只返回指定JSON。'},
        {'role': 'user', 'content': json.dumps(context, ensure_ascii=False, separators=(',', ':'))},
    ]
    config = resolve_model_record('partner_profile')
    try:
        budgeted, chars, estimated = checked_config(config, messages, MatchingSummary.model_json_schema(), SUMMARY_CHAR_LIMIT)
        prepared = round((perf_counter() - start) * 1000)
        call_start = perf_counter()
        reset_retry_count()
        try:
            raw = development_model.completion(budgeted, messages, MatchingSummary.model_json_schema())
        finally:
            log_stage('match_summary', 1, chars, estimated, prepared,
                      round((perf_counter() - call_start) * 1000), last_retry_count())
        text = MatchingSummary.model_validate_json(raw).text.strip()
        with get_db() as conn:
            conn.lock_writer()
            latest = sources(conn, partner_id)
            if latest is None or latest[3] != source_stamp:
                raise ValueError('Partner summary source changed before persistence')
            conn.execute('INSERT INTO app_metadata(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                         (SUMMARY_PREFIX + partner_id, json.dumps({'text': text, 'source_fingerprint': source_stamp,
                         'generated_at': datetime.now(timezone.utc).isoformat()}, ensure_ascii=False)))
        return True
    except Exception as error:
        record_error(error, stage='match_summary')
        return False
