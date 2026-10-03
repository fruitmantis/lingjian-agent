"""User-operated Runtime credential handoff, after the isolated backend is provisioned."""
import argparse
import getpass
import os
from pathlib import Path
import stat
import sys
import tempfile
import warnings

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from backend.app.runtime_endpoint import validate_endpoint, operation_url
from backend.agent_runtime.contracts import model_route

CONFIG = Path('/etc/banfei-agentarts/backend.env')
RUNTIME_URL = 'https://defaultgw-gzswgzdcgz.cn-southwest-2.huaweicloud-agentarts.com/runtimes/banfei-runtime-test/invocations?endpoint=Latest'


def replace_values(path, original, updates):
    metadata = path.lstat()
    if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1):
        raise RuntimeError('Unsafe private configuration file')
    if path.read_bytes() != original:
        raise RuntimeError('Configuration changed; retry the handoff later')
    lines = original.decode('utf-8').splitlines()
    lines = [line for line in lines if line.split('=', 1)[0].strip() not in updates]
    for key, value in updates.items():
        if not value or any(c.isspace() for c in value) or any(c in value for c in (chr(34), chr(39), chr(92), chr(96), chr(36))):
            raise ValueError('Credential or URL contains unsupported characters')
        lines.append(key + '=' + value)
    content = ('\n'.join(lines) + '\n').encode()
    fd, temporary = tempfile.mkstemp(prefix='.runtime-handoff-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o600)
        if path.read_bytes() != original:
            raise RuntimeError('Configuration changed; no replacement made')
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true', help='After saving, perform one authenticated Runtime-info GET; no model job')
    args = parser.parse_args()
    if os.geteuid() != 0 or not sys.stdin.isatty():
        raise RuntimeError('Run interactively as root on the provisioned ARM host; no piped credential input')
    if CONFIG.parent.resolve() != CONFIG.parent or not CONFIG.is_file() or CONFIG.is_symlink():
        raise RuntimeError('Isolated backend must be provisioned first')
    metadata = CONFIG.stat()
    if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1:
        raise RuntimeError('Backend configuration must be a root-owned 0600 regular file')
    original = CONFIG.read_bytes()
    text = original.decode('utf-8')
    for required in ('BANFEI_DEPLOYMENT_PROFILE=agentarts', 'BANFEI_MATCH_EXECUTOR=runtime', 'BANFEI_DEVELOPMENT_EXECUTOR=runtime'):
        if required not in text.splitlines(): raise RuntimeError('Not the isolated AgentArts backend configuration')
    base, _ = validate_endpoint(RUNTIME_URL, external_approved=True)
    # getpass warns before its echoing fallback reads input. Treat that warning
    # as fatal for BOTH prompts so no fallback consumes a credential and no
    # partial configuration is written if the second terminal prompt fails.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            platform_key = getpass.getpass('Platform API key (hidden; user input only): ')
            shared_key = getpass.getpass('New rotated Runtime shared key (hidden; user input only): ')
    except getpass.GetPassWarning:
        raise RuntimeError('Hidden terminal input unavailable; no credentials saved') from None
    if not platform_key or len(shared_key) < 32 or '__' in platform_key or '__' in shared_key:
        raise ValueError('Missing key, placeholder or shared key shorter than 32 characters')
    replace_values(CONFIG, original, {'BANFEI_RUNTIME_URL': base,
        'BANFEI_AGENTARTS_BEARER': platform_key, 'BANFEI_RUNTIME_SHARED_KEY': shared_key})
    print('Saved only the isolated backend configuration, root:root 0600. No service was restarted.')
    if args.verify:
        import httpx
        import uuid
        with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
            response = client.get(operation_url(base, 'runtime-info'), headers={
                'Authorization': 'Bearer ' + platform_key,
                'X-Banfei-Runtime-Key': shared_key,
                'X-Hw-Agentarts-Session-Id': str(uuid.uuid4())})
            if response.status_code != 200:
                raise RuntimeError('Runtime-info verification failed with HTTP ' + str(response.status_code))
            result = response.json()
            if result.get('protocol') != 'banfei-runtime-v1' or result.get('provider_route') != model_route('https://api.deepseek.com', 'deepseek-flash'):
                raise RuntimeError('Runtime protocol or selected deepseek-flash route mismatch')
            uuid.UUID(result['incarnation'])
        print('Authenticated Runtime-info and model route verified; no model request was sent.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print('Handoff cancelled; no credential output.', file=sys.stderr)
        raise SystemExit(1)
    except Exception as error:
        # Never echo HTTP bodies, credentials, input, headers or exception repr.
        print('Handoff or verification failed (' + type(error).__name__ + '); check the isolated configuration locally. No service changed.', file=sys.stderr)
        raise SystemExit(1)
