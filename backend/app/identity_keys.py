"""Long-lived personal keys, encrypted for owner-only redisplay; never log values."""
import hashlib
import json
import os
import re
import secrets
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken


def cipher():
    value = os.getenv('BANFEI_IDENTITY_ENCRYPTION_KEY', '')
    try:
        return Fernet(value.encode('ascii'))
    except (ValueError, UnicodeError):
        raise RuntimeError('BANFEI_IDENTITY_ENCRYPTION_KEY must be a configured Fernet key') from None


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def create_identity_key(conn, user_id):
    # Called only when creating a new identity, never as a read/legacy migration.
    for _ in range(5):
        key = 'bf_' + secrets.token_urlsafe(32)
        key_hash = digest(key)
        if not conn.execute('SELECT 1 FROM revoked_identity_keys WHERE key_hash=?', (key_hash,)).fetchone() and not conn.execute('SELECT 1 FROM user_identity_keys WHERE key_hash=?', (key_hash,)).fetchone():
            break
    else:
        raise RuntimeError('Could not allocate identity credential')
    encrypted = cipher().encrypt(json.dumps({'user_id': user_id, 'key': key}).encode()).decode()
    conn.execute('INSERT INTO user_identity_keys(user_id,key_hash,encrypted_key,created_at) VALUES (?,?,?,?)',
                 (user_id, digest(key), encrypted, datetime.now(timezone.utc).isoformat()))


def reveal_identity_key(row):
    try:
        value = json.loads(cipher().decrypt(row['encrypted_key'].encode()))
        if value['user_id'] != row['user_id'] or not secrets.compare_digest(digest(value['key']), row['key_hash']):
            raise ValueError()
        return value['key']
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise RuntimeError('Identity credential could not be decrypted') from None


def masked_identity_key(row):
    """Admin-only hint; damaged/unavailable credentials never expose raw data."""
    try:
        key = reveal_identity_key(row)
    except RuntimeError:
        return None
    if not re.fullmatch(r'bf_[A-Za-z0-9_-]{43}', key):
        return None
    return key[:5] + '…' + key[-5:]
