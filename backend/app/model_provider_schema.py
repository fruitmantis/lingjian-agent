"""Explicit schema 21 -> 22 provider split. Never called at application startup."""
import uuid
from .storage_models import model_providers

LEGACY_COLUMNS = ('provider','base_url','api_key','api_key_source','api_key_env_name')

def migrate(conn):
    conn.lock_writer()
    version=conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()
    if not version or version[0] != '21':
        raise RuntimeError('Provider migration requires schema 21')
    rows=conn.execute('SELECT * FROM model_configs ORDER BY created_at,id').fetchall()
    model_providers.create(conn.connection)
    conn.execute('ALTER TABLE model_configs ADD COLUMN provider_id TEXT')
    groups={}
    for row in rows:
        # Compare stored identity, never guessed vendor/domain or resolved env secrets.
        identity=(row['provider'],row['base_url'],'openai_chat_completions',
                  row['api_key'],row['api_key_source'],row['api_key_env_name'])
        provider_id=groups.get(identity)
        if provider_id is None:
            provider_id=str(uuid.uuid4());groups[identity]=provider_id
            conn.execute("""INSERT INTO model_providers
                (id,name,base_url,protocol,api_key,api_key_source,api_key_env_name,created_at,updated_at)
                VALUES (?,?,?,'openai_chat_completions',?,?,?,?,?)""",
                (provider_id,row['provider'] or '未命名提供商',row['base_url'],row['api_key'],
                 row['api_key_source'],row['api_key_env_name'],row['created_at'],row['updated_at']))
        conn.execute('UPDATE model_configs SET provider_id=? WHERE id=?',(provider_id,row['id']))
    conn.execute('ALTER TABLE model_configs ALTER COLUMN provider_id SET NOT NULL')
    conn.execute('ALTER TABLE model_configs ADD CONSTRAINT fk_model_configs_provider FOREIGN KEY(provider_id) REFERENCES model_providers(id) ON DELETE RESTRICT')
    for column in LEGACY_COLUMNS:
        conn.execute(f'ALTER TABLE model_configs DROP COLUMN {column}')
    conn.execute("UPDATE app_metadata SET value='22' WHERE key='schema_version'")
    return {'schema_version':'22','models':len(rows),'providers':len(groups)}
