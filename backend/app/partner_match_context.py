"""Small, revision-bound matching summaries and local evidence selection."""

import json
import logging
import math
import re
from urllib.parse import urlsplit


from .ai_client import completion_payload, last_retry_count, reset_retry_count
from .development_engine import terms
from .business_taxonomy import project_partner
from .model_resolver import model_config_from_record, resolve_model_record
from .task_failures import MatchInputBudgetError


DETAIL_CHAR_LIMIT = 25_000
DETAIL_PARTNER_TARGET = 1_500
# DeepSeek's published Flash context is 1,048,576 tokens. Other providers are
# held to a deliberately smaller local ceiling until their capacity is known.
DEEPSEEK_CONTEXT_TOKENS = 1_048_576
UNKNOWN_CONTEXT_CEILING = 32_768
_LOG = logging.getLogger('uvicorn.error')


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


def checked_config(config: dict, messages: list[dict], schema: dict, char_limit: int):
    resolved = model_config_from_record(config)
    chars, estimated_tokens = input_metrics(config, messages, schema)
    host = urlsplit(resolved.base_url).hostname
    context_ceiling = (DEEPSEEK_CONTEXT_TOKENS if host == 'api.deepseek.com' and
                       resolved.model in ('deepseek-v4-flash', 'deepseek-flash') else UNKNOWN_CONTEXT_CEILING)
    # Thinking and final content share the output allowance. Short business JSON
    # does not imply short reasoning: use the saved limit within remaining context.
    output_tokens = min(resolved.max_tokens, context_ceiling - estimated_tokens)
    if chars > char_limit or output_tokens <= 0:
        raise MatchInputBudgetError(f'模型输入超过本阶段预算（字符 {chars}/{char_limit}，估算输入 Token {estimated_tokens} + 输出预留 {output_tokens}/{context_ceiling}），任务已保留，请调整资料后重试')
    return {**config, '_match_output_tokens': output_tokens}, chars, estimated_tokens


def log_stage(stage: str, partner_count: int, chars: int, estimated_tokens: int,
              preparation_ms: int, call_ms: int, retries: int):
    # Metadata only; never log the prompt, source text, or partner names.
    _LOG.info('MATCH_STAGE %s', json.dumps({
        'stage': stage, 'partner_count': partner_count, 'input_chars': chars,
        'estimated_input_tokens': estimated_tokens, 'preparation_ms': preparation_ms,
        'call_ms': call_ms, 'retry_count': retries,
    }, separators=(',', ':')))


def recall_candidates(conn, requirement: str, facts: dict, limit: int = 12) -> list[dict]:
    """PG searches full current contribution text and tags before any candidate model call."""
    query_terms=sorted(terms(requirement+' '+json.dumps(facts,ensure_ascii=False))-
                       terms('未知 现有资料 伙伴 推荐 项目 需要 希望 请帮'))
    if not query_terms:
        return []
    # Query term incidence in PG; rare capability terms outweigh common tag overlaps.
    # A source fingerprint is refreshed transactionally on writes; pending sources are excluded.
    corpus="""WITH corpus AS (
        SELECT p.id,p.name,p.capabilities,p.industries,p.service_areas,
        lower(concat_ws(' ',p.name,p.capabilities,p.industries,p.service_areas,
          (SELECT string_agg(s.sections_json,' ') FROM partner_profile_sources s
           WHERE s.partner_id=p.id AND s.state='ready' AND
           (s.source_kind!='word' OR s.source_id=(SELECT d.id FROM partner_documents d
             JOIN partner_profile_sources w ON w.partner_id=d.partner_id AND w.source_id=d.id AND w.source_kind='word' AND w.state='ready'
             WHERE d.partner_id=p.id AND d.doc_category='profile_import'
             ORDER BY d.created_at DESC,d.id DESC LIMIT 1))))) AS body
        FROM partners p WHERE p.status='active'
    ), terms AS (SELECT value AS token FROM jsonb_array_elements_text(CAST(? AS jsonb))),
    hits AS (SELECT c.id,t.token FROM corpus c CROSS JOIN terms t WHERE strpos(c.body,t.token)>0),
    weights AS (SELECT token,count(*) AS frequency FROM hits GROUP BY token),
    ranked AS (SELECT h.id,sum((1+ln(1+(SELECT count(*) FROM corpus)::float/w.frequency))*least(length(h.token),12)) AS score
        FROM hits h JOIN weights w USING(token) GROUP BY h.id)
    SELECT c.id,c.name,r.score FROM corpus c JOIN ranked r ON r.id=c.id
    ORDER BY r.score DESC,c.id LIMIT ?"""
    rows=conn.execute(corpus,(json.dumps(query_terms,ensure_ascii=False),limit))
    return [{'partnerId':r['id'],'verificationFocus':requirement[:150]} for r in rows]


def detailed_candidate(conn, partner_id: str, focus: str, requirement: str,
                       profile_budget: int = 900, case_count: int = 3):
    row = conn.execute("SELECT * FROM partners WHERE id=? AND status='active'", (partner_id,)).fetchone()
    if row is None:
        raise ValueError('Selected partner is unavailable')
    partner = project_partner(dict(row))
    cases = [dict(r) for r in conn.execute(
        'SELECT id,partner_id,title,description,created_at FROM cases '
        'WHERE partner_id=? AND visible=1 ORDER BY id', (partner_id,))]
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
    from .profile_sources import assembled
    profile = assembled(conn,partner_id,analysis=True)
    passages = select_passages(profile or '', query, profile_budget)
    context = {
        'partnerId': partner_id, 'name': partner['name'],
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
