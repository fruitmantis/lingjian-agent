"""User-operated isolated private setup. Never starts services or opens the API gate."""
import argparse
import contextlib
import fcntl
import getpass
import hashlib
import importlib.util
import io
import json
import multiprocessing
import os
from pathlib import Path
import pwd
import re
import secrets
import stat
import sys
import uuid
import warnings
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from backend.app.runtime_endpoint import operation_url
from backend.agent_runtime.contracts import model_route

DIRECTORY = Path('/etc/banfei-agentarts')
URL = 'https://defaultgw-gzswgzdcgz.cn-southwest-2.huaweicloud-agentarts.com/runtimes/banfei-runtime-test/invocations?endpoint=Latest'
AUTHORS = {'4d9dfe52-2970-4d29-b945-b055c9869914', 'cfe6dcf6-dcdf-42be-a2cf-3ebf04ec64af'}
LOCAL_KEYS = ('DATABASE_URL', 'JWT_SECRET_KEY', 'BANFEI_IDENTITY_ENCRYPTION_KEY')
RUNTIME_KEYS = ('BANFEI_AGENTARTS_BEARER', 'BANFEI_RUNTIME_SHARED_KEY')
BASELINE = 'arm-catalog-576926a-s19-92c35b4e64df'


class SetupError(RuntimeError):
    """Only fixed, non-secret diagnostics may use this exception."""


def hidden(prompt):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            return getpass.getpass(prompt)
    except getpass.GetPassWarning:
        raise SetupError('Hidden input unavailable; input was not saved') from None


def private_read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid() or stat.S_IMODE(s.st_mode) != 0o600 or s.st_nlink != 1:
            raise SetupError('Unsafe private file permissions')
        with os.fdopen(fd, 'rb', closefd=False) as f:
            return f.read()
    finally:
        os.close(fd)


