"""Read-only ARM deployment checks. Never changes users, services, PG, Caddy or secrets."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import platform
import pwd
import re
import grp
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from backend.app.runtime_endpoint import validate_endpoint

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('arm_environment', ROOT / 'backend/scripts/enablement_environment.py')
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)
ACCOUNTS = {'banfei-agentarts': '/var/lib/banfei-agentarts',
            'banfei-agentarts-pg': '/var/lib/banfei-agentarts-pg'}
PORTS = {3001, 8001, 55432}


def listeners():
    result = set()
    for name in ('/proc/net/tcp', '/proc/net/tcp6'):
        path = Path(name)
        if path.exists():
            for row in path.read_text().splitlines()[1:]:
                fields = row.split()
                if fields[3] == '0A':
                    result.add(int(fields[1].rsplit(':', 1)[1], 16))
    return result


def account_errors(name, home):
    try:
        account = pwd.getpwnam(name)
    except KeyError:
        return ['account absent: ' + name]
    errors = []
    if account.pw_uid == 0 or account.pw_shell != '/usr/sbin/nologin' or account.pw_dir != home:
        errors.append('unexpected uid/shell/home: ' + name)
    groups = {g.gr_name for g in grp.getgrall() if name in g.gr_mem or g.gr_gid == account.pw_gid}
    if groups != {name}:
        errors.append('unexpected group membership: ' + name)
    if (Path(home) / '.ssh').exists():
        errors.append('SSH directory must not be provisioned: ' + name)
    return errors


def configuration_errors(environment):
    errors = []
    try:
        if manager.deployment_profile(environment) != 'agentarts':
            raise RuntimeError('AgentArts deployment profile must be explicit')
        manager.validate_agentarts(environment)
        if manager.origins(environment) != ['http://banfei-agentarts.test']:
            raise RuntimeError('Expected the approved HTTP hostname only')
        if environment.get('BANFEI_API_PROXY_TARGET') != manager.api_target(environment):
            raise RuntimeError('Wrong internal API target')
        if environment.get('CORS_ORIGINS') != 'http://banfei-agentarts.test':
            raise RuntimeError('Wrong CORS origin')
        validate_endpoint(environment.get('BANFEI_RUNTIME_URL', ''), external_approved=environment.get('BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED') == '1')
    except (ValueError, RuntimeError):
        errors.append('deployment profile, PG, origin, paths or runtime executors are invalid')
    for key in ('DATABASE_URL', 'JWT_SECRET_KEY', 'BANFEI_IDENTITY_ENCRYPTION_KEY',
                'BANFEI_RUNTIME_URL',
                'BANFEI_AGENTARTS_BEARER', 'BANFEI_RUNTIME_SHARED_KEY'):
        value = environment.get(key, '')
        if not value or re.search(r'__[A-Z][A-Z0-9_]*__', value) or chr(10) in value or chr(13) in value:
            errors.append('private configuration missing/placeholder: ' + key)
    if len(environment.get('JWT_SECRET_KEY', '')) < 32:
        errors.append('signing key is too short')
    if len(environment.get('BANFEI_RUNTIME_SHARED_KEY', '')) < 32:
        errors.append('runtime shared key is too short')
    if environment.get('BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED') != '1':
        errors.append('approved external transmission flag is absent')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('before', 'configured'), default='before')
    parser.add_argument('--environment', type=Path)
    args = parser.parse_args()
    errors = []
    if platform.machine() != 'aarch64':
        errors.append('target must be ARM64')
    active = sorted(PORTS & listeners())
    if args.phase == 'before' and active:
        errors.append('reserved internal ports already in use: ' + ','.join(map(str, active)))
    for executable in ('/usr/lib/postgresql/16/bin/postgres', '/usr/lib/postgresql/16/bin/initdb', '/usr/local/bin/node'):
        if not os.access(executable, os.X_OK):
            errors.append('required executable missing: ' + executable)
    for name, home in ACCOUNTS.items():
        try:
            pwd.getpwnam(name)
        except KeyError:
            if args.phase == 'configured': errors.append('account absent: ' + name)
        else:
            if args.phase == 'before': errors.append('account exists; reconcile before provisioning: ' + name)
            else: errors.extend(account_errors(name, home))
    if args.phase == 'before':
        for path in ('/opt/banfei-agentarts', '/etc/banfei-agentarts', *ACCOUNTS.values()):
            if Path(path).exists(): errors.append('target exists; reconcile before provisioning: ' + path)
    if args.phase == 'configured':
        for path in ('/opt/banfei-agentarts/venv/bin/python',
                     '/opt/banfei-agentarts/current/frontend/.next/BUILD_ID',
                     '/var/lib/banfei-agentarts-pg/data/PG_VERSION',
                     '/etc/banfei-agentarts/frontend.env',
                     '/etc/banfei-agentarts/data-copy-ready'):
            if not Path(path).is_file(): errors.append('provisioned artifact or copy gate missing: ' + path)
        marker = Path('/etc/banfei-agentarts/data-copy-ready')
        if marker.exists():
            metadata = marker.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) != 0o600:
                errors.append('data-copy gate must be a root-owned 0600 regular file')
    if args.environment:
        try:
            path = args.environment
            metadata = path.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) != 0o600:
                raise ValueError('unsafe private file metadata')
            if path.resolve() != Path('/etc/banfei-agentarts/backend.env'):
                raise ValueError('wrong private file location')
            manager.CONFIG = path
            errors.extend(configuration_errors(manager.read_environment()))
        except Exception:
            errors.append('private configuration cannot be safely checked; values were not printed')
    elif args.phase == 'configured':
        errors.append('configured phase requires the isolated backend environment file')
    print(json.dumps({'read_only': True, 'phase': args.phase, 'architecture': platform.machine(),
        'internal_ports_in_use': active, 'local_checks_passed': not errors, 'blockers': errors,
        'not_verified': ['ARM data copy completion', 'shared Caddy route', 'cloud Runtime authentication and model calls']}, ensure_ascii=False))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
