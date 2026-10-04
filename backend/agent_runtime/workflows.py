"""Both AI workflows; no database, filesystem uploads, or VM callback."""
import json,re
from backend.business import development as core_development, matching as core_matching
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
    try:core_development.strong_guard(value)
    except core_development.InvalidOutput:raise StageFailure('output_policy_rejected') from None


def validate_output(request,raw):
    if len(raw.encode())>1048576:raise StageFailure('output_too_large')
    result=CONTRACTS[request.stage].model_validate_json(raw).model_dump()
    data=request.data
    if request.workflow=='match':
        try:return core_matching.validate_stage(request.stage,data,result,raw)
        except ValueError:raise StageFailure('output_reference_invalid') from None
    try:return core_development.validate_stage(request.stage,data,result)
    except core_development.InvalidOutput:raise StageFailure('output_policy_rejected') from None



def validate_budget(request,ceiling=262144):
    messages,schema=messages_for(request)
    instruction='Return only a JSON object matching this JSON schema. No extra fields: '+json.dumps(schema,ensure_ascii=False)
    messages=[{**messages[0],'content':messages[0]['content']+'\n\n'+instruction},*messages[1:]]
    estimate=len(json.dumps(messages,ensure_ascii=False).encode())
    if estimate>request.input_token_budget or estimate+request.model.max_tokens>ceiling:raise StageFailure('input_budget_exceeded')
    return messages
