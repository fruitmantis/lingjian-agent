"""Small credential/challenge schema shared by explicit migration and test fixtures."""
CREDENTIAL_SQL = '''CREATE TABLE IF NOT EXISTS identity_credentials (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 kind TEXT NOT NULL CHECK(kind IN ('passkey','browser')),
 credential_id TEXT UNIQUE, public_key TEXT, sign_count BIGINT NOT NULL DEFAULT 0,
 secret_hash TEXT UNIQUE, created_at TEXT NOT NULL,
 CHECK((kind='passkey' AND credential_id IS NOT NULL AND public_key IS NOT NULL AND secret_hash IS NULL)
 OR (kind='browser' AND secret_hash IS NOT NULL AND credential_id IS NULL AND public_key IS NULL)))'''
CHALLENGE_SQL = '''CREATE TABLE IF NOT EXISTS identity_challenges (
 id TEXT PRIMARY KEY, challenge TEXT NOT NULL, binding_hash TEXT NOT NULL,
 purpose TEXT NOT NULL CHECK(purpose IN ('register','authenticate')),
 user_id TEXT, expires_at TEXT NOT NULL)'''

KEY_SQL = """CREATE TABLE IF NOT EXISTS user_identity_keys (
 user_id TEXT PRIMARY KEY REFERENCES users(id), key_hash TEXT NOT NULL UNIQUE,
 encrypted_key TEXT NOT NULL, created_at TEXT NOT NULL)"""


REVOKED_KEY_SQL = """CREATE TABLE IF NOT EXISTS revoked_identity_keys (
 key_hash TEXT PRIMARY KEY, revoked_at TEXT NOT NULL)"""
