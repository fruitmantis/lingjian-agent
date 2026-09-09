"""SQLAlchemy-backed PostgreSQL connections for the existing small SQL repository API.

Only parameters/dialect syntax are adapted. Transactions, constraints and permissions
remain enforced by PostgreSQL and the existing service layer.
"""
from contextlib import contextmanager
from functools import lru_cache
import re
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


@lru_cache(maxsize=8)
def engine_for(url):
    parsed = make_url(url)
    if parsed.drivername == 'postgresql':
        parsed = parsed.set(drivername='postgresql+psycopg')
    if parsed.drivername != 'postgresql+psycopg':
        raise ValueError('Only PostgreSQL with psycopg is supported')
    return create_engine(parsed, pool_pre_ping=True, hide_parameters=True,
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


def postgres_sql(sql):
    # These are the complete JSON functions used by the current catalog/task queries.
    sql=sql.replace("json_array(json_object('partnerName',t.name))", "CAST(jsonb_build_array(jsonb_build_object('partnerName',t.name)) AS TEXT)")
    scalar=r"json_extract\((\w+(?:\.\w+)?),'\$\.([\w.]+)'\)"
    sql=re.sub(scalar,lambda m:"("+m[1]+"::jsonb #>> '{"+m[2].replace('.',',')+"}')",sql)
    array=r"json_array_length\((\w+(?:\.\w+)?),'\$\.([\w.]+)'\)"
    sql=re.sub(array,lambda m:"jsonb_array_length("+m[1]+"::jsonb #> '{"+m[2].replace('.',',')+"}')",sql)
    each=r"json_each\((\w+(?:\.\w+)?),'\$\.([\w.]+)'\)"
    sql=re.sub(each,lambda m:"jsonb_array_elements_text("+m[1]+"::jsonb #> '{"+m[2].replace('.',',')+"}')",sql)
    return re.sub(r'\binstr\(', 'strpos(', sql, flags=re.I)


def bind_parameters(sql, parameters):
    # Do not treat question marks inside SQL strings/quoted identifiers as parameters.
    chunks=re.split(r"('(?:''|[^'])*'|\"(?:\"\"|[^\"])*\")",sql)
    names=[]
    def bind(_):
        name='p'+str(len(names));names.append(name);return ':'+name
    for i in range(0,len(chunks),2):
        chunks[i]=re.sub(r'\?',bind,chunks[i])
        chunks[i]=re.sub(r'\bLIKE\b','ILIKE',chunks[i],flags=re.I)
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
            # Preserve the existing SQLite single-writer critical sections. Model work
            # stays outside these short transactions; no process-local lock is used.
            self.connection.exec_driver_sql('SELECT pg_advisory_xact_lock(179183912)')
            self.locked=True
    def execute(self,sql,parameters=()):
        normalized=sql.strip().rstrip(';').upper()
        if normalized=='BEGIN IMMEDIATE':
            self.lock_writer();return None
        if normalized=='BEGIN':
            if not self.connection.in_transaction():
                self.connection.begin()
                # Existing explicit read transactions expect one consistent snapshot.
                self.connection.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            return None
        if normalized.startswith(('INSERT ','UPDATE ','DELETE ','CREATE ','ALTER ','DROP ')):
            self.lock_writer()
        sql,values=bind_parameters(postgres_sql(sql),parameters)
        return Result(self.connection.execute(text(sql),values))
    def executemany(self,sql,parameters):
        self.lock_writer()
        compiled=[bind_parameters(postgres_sql(sql),p) for p in parameters]
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
        if conn.execute(text("SELECT value FROM app_metadata WHERE key='schema_version'")).scalar()!='12':
            raise RuntimeError('PostgreSQL schema version is not 12; refusing automatic changes')
