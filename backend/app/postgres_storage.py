"""SQLAlchemy-backed PostgreSQL connections for the existing small SQL repository API.

Only positional parameters are bound; statements use native PostgreSQL syntax. Transactions, constraints and permissions
remain enforced by PostgreSQL and the existing service layer.
"""
from contextlib import contextmanager
from functools import lru_cache
import re
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def validated_url(url):
    try:
        parsed = make_url(url)
    except Exception:
        raise ValueError('DATABASE_URL must be a PostgreSQL URL') from None
    if parsed.drivername not in ('postgresql', 'postgresql+psycopg') or not parsed.database:
        raise ValueError('DATABASE_URL requires PostgreSQL with psycopg and a database name')
    return parsed.set(drivername='postgresql+psycopg')

@lru_cache(maxsize=32)
def engine_for(url):
    return create_engine(validated_url(url), pool_pre_ping=True, hide_parameters=True,
                         connect_args={'connect_timeout':5}, pool_size=5, max_overflow=10)


class Row:
    def __init__(self, row):
        self.row = row
    def keys(self): return self.row._mapping.keys()
    def __getitem__(self, key): return self.row[key] if isinstance(key,(int,slice)) else self.row._mapping[key]
    def __iter__(self): return iter(self.row)
    def __len__(self): return len(self.row)


class Result:
    def __init__(self, result): self.result=result; self.rowcount=result.rowcount
    def fetchone(self):
        row=self.result.fetchone()
        return Row(row) if row is not None else None
    def fetchall(self): return [Row(row) for row in self.result.fetchall()]
    def __iter__(self): return (Row(row) for row in self.result)


def bind_parameters(sql, parameters):
    # Do not treat question marks inside SQL strings/quoted identifiers as parameters.
    chunks=re.split(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\")",sql)
    names=[]
    def bind(_):
        name='p'+str(len(names));names.append(name);return ':'+name
    for i in range(0,len(chunks),2):
        chunks[i]=re.sub(r'\?',bind,chunks[i])
    values=list(parameters or ())
    if len(names)!=len(values):raise ValueError('SQL parameter count mismatch')
    compiled=''.join(chunks)
    compiled=re.sub(r'(:p\d+) IS NULL',r'CAST(\1 AS TEXT) IS NULL',compiled,flags=re.I)
    return compiled,dict(zip(names,values))


class Connection:
    def __init__(self, connection, readonly=False):
        self.connection=connection;self.readonly=readonly;self.locked=False
        if readonly:connection.exec_driver_sql('SET TRANSACTION READ ONLY')
    def lock_writer(self):
        if not self.locked:
            # Keep short writer critical sections serialized inside this schema.
            # Different validation schemas do not block each other.
            self.connection.exec_driver_sql("SELECT pg_advisory_xact_lock(hashtextextended(current_database() || '.' || current_schema(), 179183912))")
            self.locked=True
    def begin_read(self):
        if not self.connection.in_transaction():
            self.connection.begin()
            self.connection.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
    def execute(self,sql,parameters=()):
        normalized=sql.strip().rstrip(';').upper()
        if normalized.startswith(('INSERT ','UPDATE ','DELETE ','CREATE ','ALTER ','DROP ')):
            self.lock_writer()
        sql,values=bind_parameters(sql,parameters)
        return Result(self.connection.execute(text(sql),values))
    def executemany(self,sql,parameters):
        self.lock_writer()
        compiled=[bind_parameters(sql,p) for p in parameters]
        if not compiled:return None
        return Result(self.connection.execute(text(compiled[0][0]),[p for _,p in compiled]))
    def commit(self): self.connection.commit();self.locked=False
    def rollback(self): self.connection.rollback();self.locked=False


@contextmanager
def connect(url,readonly=False):
    with engine_for(url).connect() as raw:
        conn=Connection(raw,readonly)
        try:
            yield conn
            raw.rollback() if readonly else raw.commit()
        except Exception:
            raw.rollback();raise


def verify_schema(url):
    from .storage_models import metadata
    from sqlalchemy import inspect
    with engine_for(url).connect() as conn:
        found=set(inspect(conn).get_table_names())
        if set(metadata.tables)-found:
            raise RuntimeError('PostgreSQL schema is incomplete; explicit migration required')
        if 'last_error_details' not in {c['name'] for c in inspect(conn).get_columns('match_records')}:
            raise RuntimeError('Task failure detail column missing; run explicit additive migration')
        if conn.execute(text("SELECT value FROM app_metadata WHERE key='schema_version'")).scalar()!='20':
            raise RuntimeError('PostgreSQL schema version is not 20; refusing automatic changes')

        if 'profile_chapter_meta' not in {c['name'] for c in inspect(conn).get_columns('partners')}:
            raise RuntimeError('Profile chapter association column missing; explicit additive migration required')

        from .development_partner_schema import verify_optional_partner
        verify_optional_partner(Connection(conn))

        if 'timeout_seconds' in {c['name'] for c in inspect(conn).get_columns('model_configs')}:
            raise RuntimeError('Obsolete per-model timeout column remains; explicit cleanup required')

        if 'last_active_at' not in {c['name'] for c in inspect(conn).get_columns('users')}:
            raise RuntimeError('User activity column missing; explicit migration required')


def initialize_empty_schema(url):
    """Explicit, atomic initialization; refuse every nonempty schema."""
    from sqlalchemy import inspect
    from .storage_models import create_postgres_schema
    from .storage_defaults import seed_defaults
    with engine_for(url).begin() as raw:
        connection = Connection(raw)
        connection.lock_writer()
        if inspect(raw).get_table_names() or inspect(raw).get_view_names():
            raise RuntimeError('PostgreSQL initialization requires an empty schema')
        create_postgres_schema(raw)
        seed_defaults(connection)
    verify_schema(url)
