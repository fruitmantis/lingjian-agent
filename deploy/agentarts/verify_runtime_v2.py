#!/usr/bin/env python3
"""Interactive, memory-only v2 handshake. One GET; no model or business job."""
import argparse
import getpass
import hashlib
from http.client import HTTPException
import json
from pathlib import Path
import re
import sys
import uuid
import warnings
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.app.runtime_endpoint import operation_url, validate_endpoint

PROTOCOL = 'banfei-runtime-v2'
PROXY_URL = 'https://banfei-model-proxy-defaultgw-gzswgzdcgz.cn-southwest-2.huaweicloud-agentarts.com/inference/v1'
PROXY_DIGEST = hashlib.sha256(json.dumps(PROXY_URL, ensure_ascii=False, sort_keys=True,
                                        separators=(',', ':')).encode()).hexdigest()
MAX_BODY = 65536


class VerificationError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def safe_text(value, secrets=()):
    """Keep diagnostic codes/messages, remove entered credentials and terminal controls."""
    value = str(value)
    for secret in sorted(filter(None, secrets), key=len, reverse=True):
        for variant in (secret, quote(secret, safe=''), json.dumps(secret)[1:-1]):
            value = value.replace(variant, '[已隐藏]')
    value = re.sub(r'(?i)Bearer\s+[^\s"\'<>]+', 'Bearer [已隐藏]', value)
    value = ''.join(c if c.isprintable() else ' ' for c in value)
    return value[:1600]


def runtime_info_url(value):
    # Shared pure validator: official HTTPS domain, 443, invocation root and optional endpoint only.
    try:
        base, _ = validate_endpoint(value.strip(), external_approved=True)
    except ValueError as exc:
        raise VerificationError('Runtime URL 无效：仅支持官方 HTTPS AgentArts /runtimes/<名称>/invocations 地址，'
                                '可带 ?endpoint=<名称>；不允许凭据、其他参数或端口。') from exc
    return operation_url(base, 'runtime-info')


def validate_keys(platform_key, shared_key):
    for label, value, minimum in [('平台 Runtime Key', platform_key, 1), ('应用共享密钥', shared_key, 32)]:
        if (len(value) < minimum or not value.isascii() or any(c.isspace() or not c.isprintable() for c in value)
                or value.lower().startswith('bearer ')):
            raise VerificationError(f'{label} 格式无效：请粘贴原始 ASCII 密钥，不含 Bearer 前缀或空白；至少 {minimum} 字符。')


def diagnostics(headers, body):
    ids = [f'{key}={headers[key]}' for key in
           ('X-Request-Id', 'X-Hw-Request-Id', 'X-Correlation-Id') if headers.get(key)]
    return '; '.join(ids + [body.decode('utf-8', errors='replace')])


def verify(url, workflow, platform_key, shared_key):
    target = runtime_info_url(url)
    if workflow not in ('match', 'development'):
        raise VerificationError('工作流仅支持 match 或 development。')
    validate_keys(platform_key, shared_key)
    request = Request(target, method='GET', headers={
        'Authorization': 'Bearer ' + platform_key,
        'X-Banfei-Runtime-Key': shared_key,
        'X-Hw-Agentarts-Session-Id': str(uuid.uuid4()),
        'Content-Type': 'application/json', 'Accept': 'application/json',
    })
    # No environment proxy, redirect, retry, cookie jar, debug logger or persisted credentials.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    secrets = (platform_key, shared_key)
    try:
        try:
            with opener.open(request, timeout=20) as response:
                body = response.read(MAX_BODY + 1)
                status = response.status
                detail = diagnostics(response.headers, body)
        except HTTPError as exc:
            with exc:
                detail = diagnostics(exc.headers, exc.read(MAX_BODY + 1))
            hint = '（已拒绝重定向，不会转发密钥）' if 300 <= exc.code < 400 else ''
            raise VerificationError(f'HTTP {exc.code} {exc.reason} {hint}；{detail}') from None
        if status != 200:
            raise VerificationError(f'HTTP {status}；{detail}')
        if len(body) > MAX_BODY:
            raise VerificationError('响应超过 64 KiB，已停止读取。')
        try:
            info = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            raise VerificationError(f'HTTP 200，但响应不是有效 JSON；{detail}') from None
        if not isinstance(info, dict):
            raise VerificationError('HTTP 200，但握手 JSON 不是对象。')
        for field, expected in [('protocol', PROTOCOL), ('workflow', workflow), ('provider_endpoint', PROXY_DIGEST)]:
            if info.get(field) != expected:
                raise VerificationError(f'{field} 不匹配：期望 {expected}，实际 {info.get(field)!r}')
        try:
            incarnation = str(uuid.UUID(info['incarnation']))
        except (KeyError, ValueError, TypeError, AttributeError):
            raise VerificationError(f'incarnation 不是有效 UUID：{info.get("incarnation")!r}') from None
        return {'protocol': PROTOCOL, 'workflow': workflow, 'incarnation': incarnation,
                'provider_endpoint': PROXY_DIGEST}
    except (VerificationError, URLError, OSError, HTTPException, ValueError) as exc:
        raise VerificationError(safe_text(f'{type(exc).__name__}: {exc}', secrets)) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description='伴飞正式 v2 握手：仅一次 GET /runtime-info，不调用模型、不保存密钥。')
    parser.add_argument('--workflow', choices=('match', 'development'), help='match=伙伴匹配；development=能力发展；省略时交互选择')
    args = parser.parse_args(argv)
    platform_key = shared_key = ''
    try:
        if not sys.stdin.isatty():
            raise VerificationError('请在本机交互终端运行；不接受管道输入密钥。')
        workflow = args.workflow
        if workflow is None:
            selected = input('选择工作流 [1=伙伴匹配 / 2=能力发展]：').strip()
            workflow = {'1': 'match', '2': 'development', 'match': 'match', 'development': 'development'}.get(selected)
            if workflow is None:
                raise VerificationError('请选择 1 或 2，或使用 --workflow match|development。')
        url = input('粘贴控制台完整 Runtime 调用 URL：').strip()
        runtime_info_url(url)
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            platform_key = getpass.getpass('平台 Runtime 原始 Key（隐藏输入，不含 Bearer）：')
            shared_key = getpass.getpass('应用共享密钥 BANFEI_RUNTIME_SHARED_KEY（隐藏输入）：')
        result = verify(url, workflow, platform_key, shared_key)
        print('握手通过：' + json.dumps(result, ensure_ascii=False))
        print('仅验证 v2 路由、鉴权、工作流、实例标识和代理地址摘要；未验证模型代理 Key 或模型调用。')
        return 0
    except (VerificationError, getpass.GetPassWarning, EOFError, KeyboardInterrupt) as exc:
        message = str(exc) or '输入已取消，未完成握手。'
        print('握手失败：' + safe_text(message, (platform_key, shared_key)), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
