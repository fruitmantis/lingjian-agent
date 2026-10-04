"""Wire-stage adapters for the shared business prompts; no separate prompts."""
import json
from backend.business import development as core_development, matching as core_matching
from backend.business.matching_types import MatchUnderstanding, InitialSelection, MatchAnswer
from backend.app.business_taxonomy import taxonomy_prompt

development = core_development.request

def matching(stage, payload):
    if stage == 'understanding':
        messages=core_matching.understanding_messages(payload['requirement'],payload['standard_tags'],taxonomy_prompt())
        contract=MatchUnderstanding
    elif stage == 'initial_selection':
        messages=core_matching.initial_messages(payload['facts'],payload['partners'])
        contract=InitialSelection
    elif stage == 'detailed_review':
        messages=core_matching.detail_messages(json.dumps(payload,ensure_ascii=False,separators=(',',':')))
        contract=MatchAnswer
    else:raise ValueError('Unknown matching stage')
    return messages,contract.model_json_schema()
