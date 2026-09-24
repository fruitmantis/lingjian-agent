"""Preserved schema 13/14 data fixtures; retired credentials cannot authenticate."""
import secrets
import uuid
from datetime import datetime, timezone
import httpx
from backend.app.auth import create_token, record_audit
from backend.app.database import get_db
from backend.app.identity_keys import digest
from ..conftest import make_user


def legacy_browser(client=None):
    user = make_user('legacy_browser_'+uuid.uuid4().hex)
    secret = secrets.token_urlsafe(32)
    with get_db() as conn:
        conn.execute("INSERT INTO identity_credentials(id,user_id,kind,secret_hash,created_at) VALUES (?,?,'browser',?,?)",
                     (str(uuid.uuid4()),user['id'],digest(secret),datetime.now(timezone.utc).isoformat()))
        record_audit(conn,'identity.created',actor_user_id=user['id'],target_user_id=user['id'])
        record_audit(conn,'identity.login',actor_user_id=user['id'],target_user_id=user['id'])
    return httpx.Response(200,request=httpx.Request('POST','http://testserver/retired-fixture'),json={'user':user,'access_token':create_token(user['id'],user['username'],'user',auth_method='browser')},
                          headers={'set-cookie':'banfei_browser_identity='+secret})


def legacy_passkey(client=None):
    user=make_user('legacy_passkey_'+uuid.uuid4().hex)
    with get_db() as conn:
        conn.execute("INSERT INTO identity_credentials(id,user_id,kind,credential_id,public_key,created_at) VALUES (?,?,'passkey',?,?,?)",
                     (str(uuid.uuid4()),user['id'],secrets.token_urlsafe(32),'historical-test-public-key',datetime.now(timezone.utc).isoformat()))
        record_audit(conn,'identity.created',actor_user_id=user['id'],target_user_id=user['id'])
    return ({'user':user,'access_token':create_token(user['id'],user['username'],'user',auth_method='passkey')},None,None,None,None,None)
