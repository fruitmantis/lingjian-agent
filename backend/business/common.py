"""Strict contracts shared by the existing business modules."""
from pydantic import BaseModel, ConfigDict
import json
import re


class ModelJSONError(ValueError):
    """A model response has no unambiguous complete top-level JSON object."""


def model_json_object(raw):
    """Unwrap BOM/fences or prose around one object; never repair JSON syntax."""
    if not isinstance(raw,str):raise ModelJSONError('Model JSON response must be text')
    text=raw.strip().removeprefix('\ufeff').strip()
    fenced=re.fullmatch(r'```(?:json)?[ \t]*\r?\n(.*?)\r?\n?```',text,re.I|re.S)
    if fenced:text=fenced.group(1).strip()
    try:
        value=json.loads(text)
    except json.JSONDecodeError:
        # Start at the first structural opener only. A broken enclosing object
        # must fail, rather than searching inside it for a convenient nested one.
        first=re.search(r'[\{\[]',text)
        if not first or first[0]!='{' or text.startswith(('"',"'")):
            raise
        try:value,end=json.JSONDecoder().raw_decode(text,first.start())
        except json.JSONDecodeError as error:raise error from None
        outside=text[:first.start()]+text[end:]
        if re.search(r'[{}\[\]]',outside) or text[end:].lstrip().startswith(('"',"'")):
            raise ModelJSONError('Ambiguous model JSON envelope') from None
    if not isinstance(value,dict):raise ModelJSONError('Model JSON root must be an object')
    return value


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
    payload.pop('limitations',None)  # Read projection only, including existing Version 2 payloads.
    return payload
