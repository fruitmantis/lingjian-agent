"""Small, revision-bound matching summaries and local evidence selection."""

import json
import logging
import hashlib
import math
import re
from urllib.parse import urlsplit


from .ai_client import completion_payload, last_retry_count, reset_retry_count
from .development_engine import terms
from .business_taxonomy import project_partner
from .model_resolver import model_config_from_record, resolve_model_record
from .task_failures import MatchInputBudgetError
from backend.business import matching


DETAIL_CHAR_LIMIT = 25_000
# DeepSeek's published Flash context is 1,048,576 tokens. Other providers are
# held to a deliberately smaller local ceiling until their capacity is known.
DEEPSEEK_CONTEXT_TOKENS = 1_048_576
UNKNOWN_CONTEXT_CEILING = 32_768
_LOG = logging.getLogger('uvicorn.error')


_QUALIFIER = re.compile(r'集团口径|企业自述|待核实|规划|尚未|未交付|未实施|未落地|未覆盖|不支持|不能|仅限|未来|计划|拟开发|self.report|planned|planning|not yet', re.I)


def _heading(text):
    return bool(text and len(text) <= 60 and not re.search(r'[。！？；;|\t]', text))


def _line_ranges(value):
    offset = 0
    rows = []
    for line in value.splitlines(keepends=True):
        rows.append((offset, offset + len(line), line))
        offset += len(line)
    return rows


def _native_blocks(value):
    """Original paragraph/table ranges; PDF soft wraps stay within one fact."""
    lines = _line_ranges(value)
    blocks, left = [], None
    def page(text):
        return bool(re.fullmatch(r'第\s*\d+\s*页', text))
    def title(text):
        return bool(_heading(text) and (
            text.startswith('#') or re.match(r'^(?:\d+[、.)）]|[一二三四五六七八九十]+[、）])', text)
            or re.fullmatch(r'\d{1,2}', text)))
    def finish(right):
        nonlocal left
        if left is not None:
            blocks.append((lines[left][0], lines[right-1][1]))
            left = None
    table = False
    for i, (_, _, line) in enumerate(lines):
        text = line.strip()
        if not text or page(text):
            finish(i); table = False
            continue
        if title(text):
            finish(i); table = False
        if left is None:
            left = i
        table = table or '\t' in line or '|' in line
        # A sentence-ending native line closes a paragraph. Wrapped lines and
        # native table rows remain continuous, including short numbers/titles.
        if not table and re.search(r'[。！？.!?][”"’\')）]*$', text):
            finish(i+1)
    finish(len(lines))
    return blocks


def _group_ranges(value, start, end):
    """One continuous native fact, with its adjacent title or table header."""
    blocks = _native_blocks(value)
    hit = [(a,b) for a,b in blocks if a < end and b > start]
    if not hit:
        # Page markers still have legal original offsets for existing quote readers.
        return [(start,end)] if 0 <= start < end <= len(value) else []
    left, right = hit[0][0], hit[-1][1]
    # A native heading/number hit belongs with the next original paragraph, even
    # across its blank separator; it is not packaged as a standalone number.
    if all(_heading(line.strip()) for line in value[left:right].splitlines() if line.strip()):
        following = next(((a,b) for a,b in blocks if a >= right),None)
        if following and not re.search(r'^第\s*\d+\s*页\s*$',value[right:following[0]],re.M):
            right = following[1]
            # A title followed by a native qualification paragraph still needs its
            # factual body; do not stop at "enterprise self-report / to verify".
            if _QUALIFIER.match(value[following[0]:following[1]].lstrip()):
                body = next(((a,b) for a,b in blocks if a >= right),None)
                if (body and not value[body[0]:body[1]].lstrip().startswith('#') and
                        not re.search(r'^第\s*\d+\s*页\s*$',value[right:body[0]],re.M)):
                    right = body[1]
    lines = _line_ranges(value)
    before = next((i for i,(_,b,_) in enumerate(lines) if b==left),None)
    after = next((i for i,(a,_,_) in enumerate(lines) if a==right),None)
    if before is not None and lines[before][2].strip() and _QUALIFIER.search(lines[before][2]):
        previous_block = next(((a,b) for a,b in reversed(blocks) if a < left and b >= lines[before][1]),None)
        if previous_block:
            left = previous_block[0]
    if after is not None and lines[after][2].strip() and _QUALIFIER.search(lines[after][2]):
        next_block = next(((a,b) for a,b in blocks if a <= lines[after][0] < b),None)
        if next_block:
            right = next_block[1]
    previous = [i for i, (_,b,text) in enumerate(lines) if b <= left and text.strip()]
    # The immediately preceding heading qualifies this paragraph. At most the
    # title and its wrapped continuation; never absorb a preceding menu/chapter.
    for i in reversed(previous[-2:]):
        text = lines[i][2].strip()
        if (not _heading(text) or text.startswith('>') or
                re.fullmatch(r'第\s*\d+\s*页', text)):
            break
        left = lines[i][0]
    return [(left,right)]


