"""Pure URL validation for the explicitly configured AgentArts invocation root."""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def validate_endpoint(value, *, local_test=False, external_approved=False):
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError('Invalid Runtime endpoint') from None
    local = local_test and parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and port is not None
    if (not value or value != value.strip() or any(character.isspace() for character in value)
            or not parsed.hostname or parsed.username or parsed.password or parsed.fragment):
        raise ValueError('Invalid Runtime endpoint')
    path = parsed.path.rstrip('/')
    if local:
        if not 1024 <= port <= 65535 or any(part in ('.', '..') for part in path.split('/')) or not re.fullmatch(r'(?:/[A-Za-z0-9._-]+)*', path):
            raise ValueError('Invalid local Runtime test endpoint')
    else:
        host = parsed.hostname.lower()
        if (parsed.scheme != 'https' or port not in (None, 443)
                or not host.endswith('.huaweicloud-agentarts.com')
                or not re.fullmatch(r'[a-z0-9.-]+', host)
                or not re.fullmatch(r'/runtimes/[A-Za-z0-9][A-Za-z0-9._-]{0,127}/invocations', path)):
            raise ValueError('Runtime requires an official HTTPS AgentArts invocation root')
        if not external_approved:
            raise ValueError('External Runtime data transmission is not approved')
    try:
        query = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise ValueError('Invalid Runtime query') from None
    if query and (len(query) != 1 or query[0][0] != 'endpoint' or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}', query[0][1])):
        raise ValueError('Only one named AgentArts endpoint selector is allowed')
    return urlunsplit((parsed.scheme, parsed.netloc.lower(), path, urlencode(query), '')), local


def operation_url(base, operation):
    if not re.fullmatch(r'(?:runtime-info|jobs(?:/[0-9a-fA-F-]{36}(?:/retry)?)?)', operation):
        raise ValueError('Invalid Runtime operation path')
    parsed = urlsplit(base)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip('/') + '/' + operation, parsed.query, ''))
