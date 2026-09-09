"""Best-effort projection of one model answer into existing opportunity fields.

Only extraction is tolerant. Formal dictionaries, ownership and storage constraints
remain unchanged. Unusable individual fields become unknown, never invented data.
"""
import json
import math
import re
from .business_taxonomy import canonical

UNKNOWN = "未知"
TEXT_FIELDS = (
    "customerName", "projectName", "industry", "region", "projectStage",
    "businessNeeds", "technicalNeeds", "deliveryNeeds", "qualificationRequirements",
    "caseRequirements", "onsiteRequirement", "timelineRequirement", "cloudPlatformPreference",
)
UNKNOWN_TEXT = {"", "未知", "未识别", "未提供", "暂无", "无法识别", "不详", "unknown", "null", "none", "n/a", "-"}


def _without_trailing_commas(raw):
    # Repair only JSON separators, preserving commas inside quoted business text.
    result = []; quoted = False; escaped = False
    for index, char in enumerate(raw):
        if quoted:
            result.append(char)
            if escaped: escaped = False
            elif char == "\\": escaped = True
            elif char == '"': quoted = False
            continue
        if char == '"': quoted = True
        if char == ',':
            rest = index + 1
            while rest < len(raw) and raw[rest].isspace(): rest += 1
            if rest < len(raw) and raw[rest] in '}]': continue
        result.append(char)
    return ''.join(result)


def _object(value, depth=0):
    if depth > 5: return {}
    if isinstance(value, list):
        # Multiple project objects are ambiguous; do not pick an arbitrary project.
        return _object(value[0], depth + 1) if len(value) == 1 else {}
    if not isinstance(value, dict): return {}
    if any(key in value for key in (*TEXT_FIELDS, "followUpQuestions")): return value
    for wrapper in ("data", "result", "opportunity", "projectOpportunity"):
        if wrapper in value: return _object(value[wrapper], depth + 1)
    return {}


def parse_fields(raw):
    if not isinstance(raw, str): return _object(raw)
    raw = raw.strip().lstrip("\ufeff")
    decoder = json.JSONDecoder(strict=False)
    repaired = _without_trailing_commas(raw)
    for candidate in (raw, repaired):
        try: return _object(decoder.decode(candidate))
        except (ValueError, RecursionError): pass
    # A prose prefix or Markdown fence does not invalidate an enclosed object.
    for match in re.finditer(r"[\[{]", repaired):
        try:
            value, _ = decoder.raw_decode(repaired, match.start())
        except (ValueError, RecursionError): continue
        if isinstance(value, list) and len(value) > 1: return {}
        result = _object(value)
        if result: return result

    return {}


def _text(value, depth=0):
    if depth > 5: return UNKNOWN
    if isinstance(value, str):
        value = value.replace("\x00", "").encode("utf-8", "replace").decode().strip()
        return UNKNOWN if value.casefold() in UNKNOWN_TEXT else value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value) if not isinstance(value, float) or math.isfinite(value) else UNKNOWN
    if isinstance(value, list):
        items = [_text(item, depth + 1) for item in value]
        return "；".join(dict.fromkeys(item for item in items if item != UNKNOWN)) or UNKNOWN
    if isinstance(value, dict):
        for key in ("text", "value", "name"):
            if key in value: return _text(value[key], depth + 1)
    return UNKNOWN


def _classification_parts(value, kind, depth=0):
    if depth > 5: return []
    if isinstance(value, str): return [value]
    if isinstance(value, list):
        return [part for item in value for part in _classification_parts(item, kind, depth + 1)]
    if isinstance(value, dict):
        keys = ("domestic", "overseas", "regions", "region_groups", "region", "value", "name") if kind == "region" else ("industries", "industry", "values", "value", "name")
        return [part for key in keys if key in value for part in _classification_parts(value[key], kind, depth + 1)]
    return []


def normalize_opportunity(raw):
    data = parse_fields(raw)
    result = {field: _text(data.get(field)) for field in TEXT_FIELDS}
    for field in ("industry", "region"):
        parts = _classification_parts(data.get(field), field)
        result[field] = canonical(parts, field) or UNKNOWN
    questions = data.get("followUpQuestions", [])
    if not isinstance(questions, list): questions = [questions]
    result["followUpQuestions"] = [text for item in questions if (text := _text(item)) != UNKNOWN]
    return result