def _source_layout(value):
    """Recognize the saved webpage wrapper; no business-word or disclaimer filter."""
    lines = _line_ranges(value)
    archive = any(re.match(r'原始\s*URL\s*[:：]', text.strip(), re.I)
                  for _,_,text in lines[:12])
    if not archive:
        return 0,len(value),[]
    # The archive format has operation metadata, a navigation run, then an article
    # title/date. Keep mixed factual boundary text separately, exactly as saved.
    dates = [i for i,(_,_,text) in enumerate(lines)
             if re.fullmatch(r'\d{4}\s*/\s*\d{1,2}\s*/\s*\d{1,2}',text.strip())]
    if not dates:
        return 0,len(value),[]  # Unrecognized layout is retained, never cleaned.
    first = dates[0]
    start = lines[max(0,first-1)][0]
    end = len(value)
    for index in dates[1:]:
        previous = next((j for j in range(index-1,first,-1) if lines[j][2].strip()),None)
        if previous is not None and lines[previous][2].strip() in ('推荐阅读','相关阅读','相关推荐'):
            end = lines[previous][0]
            break  # An in-article date is a fact, not a footer boundary.
    qualifiers = []
    for i,(_,_,text) in enumerate(lines[:first]):
        if text.strip().startswith('证据边界：'):
            j=i+1
            while j<first and lines[j][2].strip() and not re.match(r'^[^：:\n]{1,12}[:：]',lines[j][2].strip()):
                j+=1
            qualifiers.append((lines[i][0],lines[j-1][1]))
            break
    return start,end,qualifiers


def _intro_ranges(value):
    """Keep the source's opening subject/project introduction as separate ranges."""
    start,end,qualifiers = _source_layout(value)
    lines = _line_ranges(value)
    headings = [a for a,_,text in lines if start < a < end and _heading(text.strip()) and
                (re.fullmatch(r'\d{1,2}',text.strip()) or
                 re.match(r'^(?:#{1,6}\s|\d+[、.)）]|[一二三四五六七八九十]+[、）])',text.strip()))]
    blocks = [(a,b) for a,b in _native_blocks(value) if start <= a < end]
    if start:
        # A webpage's pre-section introduction includes its title/date and project
        # setup. It is a native introductory section, not the full article.
        stop = headings[0] if headings else (blocks[1][1] if len(blocks)>1 else end)
        return qualifiers + [(start,stop)]
    # For extracted PDFs, keep the cover subject and the first factual paragraph;
    # agenda-only short lines do not become evidence. Other sources keep their
    # first paragraph. Whole native ranges are selected or skipped together.
    facts = [(a,b) for a,b in blocks if any(
        not _heading(line.strip()) or re.search(r'[:：]',line)
        for line in value[a:b].splitlines() if line.strip())]
    if not facts:
        return blocks[:1]
    pages = [(a,b) for a,b,text in lines if re.fullmatch(r'第\s*\d+\s*页',text.strip())]
    if len(pages)>1:
        cover = [(a,b) for a,b in blocks if pages[0][1] <= a < pages[1][0]]
        body = next(((a,b) for a,b in facts if a >= pages[1][1]),None)
        return cover + ([body] if body else [])
    first_line = next((text.strip() for _,_,text in lines if text.strip()),'')
    if not _heading(first_line):
        return []  # A generic body paragraph is not an identified distant introduction.
    first = facts[0]
    cover = blocks[:1] if blocks and blocks[0][1] <= first[0] else []
    return cover + [first]


