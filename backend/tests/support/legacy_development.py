"""Seed a historical confirmed pointer; application code must never use or change it."""
from backend.app.database import get_db


def legacy_confirmed(plan_id, version_id, user):
    with get_db() as conn:
        conn.execute('UPDATE development_plans SET confirmed_version_id=? WHERE id=?', (version_id, plan_id))
