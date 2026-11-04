"""The six manually maintained, independent partner identities."""
import json
from pathlib import Path

IDENTITIES = json.loads((Path(__file__).resolve().parents[2] / 'shared/partner-identities.json').read_text())


def validate_identities(values):
    if values is None:
        return None
    if any(value not in IDENTITIES for value in values):
        raise ValueError('请选择有效的伙伴身份')
    return list(dict.fromkeys(values))


def read_identities(value):
    return [] if value is None else json.loads(value) if isinstance(value, str) else value


def stored_identities(values):
    return json.dumps(values, ensure_ascii=False) if values else None