def _merge_ranges(ranges):
    merged = []
    for a,b in sorted(set(ranges)):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0],max(b,merged[-1][1]))
        else:
            merged.append((a,b))
    return merged


def _normalized_spans(value, query_terms):
    """Map normalized recall hits back to untouched source-string offsets."""
    normalized = ''.join(c.lower() for c in value)
    positions = [(i, i + 1) for i, c in enumerate(value) for _ in c.lower()]
    for pattern, canonical in matching.normalization_rules():
        output, mapped, last = [], [], 0
        for hit in re.finditer(pattern, normalized):
            output.append(normalized[last:hit.start()]);mapped.extend(positions[last:hit.start()])
            output.append(canonical)
            mapped.extend([(positions[hit.start()][0], positions[hit.end()-1][1])] * len(canonical))
            last = hit.end()
        output.append(normalized[last:]);mapped.extend(positions[last:])
        normalized, positions = ''.join(output), mapped
    spans = set()
    for term in query_terms:
        start = 0
        while term and (index := normalized.find(term, start)) >= 0:
            spans.add((positions[index][0], positions[index + len(term) - 1][1]))
            start = index + len(term)
    return sorted(spans)


def passage_selection(value: str, query: str, limit: int, *, recall_terms=(), facts=None):
    # Compatibility for existing callers: selection uses retrieval positions only.
    spans = _normalized_spans(value, recall_terms or matching.recall_query(query, {})[0])
    groups = list(dict.fromkeys(tuple(_group_ranges(value, a, b)) for a, b in spans))
    chosen, used, omitted = [], 0, 0
    for index, ranges in enumerate(groups):
        size = sum(b-a for a,b in ranges)
        if used + size <= DETAIL_CHAR_LIMIT:
            chosen.append((index, ''.join(value[a:b] for a,b in ranges), True));used += size
        else:
            omitted += 1
    return chosen, {'complete': not omitted, 'omittedHitGroups': omitted,
                    'hitGroupCount': len(groups), 'selectedGroupCount': len(chosen)}


def select_passages(value: str, query: str, limit: int, *, facts=None) -> list[str]:
    return [p for _, p, _ in passage_selection(value, query, limit, facts=facts)[0]]


