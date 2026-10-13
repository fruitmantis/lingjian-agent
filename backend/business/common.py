"""Strict contracts shared by the existing business modules."""
from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class ModelOutput(BaseModel):
    """Model-only projection; HTTP and persistence contracts stay strict."""
    model_config = ConfigDict(extra='ignore', str_strip_whitespace=True)


MATCH_LEGACY_TEMPLATE = '供给覆盖依据以下有效推荐及其待核实事项判断。'
DEVELOPMENT_LEGACY_TEMPLATES = frozenset({
    '当前提供的信息有限，本次建议主要依据已有信息和发展方向，未说明的能力仍待核实，需通过真实项目验证。',
    '当前提供的信息有限，未说明的能力仍待核实，需通过真实项目验证。',
})

def historical_match_answer(text,format_version):
    if format_version==2:return text
    import re
    parts=re.split(r'(\n[ \t]*\n(?:[ \t]*\n)*)',text)
    for index in range(len(parts)-1,-1,-1):
        if index%2==0 and parts[index].strip()==MATCH_LEGACY_TEMPLATE:
            if index+1<len(parts):del parts[index:index+2]
            elif index:del parts[index-1:index+1]
            else:parts[index]=''
    return ''.join(parts)

def historical_development_payload(payload):
    if payload.get('format_version')!=2 and 'limitations' in payload:
        payload['limitations']=[item for item in payload['limitations'] if item not in DEVELOPMENT_LEGACY_TEMPLATES]
    return payload
