#!/usr/bin/env python3
"""User-operated v2 credential update for the existing isolated ARM backend only."""
import argparse
import getpass
import os
from pathlib import Path
import platform
import shlex
import stat
import sys
import tempfile
from urllib.parse import urlsplit
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_runtime_v2 import VerificationError, safe_text, validate_keys, verify

CONFIG = Path('/etc/banfei-agentarts/backend.env')
BASE = 'https://defaultgw-gzswgzdcgz.cn-southwest-2.huaweicloud-agentarts.com/runtimes/'
URLS = {'match': BASE + 'banfei-matching/invocations?endpoint=Latest',
        'development': BASE + 'banfei-development/invocations?endpoint=Latest'}


class SetupError(Exception):
    pass


def read_private(path):
    parent = path.parent.stat()
    if (path.parent.resolve() != path.parent or parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) & 0o022):
        raise SetupError('隔离配置目录的属主、权限或路径不安全。')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as source:
        metadata = os.fstat(source.fileno())
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1):
            raise SetupError('配置必须是当前 root 所有的 0600 普通文件，不能是链接。')
        original = source.read(2 * 1024 * 1024 + 1)
    if len(original) > 2 * 1024 * 1024:
        raise SetupError('配置超过允许大小。')
    return original


def parse_config(original):
    values = {}
    try:
        for line in original.decode('utf-8').splitlines():
            parts = shlex.split(line, comments=True, posix=True)
            if not parts:
                continue
            if len(parts) != 1 or '=' not in parts[0]:
                raise ValueError()
            key, value = parts[0].split('=', 1)
            if key in values:
                raise ValueError()
            values[key] = value
    except (UnicodeError, ValueError):
        raise SetupError('配置语法不支持或含重复键；未写入，不显示原文。') from None
    return values


def check_isolation(original):
    values = parse_config(original)
    try:
        database = urlsplit(values.get('DATABASE_URL', ''))
        valid = (values.get('BANFEI_DEPLOYMENT_PROFILE') == 'agentarts'
                 and database.scheme in ('postgresql', 'postgresql+psycopg')
                 and database.hostname == '127.0.0.1' and database.port == 55432
                 and database.path == '/banfei_agentarts' and database.username == 'banfei_agentarts_app'
                 and not database.query and not database.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise SetupError('配置不是既有 AgentArts 隔离环境（专用 PG 55432）；未写入。')


def candidate_config(original, keys):
    check_isolation(original)
    updates = {'BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED': '0'}
    for workflow in ('match', 'development'):
        platform_key, shared_key = keys[workflow]
        validate_keys(platform_key, shared_key)
        for value in (platform_key, shared_key):
            # Keep systemd and dotenv parsing identical; reject rather than transform secrets.
            if any(c in value for c in ('"', "'", '\\', '`', '$', '#')):
                raise SetupError('密钥含环境文件不支持的字符；未写入，不显示内容。')
        prefix = 'BANFEI_' + workflow.upper()
        updates[prefix + '_AGENTARTS_BEARER'] = platform_key
        updates[prefix + '_RUNTIME_SHARED_KEY'] = shared_key
    lines = []
    for line in original.decode('utf-8').splitlines(keepends=True):
        parts = shlex.split(line, comments=True, posix=True)
        if not parts or parts[0].split('=', 1)[0] not in updates:
            lines.append(line)
    content = ''.join(lines)
    if content and not content.endswith('\n'):
        content += '\n'
    content += ''.join(f'{key}={value}\n' for key, value in updates.items())
    return content.encode('utf-8')


def save_private(path, original, candidate):
    if read_private(path) != original:
        raise SetupError('配置已被其他操作修改；本次未写入。')
    fd, temporary = tempfile.mkstemp(prefix='.runtime-v2-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(candidate)
            output.flush()
            os.fsync(output.fileno())
        if read_private(path) != original:
            raise SetupError('配置在录入期间发生变化；本次未替换。')
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv=None):
    parser = argparse.ArgumentParser(description='正式 v2：隐藏录入四个 Key，仅更新隔离后端配置；外发开关固定为 0。')
    parser.add_argument('--verify', action='store_true', help='保存后对两个固定 Runtime 各发一次无模型握手 GET；默认不联网')
    args = parser.parse_args(argv)
    keys = {}
    stage = 'preflight'
    try:
        if os.geteuid() != 0 or not sys.stdin.isatty() or platform.machine() != 'aarch64':
            raise SetupError('请在已配置 ARM 的本机交互终端用 sudo 运行；不接受管道输入。')
        original = read_private(CONFIG)
        check_isolation(original)
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            for workflow, label in [('match', '伙伴匹配'), ('development', '能力发展')]:
                platform_key = getpass.getpass(label + '：平台 Runtime 原始 Key（隐藏，不含 Bearer）：')
                shared_key = getpass.getpass(label + '：应用 shared key（隐藏，至少 32 字符）：')
                validate_keys(platform_key, shared_key)
                keys[workflow] = (platform_key, shared_key)
        candidate = candidate_config(original, keys)
        stage = 'saving'
        save_private(CONFIG, original, candidate)
        stage = 'saved'
        print('已原子更新隔离 backend.env，权限 0600；外发开关=0。未重启服务、未写数据库。')
        if args.verify:
            for workflow in ('match', 'development'):
                result = verify(URLS[workflow], workflow, *keys[workflow])
                print(workflow + ' v2 握手通过；incarnation=' + result['incarnation'])
            print('两次 GET 完成；未调用模型，外发开关仍为 0。')
        print('后端进程需在部署窗口重启后读取新配置；模型元数据和智能体地址在后台另行设置。')
        return 0
    except (SetupError, VerificationError, getpass.GetPassWarning, OSError, EOFError, KeyboardInterrupt) as exc:
        prefix = {'saving': '写入未确认，请在本机核对状态；', 'saved': '配置已保存，后续握手未完成；'}.get(stage, '配置未写入；')
        # OS/getpass errors may contain paths or terminal details: only fixed actionable context.
        message = str(exc) if isinstance(exc, (SetupError, VerificationError)) else '终端、文件权限或输入中断，请本机检查。'
        secrets = tuple(value for pair in keys.values() for value in pair)
        print(prefix + safe_text(message, secrets), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