def _partner_values(partner):
    version = hashlib.sha256(json.dumps(
        {key: partner.get(key) for key in ('id','name','capabilities','industries','service_areas',
                                          'materials_revision','updated_at')},
        ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return [{'sourceRef': 'partner:' + partner['id'], 'source_version': version,
             'path': '/' + key, 'text': partner.get(key) or '', 'original': '',
             'kind': 'field', 'background': key != 'capabilities'}
            for key in ('name','capabilities','industries','service_areas')]


def _candidate_values(conn, partner):
    from .profile_sources import matching_values
    return _partner_values(partner) + matching_values(conn, partner['id'])


def provider_context(context):
    # Explicit business projection; engineering coverage and positions stay private.
    return {key: context[key] for key in (
        'partnerId', 'name', 'capabilities', 'industries', 'regions',
        'profilePassages', 'visibleCases', 'deliverables')
        if key in context}





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


def recall_candidates(conn, requirement: str, facts: dict, limit: int = 12,
                      *, diagnostics: dict | None = None) -> list[dict]:
    """Rank original grounded term hits in PG without a conjunctive phrase gate."""
    query_terms, _ = matching.recall_query(requirement, facts)
    info = diagnostics if diagnostics is not None else {}
    info.update(rules_version=matching.MATCHING_RULES_VERSION,
                keyword_count=len(query_terms),
                keyword_fingerprint=hashlib.sha256(json.dumps(query_terms,ensure_ascii=False,separators=(',', ':')).encode()).hexdigest(),
                candidate_order=[])
    if not query_terms:
        return []
    # Normalize the same controlled capability expressions in query and corpus.
    body = "body"
    parameters = []
    for pattern, canonical in matching.normalization_rules():
        body = "regexp_replace(" + body + ",?,?,'g')"
        parameters += [pattern, canonical]
    partners = [dict(r) for r in conn.execute("SELECT * FROM partners WHERE status='active' ORDER BY id")]
    values = {p['id']: _candidate_values(conn, p) for p in partners}
    valid_corpus = [{'id': p['id'], 'body': ' '.join(v['text'] for v in values[p['id']]).lower()} for p in partners]
    corpus = """WITH raw_corpus AS (
        SELECT * FROM jsonb_to_recordset(CAST(? AS jsonb)) AS x(id text,body text)
    ), corpus AS (SELECT id,""" + body + """ AS body FROM raw_corpus),
    terms AS (SELECT value AS token FROM jsonb_array_elements_text(CAST(? AS jsonb))),
    hits AS (SELECT c.id,t.token FROM corpus c
             CROSS JOIN terms t WHERE strpos(c.body,t.token)>0),
    weights AS (SELECT token,count(*) AS frequency FROM hits GROUP BY token),
    ranked AS (SELECT h.id,sum((1+ln(1+(SELECT count(*) FROM corpus)::float/w.frequency))*least(length(h.token),12)) AS score,
         jsonb_agg(h.token ORDER BY (1+ln(1+(SELECT count(*) FROM corpus)::float/w.frequency))*least(length(h.token),12) DESC,h.token) AS matched_terms
        FROM hits h JOIN weights w USING(token) GROUP BY h.id)
    SELECT id,score,matched_terms FROM ranked ORDER BY score DESC,id LIMIT ?"""
    rows = list(conn.execute(corpus, (json.dumps(valid_corpus,ensure_ascii=False), *parameters,
                                     json.dumps(query_terms,ensure_ascii=False),
                                     min(limit, 12))))
    info['candidate_order'] = [r['id'] for r in rows]
    selected = []
    for row in rows:
        hits = []
        for value in values[row['id']]:
            for start, end in _normalized_spans(value['text'], row['matched_terms']):
                hit = {key: value[key] for key in ('sourceRef','source_version','path')}
                hit.update(start=start, end=end)
                if hit not in hits:
                    hits.append(hit)
        selected.append({'partnerId': row['id'], 'verificationFocus': '依据本次完整需求评估',
                         'recallTerms': row['matched_terms'], 'hits': hits})
    return selected


def log_match_metadata(event: str, **values):
    # No original words, demand fragments or document text enter this logger.
    allowed = {'task_id','input_version','rules_version','keyword_count',
               'keyword_fingerprint','candidate_order','raw_recommendation_count',
               'valid_recommendation_count','rejection_count','evidence_references_filtered'}
    metadata = {key:value for key,value in values.items() if key in allowed}
    _LOG.info('MATCH_%s %s', event, json.dumps(metadata,ensure_ascii=False,separators=(',', ':')))


def detailed_candidate(conn, partner_id: str, focus: str, requirement: str,
                       profile_budget: int = 900, case_count: int = 3, *, recall_terms=(), facts=None, hits=None):
    row = conn.execute("SELECT * FROM partners WHERE id=? AND status='active'", (partner_id,)).fetchone()
    if row is None:
        raise ValueError('Selected partner is unavailable')
    original_partner = dict(row)
    partner = project_partner(original_partner)
    values = _candidate_values(conn, original_partner)
    by_position = {(v['sourceRef'],v['source_version'],v['path']):v for v in values}
    if hits is None:
        hits = []
        for value in values:
            for start,end in _normalized_spans(value['text'], recall_terms or matching.recall_query(requirement,{})[0]):
                hits.append({**{k:value[k] for k in ('sourceRef','source_version','path')},'start':start,'end':end})
    groups, omissions, background = [], [], []
    for index, hit in enumerate(hits):
        value = by_position.get(tuple(hit.get(k) for k in ('sourceRef','source_version','path')))
        start,end = hit.get('start'),hit.get('end')
        if not value or not isinstance(start,int) or not isinstance(end,int) or not 0 <= start < end <= len(value['text']):
            omissions.append({'reason':'source_position_unavailable','hitIndexes':[index]})
            continue
        # All partner fields are already sent whole in the fixed business fields.
        if value.get('background') or value['kind'] == 'field':
            background.append(index)
            continue
        hit_text = matching.normalize_recall_text(value['text'][start:end])
        priority = next((i for i,t in enumerate(recall_terms) if t in hit_text),len(recall_terms))
        group_text, group_path = value['text'], value['path']
        # Non-Word contributions are already literal ranges. Expand only where
        # they uniquely locate in the same original source; ambiguity is recorded.
        if value['kind'] not in ('word','field'):
            offset = value['original'].find(value['text'])
            if offset < 0:
                omissions.append({'reason':'original_range_unavailable','hitIndexes':[index]})
                continue
            if value['original'].count(value['text']) != 1:
                omissions.append({'reason':'ambiguous_original_range','hitIndexes':[index]})
                continue
            if value['original'].count(value['text']) == 1:
                group_text, group_path = value['original'], '/text'
                start,end = start+offset,end+offset
        body_start,body_end,_ = _source_layout(group_text)
        if not body_start <= start < end <= body_end:
            background.append(index)  # Recognized wrapper/menu/footer; raw source is untouched.
            continue
        ranges = [(max(a,body_start),min(b,body_end))
                  for a,b in _group_ranges(group_text,start,end)
                  if max(a,body_start) < min(b,body_end)]
        if not ranges:
            omissions.append({'reason':'source_group_unavailable','hitIndexes':[index]})
            continue
        key = (value['sourceRef'],value['source_version'],group_path,tuple(ranges))
        existing = next((g for g in groups if g['key']==key),None)
        if existing:
            existing['hitIndexes'].append(index)
            existing['priority'] = min(existing['priority'],priority)
        else:
            groups.append({'key':key,'value':value,'path':group_path,'text':group_text,
                           'ranges':ranges,'hitIndexes':[index],'priority':priority})
    # Merge only overlapping/adjacent original ranges in the same source/version.
    # Hit priority/diagnostics stay attached to their actual factual group.
    merged = []
    for group in groups:
        peers = [g for g in merged if g['key'][:3] == group['key'][:3] and
                 any(a <= d and c <= b for a,b in g['ranges'] for c,d in group['ranges'])]
        for peer in peers:
            group['ranges'] = _merge_ranges(peer['ranges']+group['ranges'])
            group['hitIndexes'] = sorted(set(peer['hitIndexes']+group['hitIndexes']))
            group['priority'] = min(peer['priority'],group['priority'])
            merged.remove(peer)
        merged.append(group)
    passages, source_map, raw_groups, positions = [], {}, [], {}
    for group in merged:
        ranges = group['ranges']
        if group['value']['kind'] != 'word':
            ranges = _merge_ranges(ranges+_intro_ranges(group['text']))
        keys = []
        for start, end in ranges:
            position = (*group['key'][:3],start,end)
            source = positions.get(position)
            if not source:
                source = f'S{len(passages)+1}'
                text = group['text'][start:end]
                passages.append({'source':source,'text':text})
                source_map[source] = {'partnerId':partner_id,'sourceRef':group['value']['sourceRef'],
                    'source_version':group['value']['source_version'],'path':group['path'],
                    'start':start,'end':end,'text':text}
                positions[position] = source
            keys.append(source)
        raw_groups.append({'sources':keys,'hitIndexes':group['hitIndexes'],
                           'size':sum(b-a for a,b in ranges),'priority':group['priority']})
    cases = [dict(r) for r in conn.execute(
        'SELECT id,partner_id,title,description,created_at FROM cases '
        'WHERE partner_id=? AND visible=1 ORDER BY id', (partner_id,))]
    query_terms = set(matching.recall_query(requirement,{})[0])
    def relevance(case):
        body = matching.normalize_recall_text((case['title'] or '')+' '+(case['description'] or ''))
        return sum(min(len(token),12) for token in query_terms if token in body)
    cases.sort(key=lambda c:(-relevance(c),c['id']))
    evidence_deliverables = []
    for case in cases:
        files = [dict(r) for r in conn.execute(
            'SELECT id,case_id,filename,? AS case_title FROM deliverables WHERE case_id=? ORDER BY id',
            (case['title'],case['id']))]
        files.sort(key=lambda d:(-sum(min(len(t),6) for t in query_terms & terms(d['filename'])),d['id']))
        evidence_deliverables += files
    coverage = {'complete':not omissions,'hitCount':len(hits),'hitGroupCount':len(merged),
                'omittedHitGroups':len(omissions),'selectedGroupCount':len(raw_groups),
                'backgroundHitCount':len(background),'omissions':omissions}
    context = {'partnerId':partner_id,'name':partner['name'],
               'capabilities':partner.get('capabilities') or '',
               'industries':partner.get('industries') or '',
               'regions':partner.get('service_areas') or '',
               'profilePassages':passages,
               'visibleCases':[{'id':c['id'],'title':c['title'],
                                'relevantDescription':c.get('description') or ''} for c in cases],
               'deliverables':[{'id':d['id'],'caseId':d['case_id'],'filename':d['filename'],
                                'caseTitle':d['case_title']} for d in evidence_deliverables],
               'inputCoverage':coverage,
               'evidenceState':_source_note(coverage),
               '_sourceMap':source_map,'_groups':raw_groups}
    return partner,context,cases,evidence_deliverables


def _source_note(coverage):
    reasons = {entry['reason'] for entry in coverage.get('omissions', [])}
    if 'source_position_unavailable' in reasons:
        return '部分召回命中的来源位置无法确认，相关片段未能送达。'
    if reasons & {'original_range_unavailable', 'ambiguous_original_range', 'source_group_unavailable'}:
        return '部分召回命中的原文范围无法唯一定位，相关片段未能送达。'
    return ''


def _coalesced_passages(entries, existing_keys):
    """Merge only contiguous ranges of one original; retain every exact raw char."""
    buckets = {}
    for key,entry in entries:
        identity = tuple(entry[k] for k in ('partnerId','sourceRef','source_version','path'))
        buckets.setdefault(identity,[]).append((key,entry))
    mapping,aliases = {},{}
    for parts in buckets.values():
        merged = []
        for key,entry in sorted(parts,key=lambda part:(part[1]['start'],part[1]['end'])):
            if merged and entry['start'] <= merged[-1][1]['end']:
                chosen,current,keys = merged[-1]
                overlap = current['end']-entry['start']
                common = min(overlap,len(entry['text']))
                if current['text'][entry['start']-current['start']:entry['start']-current['start']+common] != entry['text'][:common]:
                    raise ValueError('Conflicting original source ranges')
                if entry['end'] > current['end']:
                    current['text'] += entry['text'][overlap:]
                    current['end'] = entry['end']
                keys.add(key)
                if chosen not in existing_keys and key in existing_keys:
                    merged[-1] = (key,current,keys)
            else:
                merged.append((key,dict(entry),{key}))
        for key,entry,keys in merged:
            mapping[key] = entry
            aliases.update({old:key for old in keys})
    return [{'source':key,'text':entry['text']} for key,entry in mapping.items()],mapping,aliases


def assemble_details(rows, config, content_builder, schema):
    """Select forward from raw groups using the final provider request each time."""
    material = []
    pending_note = '主要命中原文因本次额度未能送达。'
    for candidate_index, (_, context, cases, files) in enumerate(rows,1):
        # Short wire IDs are unique within this request; the full original identity
        # and offsets remain in the existing private snapshot map.
        aliases = {p['source']:f'P{candidate_index}-S{i}' for i,p in enumerate(context['profilePassages'],1)}
        context['profilePassages'] = [{**p,'source':aliases[p['source']]} for p in context['profilePassages']]
        context['_sourceMap'] = {aliases[key]:entry for key,entry in context['_sourceMap'].items()}
        context['_groups'] = [{**g,'sources':[aliases[key] for key in g['sources']]} for g in context['_groups']]
        raw = {'groups': sorted(enumerate(context['_groups']), key=lambda g:(g[1]['priority'],g[0])),
               'source_map': dict(context['_sourceMap']),
               'cases': list(cases), 'files': list(files),
               'source_note': _source_note(context['inputCoverage']), 'processed':set()}
        material.append(raw)
        context['profilePassages'] = []
        context['_sourceMap'] = {}
        context['_groups'] = []
        context['visibleCases'] = []
        context['deliverables'] = []
        cases[:] = []
        files[:] = []
        # Preserve concrete positioning/primary omissions only in private diagnostics.
        context['evidenceState'] = raw['source_note'] or (pending_note if raw['groups'] else '')
        coverage = context['inputCoverage']
        coverage.update(selectedGroupCount=0, budgetSkippedGroups=0, deduplicatedGroups=0)
    def request():
        return matching.detail_messages(content_builder(rows))
    def checked():
        return checked_config(config, request(), schema, DETAIL_CHAR_LIMIT)
    fixed_chars, fixed_tokens = input_metrics(config, request(), schema)
    checked()  # System, schema, full demand, facts and candidate fixed fields already count.
    for row in rows:
        row[1]['inputCoverage'].update(fixedInputChars=fixed_chars, fixedEstimatedTokens=fixed_tokens)
    def add_group(index, group_index, group):
        _, context, _, _ = rows[index]
        raw = material[index]
        raw['processed'].add(group_index)
        old_passages,old_map = context['profilePassages'],context['_sourceMap']
        old_chars = sum(len(p['text']) for p in old_passages)
        entries = list(old_map.items())+[(source,raw['source_map'][source]) for source in group['sources']]
        passages,mapping,aliases = _coalesced_passages(entries,set(old_map))
        old_state = context['evidenceState']
        context['evidenceState'] = raw['source_note']
        context['profilePassages'],context['_sourceMap'] = passages,mapping
        try:
            checked()
        except MatchInputBudgetError:
            context['profilePassages'],context['_sourceMap'] = old_passages,old_map
            context['evidenceState'] = old_state
            coverage = context['inputCoverage']
            coverage['omissions'].append({'reason':'selection_budget','hitIndexes':group['hitIndexes']})
            coverage['budgetSkippedGroups'] += 1
            return False
        context['_groups'] = [{**g,'sources':list(dict.fromkeys(aliases[key] for key in g['sources']))}
                              for g in context['_groups']]
        context['_groups'].append({**group,'sources':list(dict.fromkeys(aliases[key] for key in group['sources']))})
        if sum(len(p['text']) for p in passages) == old_chars:
            context['inputCoverage']['deduplicatedGroups'] += 1
        return True
    # Give each candidate its first whole fitting group before adding any background.
    for index, raw in enumerate(material):
        for group_index, group in raw['groups']:
            if add_group(index, group_index, group):
                break
    # Additional facts rotate across candidates, with their original relevance
    # order. No candidate consumes all remaining material before its peers.
    while True:
        pending = False
        for index, raw in enumerate(material):
            next_group = next(((key,g) for key,g in raw['groups'] if key not in raw['processed']),None)
            if next_group is not None:
                pending = True
                add_group(index,*next_group)
        if not pending:
            break
    # Related visible cases rotate first, then filenames belonging to sent cases.
    for kind in ('cases','files'):
        for offset in range(max((len(raw[kind]) for raw in material),default=0)):
            for index,raw in enumerate(material):
                if offset >= len(raw[kind]):
                    continue
                _,context,sent_cases,sent_files = rows[index]
                entry = raw[kind][offset]
                if kind == 'cases':
                    target,sent = context['visibleCases'],sent_cases
                    item = {'id':entry['id'],'title':entry['title'],
                            'relevantDescription':entry.get('description') or ''}
                else:
                    if entry['case_id'] not in {c['id'] for c in sent_cases}:
                        continue
                    target,sent = context['deliverables'],sent_files
                    item = {'id':entry['id'],'caseId':entry['case_id'],
                            'filename':entry['filename'],'caseTitle':entry['case_title']}
                target.append(item)
                try:
                    checked()
                except MatchInputBudgetError:
                    target.pop()
                    context['inputCoverage']['omissions'].append({
                        'reason':'case_selection_budget' if kind=='cases' else 'file_selection_budget',
                        'caseId' if kind=='cases' else 'fileId':entry['id']})
                else:
                    sent.append(entry)
    for index,raw in enumerate(material):
        context = rows[index][1]
        coverage = context['inputCoverage']
        if raw['groups'] and not context['_groups']:
            coverage['complete'] = False
            coverage['omissions'].append({'reason':'primary_evidence_budget',
                'hitIndexes':sorted({hit for _,g in raw['groups'] for hit in g['hitIndexes']})})
        coverage['selectedGroupCount'] = len(context['_groups'])
        coverage['omittedHitGroups'] = sum(bool(entry.get('hitIndexes')) for entry in coverage['omissions'])
    return checked()
