"""Both AI workflows; no database, filesystem uploads, or VM callback."""
import json,re
from .prompts import development,matching
from .match_types import MatchUnderstanding,InitialSelection,MatchAnswer
from .development_types import Understanding,AdviceOutput,AdvicePatch
from .diagnostics import StageFailure

CONTRACTS={'understanding':MatchUnderstanding,'initial_selection':InitialSelection,'detailed_review':MatchAnswer,
           'analyze':Understanding,'plan':AdviceOutput,'patch':AdvicePatch}

def messages_for(request):
    contract=CONTRACTS[request.stage]
    messages,schema = matching(request.stage,request.data) if request.workflow=='match' else development(request.stage,request.data,contract)
    messages[0]['content'] += '\n'+request.material_notice
    return messages,schema

def strong_guard(value):
    if isinstance(value,dict):
        for v in value.values():strong_guard(v)
    elif isinstance(value,list):
        for v in value:strong_guard(v)
    # Absence of capability records/evidence is not absence of capability.
    elif isinstance(value,str) and re.search(r'确认.*不具备|确认不足|明确不满足|没有(?:(?!能力)[^，。！？；,.;!?\n]){0,12}能力(?![ \t]*(?:的[ \t]*)?(?:记载|记录|证据))|学完.{0,8}具备|能力已提升',value):
        raise StageFailure('output_policy_rejected')

def ref(item):return (item['source_type'],item['source_id'],item['source_version'])

def validate_output(request,raw):
    if len(raw.encode())>1048576:raise StageFailure('output_too_large')
    result=CONTRACTS[request.stage].model_validate_json(raw).model_dump()
    data=request.data
    if request.workflow=='match':
        if request.stage=='understanding' and result['in_scope']:
            if not set(result['facts']['capabilityTags'])<=set(data['standard_tags']):raise StageFailure('output_reference_invalid')
            if any(not s['evidenceText'] or s['evidenceText'] not in data['requirement'] for s in result['tag_suggestions']):raise StageFailure('output_reference_invalid')
        elif request.stage=='initial_selection':
            ids=[v['partnerId'] for v in result['candidates']]
            if len(ids)!=len(set(ids)) or not set(ids)<={p['partnerId'] for p in data['partners']}:raise StageFailure('output_reference_invalid')
        elif request.stage=='detailed_review':
            allowed={p['partnerId']:p for p in data['candidates']}
            seen=set()
            for item in result['recommendations']:
                if item['partnerId'] not in allowed or item['partnerId'] in seen:raise StageFailure('output_reference_invalid')
                seen.add(item['partnerId'])
            if result['supplyStatus']=='sufficient' and not seen:raise StageFailure('output_policy_rejected')
        return result
    text=json.dumps(result,ensure_ascii=False)
    if re.search(r'INTERNAL_SECRET_|Bearer\s|api_key|<think>|</think>|/tasks/|javascript:|https?://',text,re.I):raise StageFailure('output_policy_rejected')
    if result['target_partner_id'] != data['request']['target_partner_id']:raise StageFailure('output_reference_invalid')
    strong_guard(result)
    if request.stage=='analyze':
        if not result['in_scope']:return result
        tags={t['id'] for t in data['formal_tags']}
        if any(p['capability_tag_id'] and p['capability_tag_id'] not in tags for p in result['priorities']):raise StageFailure('output_reference_invalid')
        current=data.get('current')
        if current:
            if result['action']=='generate':raise StageFailure('output_state_invalid')
            if not set(result['edit_item_ids'])<={i['item_id'] for i in current['resources']}:raise StageFailure('output_reference_invalid')
            if any(current['answer'].count(s)!=1 for s in result['edit_answer_spans']):raise StageFailure('output_reference_invalid')
            if not {ref(i) for i in result['references']}<={ref(i) for i in current['resources']}:raise StageFailure('output_reference_invalid')
            if result['action']=='patch' and (current['content_unavailable'] or not (result['edit_item_ids'] or result['edit_answer_spans'])):raise StageFailure('output_state_invalid')
        elif result['action'] in ('patch','regenerate'):raise StageFailure('output_state_invalid')
        if result['action']!='answer':result['answer']=''
        elif not result['answer'].strip():raise StageFailure('output_validation_failed')
    else:
        allowed={ref(i) for i in data['candidates']}
        items=[i for s in result['stages'] for i in s['items']] if request.stage=='plan' else [i for c in result['changes'] for i in c['items']]
        if any(ref(i) not in allowed for i in items):raise StageFailure('output_reference_invalid')
        if request.stage=='patch':
            ids=[c['item_id'] for c in result['changes']]
            if len(ids)!=len(set(ids)) or not set(ids)<=set(data['understanding']['edit_item_ids']):raise StageFailure('output_reference_invalid')
            spans=[c['before'] for c in result['answer_changes']]
            if len(spans)!=len(set(spans)) or not set(spans)<=set(data['understanding']['edit_answer_spans']):raise StageFailure('output_reference_invalid')
    return result


def validate_budget(request,ceiling=262144):
    messages,schema=messages_for(request)
    instruction='Return only a JSON object matching this JSON schema. No extra fields: '+json.dumps(schema,ensure_ascii=False)
    messages=[{**messages[0],'content':messages[0]['content']+'\n\n'+instruction},*messages[1:]]
    estimate=len(json.dumps(messages,ensure_ascii=False).encode())
    if estimate>request.input_token_budget or estimate+request.model.max_tokens>ceiling:raise StageFailure('input_budget_exceeded')
    return messages