def private_write(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(content); f.flush(); os.fsync(f.fileno())
    except BaseException:
        # This process created this exact root-only temporary file.
        path.unlink()
        raise


def digest(content):
    return hashlib.sha256(content).hexdigest()


def parse(content):
    from dotenv import dotenv_values
    text = content.decode('utf-8')
    keys = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = re.match(r'^([A-Z][A-Z0-9_]*)=', line)
        if not match:
            raise ValueError('Unsupported environment syntax')
        keys.append(match.group(1))
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate environment keys')
    return dict(dotenv_values(stream=io.StringIO(text), interpolate=False))


def render(original, values):
    removed = set(values) | {'BOOTSTRAP_ADMIN_USERNAME', 'BOOTSTRAP_ADMIN_PASSWORD'}
    lines = [line for line in original.decode().splitlines() if line.split('=', 1)[0].strip() not in removed]
    for key, value in values.items():
        if not value or re.search(r'__[A-Z][A-Z0-9_]*__', value) or any(c.isspace() or c in '\"\'\\`$' for c in value):
            raise ValueError('Unsupported private value format')
        lines.append(key + '=' + value)
    return ('\n'.join(lines) + '\n').encode()


def configured(values):
    spec = importlib.util.spec_from_file_location('private_setup_preflight', ROOT / 'deploy/agentarts/arm/preflight.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    if module.configuration_errors(values):
        raise ValueError('Private configuration incomplete or invalid')
    from cryptography.fernet import Fernet
    Fernet(values['BANFEI_IDENTITY_ENCRYPTION_KEY'].encode())


def verify_runtime(values):
    import httpx
    with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
        response = client.get(operation_url(URL, 'runtime-info'), headers={
            'Authorization': 'Bearer ' + values['BANFEI_AGENTARTS_BEARER'],
            'X-Banfei-Runtime-Key': values['BANFEI_RUNTIME_SHARED_KEY'],
            'X-Hw-Agentarts-Session-Id': str(uuid.uuid4())})
    if response.status_code != 200:
        raise SetupError('[RUNTIME_HTTP_' + str(response.status_code) + '] Runtime-info认证未通过；本地尚未保存。')
    body = response.json()
    if body.get('protocol') != 'banfei-runtime-v1' or body.get('provider_route') != model_route('https://api.deepseek.com', 'deepseek-flash'):
        raise SetupError('Runtime route or protocol mismatch')
    uuid.UUID(body['incarnation'])


def validate_state(state):
    if state['database'] != 'banfei_agentarts' or state['port'] != '55432' or state['data'] != '/var/lib/banfei-agentarts-pg/data' or state['schema'] != '19':
        raise SetupError('Wrong independent PostgreSQL instance')
    if state['role'] != [False, False, False, False, True]:
        raise SetupError('Unexpected application role privileges')
    users = state['users']
    authors = [x for x in users if x['id'] in AUTHORS]
    if len(authors) != 2 or any(x['role'] != 'user' or x['status'] != 'disabled' or not x['password_null'] for x in authors):
        raise SetupError('Source author metadata changed; refusing setup')
    others = [x for x in users if x['id'] not in AUTHORS]
    if any(x['role'] != 'admin' or x['status'] != 'active' or x['password_null'] for x in others) or len(others) > 1 or state['identity_rows'] or state['history_rows']:
        raise SetupError('Existing business identities/history require separate maintenance')
    return bool(others)


def pg_state(conn):
    def one(sql): return conn.execute(sql).fetchone()[0]
    users = conn.execute('SELECT id,role,status,hashed_password IS NULL FROM users ORDER BY id').fetchall()
    role = conn.execute("SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolcanlogin FROM pg_roles WHERE rolname='banfei_agentarts_app'").fetchone()
    return {'database': one('SELECT current_database()'), 'port': one('SHOW port'), 'data': one('SHOW data_directory'),
            'schema': one("SELECT value FROM app_metadata WHERE key='schema_version'"), 'role': list(role or []),
            'users': [dict(zip(('id','role','status','password_null'), x)) for x in users],
            'identity_rows': one('SELECT (SELECT count(*) FROM user_identity_keys)+(SELECT count(*) FROM identity_credentials)+(SELECT count(*) FROM identity_challenges)'),
            'history_rows': one('SELECT (SELECT count(*) FROM match_records)+(SELECT count(*) FROM development_plans)')}


def pg_worker(pipe, uid, gid, parent_pipe, inherited_lock_fd):
    # psycopg and libpq are loaded before dropping privilege: no shared venv
    # permissions, root peer mapping, password or authentication changes needed.
    import psycopg
    from psycopg import sql
    request = {}
    try:
        parent_pipe.close()
        if inherited_lock_fd is not None: os.close(inherited_lock_fd)
        for key in list(os.environ):
            if key.startswith('PG'): os.environ.pop(key)
        os.setgroups([]); os.setgid(gid); os.setuid(uid)
        with psycopg.connect(dbname='banfei_agentarts', user='banfei_agentarts_admin', host='/run/banfei-agentarts-pg', port=55432, connect_timeout=5, passfile='/dev/null/disabled-pgpass', sslmode='disable', options='') as conn:
            while True:
                request = pipe.recv(); action = request['action']
                if action == 'close': conn.rollback(); return
                if action == 'inspect':
                    result = pg_state(conn); conn.rollback()
                elif action == 'marker':
                    # The old transaction must have released the SAME lock.
                    # A fresh READ COMMITTED query after acquiring it sees the
                    # terminal commit marker, never an in-flight snapshot.
                    conn.execute('SET TRANSACTION ISOLATION LEVEL READ COMMITTED')
                    settled = conn.execute('SELECT pg_try_advisory_xact_lock(55432,20261002)').fetchone()[0]
                    if settled is not True:
                        conn.rollback(); raise SetupError('Prior transaction is not settled; recovery deferred')
                    row = conn.execute("SELECT value FROM app_metadata WHERE key='agentarts_private_setup'").fetchone()
                    result = {'settled':True, 'marker':row[0] if row else None}; conn.rollback()
                elif action == 'prepare':
                    conn.execute('SELECT pg_advisory_xact_lock(55432,20261002)')
                    conn.execute('LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE')
                    state = pg_state(conn); has_admin = validate_state(state)
                    if state != request['expected']:
                        raise SetupError('Database changed during input')
                    # Prevent this session from logging statements containing a
                    # verifier or bound private values, including error statements.
                    conn.execute("SET LOCAL log_statement='none'")
                    conn.execute("SET LOCAL log_min_error_statement='panic'")
                    conn.execute("SET LOCAL password_encryption='scram-sha-256'")
                    password = request['password']
                    if password:
                        conn.execute(sql.SQL('ALTER ROLE banfei_agentarts_app PASSWORD {}').format(sql.Literal(password)))
                    admin = request['admin']
                    if has_admin and admin is not None:
                        raise SetupError('Existing administrator must be preserved')
                    if not has_admin:
                        if not admin: raise SetupError('Explicit administrator input required')
                        conn.execute("INSERT INTO users(id,username,display_name,hashed_password,role,status,must_change_password,created_at,updated_at) VALUES (%s,%s,'系统管理员',%s,'admin','active',1,%s,%s)",
                                     (admin['id'], admin['username'], admin['hash'], admin['now'], admin['now']))
                    conn.execute("INSERT INTO app_metadata(key,value) VALUES ('agentarts_private_setup',%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value", (request['setup_id'],))
                    validate_state(pg_state(conn)); result = True
                elif action == 'commit': conn.commit(); result = True
                elif action == 'rollback': conn.rollback(); result = True
                else: raise ValueError('Invalid internal action')
                pipe.send({'id':request['id'], 'action':action, 'ok':True, 'result':result})
    except BaseException:
        # Do not send exception text, statements, input or credentials to output.
        try: pipe.send({'id':request.get('id'), 'action':request.get('action'), 'ok':False})
        except BaseException: pass
    finally:
        pipe.close()


class Peer:
    def __init__(self, inherited_lock_fd=None):
        self.inherited_lock_fd = inherited_lock_fd
        self.sequence = 0
        self.poisoned = False
    def __enter__(self):
        import psycopg  # Load native dependencies as root before fork.
        account = pwd.getpwnam('banfei-agentarts-pg')
        ctx = multiprocessing.get_context('fork')
        self.pipe, child = ctx.Pipe()
        self.process = ctx.Process(target=pg_worker, args=(child, account.pw_uid, account.pw_gid, self.pipe, self.inherited_lock_fd))
        self.process.start(); child.close(); return self
    def invalidate(self):
        self.poisoned = True
        with contextlib.suppress(Exception): self.pipe.close()
    def request(self, action, **values):
        if self.poisoned:
            raise SetupError('Private transaction channel is unusable; recovery requires a new connection')
        if action == 'marker' and self.sequence != 0:
            raise SetupError('Recovery requires a fresh private PostgreSQL connection')
        self.sequence += 1
        try:
            self.pipe.send({'id':self.sequence, 'action':action, **values})
            if not self.pipe.poll(20):
                raise SetupError('Private PostgreSQL response timed out; outcome is unknown')
            reply = self.pipe.recv()
            if (not isinstance(reply,dict) or type(reply.get('id')) is not int
                    or reply['id'] != self.sequence or reply.get('action') != action
                    or reply.get('ok') is not True or 'result' not in reply):
                raise SetupError('Private PostgreSQL response mismatch; outcome is unknown')
            result = reply['result']
            if action in ('prepare','commit','rollback') and result is not True:
                raise SetupError('Invalid transaction acknowledgement')
            if action == 'marker': validate_marker(result)
            if action == 'inspect' and not isinstance(result,dict):
                raise SetupError('Invalid PostgreSQL inspection response')
            return result
        except BaseException:
            self.invalidate()
            raise
    def __exit__(self, *_):
        if not self.poisoned:
            with contextlib.suppress(Exception): self.pipe.send({'id':self.sequence+1, 'action':'close'})
        self.invalidate(); self.process.join(5)
        if self.process.is_alive(): self.process.terminate(); self.process.join(5)


def validate_marker(result):
    if (type(result) is not dict or set(result) != {'settled','marker'}
            or result['settled'] is not True
            or (result['marker'] is not None and
                (type(result['marker']) is not str or not re.fullmatch(r'[0-9a-f]{32}', result['marker'])))):
        raise SetupError('Recovery outcome is unknown; keep private recovery records')
    return result['marker']


class Store:
    def __init__(self, directory=DIRECTORY):
        self.directory = directory; self.config = directory / 'backend.env'
        self.pending = directory / 'private-setup-pending'
        s = directory.lstat()
        if directory.resolve() != directory or not stat.S_ISDIR(s.st_mode) or s.st_uid != os.geteuid() or s.st_mode & 0o022:
            raise SetupError('Unsafe private configuration directory')
        self.lock = None
    def __enter__(self):
        path = self.directory / 'private-setup.lock'
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self.lock = os.fdopen(fd, 'rb')
        s = os.fstat(fd)
        if s.st_uid != os.geteuid() or stat.S_IMODE(s.st_mode) != 0o600 or s.st_nlink != 1:
            self.lock.close(); raise SetupError('Unsafe setup lock')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB); return self
    def __exit__(self, *_):
        if self.lock: self.lock.close()
    def sync(self):
        fd = os.open(self.directory, os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    def live_safe(self):
        if (self.directory / 'private-config-ready').exists():
            raise SetupError('Business gate is already open; use separate maintenance')
        import subprocess
        result = subprocess.run(['/usr/bin/systemctl','is-active','banfei-agentarts-backend.service'], capture_output=True, text=True)
        if result.stdout.strip() not in ('inactive','failed'):
            raise SetupError('Isolated backend must remain stopped')
        if private_read(self.directory / 'data-copy-ready').decode().strip() != BASELINE:
            raise SetupError('Wrong catalog baseline')
    def cleanup(self, info):
        for name in ('candidate', 'rollback'):
            path = self.directory / info[name]
            if path.exists(): private_read(path); path.unlink()
        self.pending.unlink(); self.sync()
    def recover(self, peer):
        if not self.pending.exists(): return
        info = json.loads(private_read(self.pending))
        if not re.fullmatch(r'[0-9a-f]{32}', info['id']): raise SetupError('Invalid recovery metadata')
        for key in ('candidate','rollback'):
            if info[key] != '.private-setup-' + info['id'] + '-' + key: raise SetupError('Invalid recovery path')
        current = private_read(self.config)
        committed = validate_marker(peer.request('marker')) == info['id']
        if committed:
            if digest(current) != info['new']: raise SetupError('Committed configuration changed; manual reconciliation required')
        else:
            if digest(current) not in (info['old'], info['new']): raise SetupError('Configuration changed; recovery refused')
            backup = self.directory / info['rollback']
            if digest(current) == info['new'] and info['new'] != info['old']:
                if digest(private_read(backup)) != info['old']: raise SetupError('Unsafe recovery snapshot')
                os.replace(backup, self.config); self.sync()
            # If the old file is already in place, a crash may have occurred
            # before snapshot creation or after restoration. No secret is lost.
        self.cleanup(info)
        return 'committed' if committed else 'rolled_back'
    def commit(self, peer, original, candidate, expected, password, admin):
        # A durable, root-only rollback snapshot coordinates PG and the file.
        # A crash keeps the backend gate closed and is reconciled next run by
        # the non-secret transaction ID atomically committed inside PostgreSQL.
        configured(parse(candidate))
        if private_read(self.config) != original: raise SetupError('Configuration changed during input')
        ident = uuid.uuid4().hex
        info = {'id':ident,'old':digest(original),'new':digest(candidate),
                'candidate':'.private-setup-'+ident+'-candidate','rollback':'.private-setup-'+ident+'-rollback'}
        backup = self.directory / info['rollback']; staged = self.directory / info['candidate']
        if self.pending.exists(): raise SetupError('Pending transaction must be reconciled first')
        journal_created = False
        try:
            # Persist the non-secret journal before any temporary secret file.
            private_write(self.pending, json.dumps(info).encode()); journal_created = True; self.sync()
            private_write(backup, original); private_write(staged, candidate); self.sync()
        except BaseException:
            if journal_created: self.cleanup(info)
            raise
        try:
            peer.request('prepare', expected=expected, password=password, admin=admin, setup_id=ident)
            if private_read(self.config) != original: raise SetupError('Configuration changed before replacement')
            os.replace(staged, self.config); self.sync()
            peer.request('commit')
        except BaseException:
            # Never queue rollback or inspect on a channel with uncertain
            # replies. Preserve BOTH private snapshots and the journal. Only a
            # later invocation, with a fresh connection and the advisory-lock
            # settlement check, may reconcile the committed marker.
            peer.invalidate()
            raise SetupError('Setup outcome unknown; recovery records and closed gate retained. Exit and re-run to reconcile') from None
        self.cleanup(info)


def validate_admin_password(password, confirmation):
    if password != confirmation:
        raise SetupError('[ADMIN_PASSWORD_MISMATCH] 两次管理员密码不一致，请重新输入两次。')
    try:
        encoded = password.encode('utf-8')
    except UnicodeEncodeError:
        raise SetupError('[ADMIN_PASSWORD_ENCODING] 密码包含无法编码的字符，请重新输入。') from None
    if len(encoded) > 72:
        raise SetupError('[ADMIN_PASSWORD_TOO_LONG] 管理员密码的UTF-8长度不能超过72字节，请缩短后重试。')
    if len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise SetupError('[ADMIN_PASSWORD_REQUIREMENTS] 管理员密码至少8个字符，并同时包含字母和数字。')


def read_admin_password():
    while True:
        password = hidden('新管理员密码（至少8字符，含字母数字，UTF-8不超过72字节）：')
        confirmation = hidden('再次输入管理员密码：')
        try:
            validate_admin_password(password, confirmation)
            return password
        except SetupError as error:
            # Validation retries remain in memory. Runtime inputs need not be
            # entered again; no administrator/secret is persisted here.
            print(str(error) + ' 尚未保存；可按Ctrl+C取消。', file=sys.stderr)


def collect(values, state):
    has_admin = validate_state(state)
    if has_admin and not all(values.get(k) for k in LOCAL_KEYS):
        raise SetupError('Existing administrator with missing local keys requires separate repair')
    print('仅配置 AgentArts：保留原版、作者引用和已有管理员。')
    print('缺失时在本机生成独立数据库口令、JWT签名键、Fernet键；运行时两把密钥由你隐藏输入。')
    print('秘密只保存到新 backend.env（root:root 0600）及新PG认证存储；管理员只存bcrypt哈希。')
    print('事务期间临时保留同目录0600回滚文件；异常恢复前不开放业务。不会启动服务或调用模型。')
    if input('确认批准以上动作，请输入 CONFIGURE AGENTARTS：').strip() != 'CONFIGURE AGENTARTS':
        raise SetupError('Explicit local approval not given')
    result = dict(values)
    for key,label in [(RUNTIME_KEYS[0],'平台 APIKey'),(RUNTIME_KEYS[1],'已轮换的新 SHARED_KEY')]:
        entered = hidden(label + ('（留空保留已有值）' if values.get(key) else '') + '：')
        result[key] = entered or values.get(key,'')
    if not result.get('BANFEI_AGENTARTS_BEARER'):
        raise SetupError('[RUNTIME_API_KEY_REQUIRED] 平台APIKey不能为空；尚未保存。')
    if len(result.get('BANFEI_RUNTIME_SHARED_KEY','')) < 32:
        raise SetupError('[RUNTIME_SHARED_KEY_REQUIREMENTS] 新SHARED_KEY至少32个字符；尚未保存。')
    admin = None
    if not has_admin:
        username = input('新独立管理员用户名：').strip().lower()
        if not re.fullmatch(r'[a-z][a-z0-9_.-]{2,31}', username):
            raise SetupError('[ADMIN_USERNAME_REQUIREMENTS] 用户名为3至32个小写字母、数字或_.-，且以字母开头。')
        password = read_admin_password()
        if input('确认创建该独立管理员，请输入 CREATE ADMIN：').strip() != 'CREATE ADMIN':
            raise SetupError('Explicit administrator approval not given')
        import bcrypt
        admin = {'id':str(uuid.uuid4()), 'username':username, 'hash':bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode(), 'now':datetime.now(timezone.utc).isoformat()}
    db_password = None
    if not result.get('DATABASE_URL'):
        db_password = secrets.token_urlsafe(48)
        result['DATABASE_URL'] = 'postgresql+psycopg://banfei_agentarts_app:'+db_password+'@127.0.0.1:55432/banfei_agentarts'
    if not result.get('JWT_SECRET_KEY'): result['JWT_SECRET_KEY'] = secrets.token_urlsafe(48)
    if not result.get('BANFEI_IDENTITY_ENCRYPTION_KEY'):
        from cryptography.fernet import Fernet
        result['BANFEI_IDENTITY_ENCRYPTION_KEY'] = Fernet.generate_key().decode()
    result['BANFEI_RUNTIME_URL'] = URL
    configured(result)
    return result, db_password, admin


DIAGNOSTIC_STAGE = 'preflight'


def main():
    global DIAGNOSTIC_STAGE
    DIAGNOSTIC_STAGE = 'preflight'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-runtime',action='store_true',help='Before saving: one runtime-info GET, no model request')
    args = parser.parse_args()
    if os.geteuid() != 0 or not sys.stdin.isatty() or not sys.stderr.isatty():
        raise SetupError('Use your own root interactive terminal; no piped credentials')
    for key in list(os.environ):
        if key.startswith('PG'): os.environ.pop(key)
    with Store() as store:
        store.live_safe()
        with Peer(inherited_lock_fd=store.lock.fileno()) as peer:
            store.recover(peer)
            original = private_read(store.config); values = parse(original)
            DIAGNOSTIC_STAGE = 'database_preflight'
            state = peer.request('inspect'); validate_state(state)
            # Check the fixed non-secret profile before accepting private input.
            if any(values.get(k) != v for k,v in {'BANFEI_DEPLOYMENT_PROFILE':'agentarts','BANFEI_MATCH_EXECUTOR':'runtime','BANFEI_DEVELOPMENT_EXECUTOR':'runtime','BANFEI_IDENTITY_ORIGIN':'http://banfei-agentarts.test','BANFEI_RUNTIME_EXTERNAL_DATA_APPROVED':'1'}.items()):
                raise SetupError('Wrong isolated deployment profile')
            DIAGNOSTIC_STAGE = 'interactive_input'
            values, password, admin = collect(values,state)
            if password is None:
                # Retained local keys are never rotated to conceal a mismatch.
                import psycopg
                DIAGNOSTIC_STAGE = 'database_connection'
                with psycopg.connect(values['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://', 1), connect_timeout=5, passfile='/dev/null/disabled-pgpass', sslmode='disable', options='') as conn:
                    if conn.execute('SELECT current_database(),current_user').fetchone() != ('banfei_agentarts','banfei_agentarts_app'):
                        raise SetupError('Existing private database connection is invalid')
            if args.verify_runtime:
                DIAGNOSTIC_STAGE = 'runtime_verification'
                verify_runtime(values)
            DIAGNOSTIC_STAGE = 'configuration_validation'
            candidate = render(original,values)
            store.live_safe()
            DIAGNOSTIC_STAGE = 'private_transaction'
            store.commit(peer,original,candidate,state,password,admin)
    if args.verify_runtime: print('Runtime-info认证与deepseek-flash路由已验证；未调用模型。')
    print('独立私有配置已保存；已有管理员未覆盖，作者仍禁用。未启动服务，维护503仍保留。')
    return 0


def diagnostic_code():
    return {'database_preflight':'DB_UNAVAILABLE','database_connection':'DB_UNAVAILABLE',
            'runtime_verification':'RUNTIME_UNAVAILABLE','interactive_input':'INPUT_INTERNAL',
            'configuration_validation':'CONFIG_INVALID','private_transaction':'TRANSACTION_UNCERTAIN'}.get(DIAGNOSTIC_STAGE,'SETUP_PREFLIGHT')


def run_cli():
    try:
        return main()
    except SetupError as error:
        message = str(error)
        prefix = '' if message.startswith('[') else '[' + diagnostic_code() + '] '
        print(prefix + message + ' 未开放业务。', file=sys.stderr)
    except EOFError:
        print('[INPUT_EOF] 输入已结束，配置未完成；未开放业务。请在交互终端重试。', file=sys.stderr)
    except KeyboardInterrupt:
        print('[INPUT_CANCELLED] 已取消；未开放业务。若存在恢复记录，下次运行会先协调。', file=sys.stderr)
    except Exception:
        # Fixed phase codes only: never format the exception, private values,
        # SQL, HTTP bodies/headers, or credential lengths.
        code = diagnostic_code()
        print('[' + code + '] 此阶段未完成；未开放业务。请仅反馈错误码，不要粘贴秘密。', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(run_cli())
