"""Seed the database selected by LINGJIAN_DATABASE_PATH with synthetic identities."""

import json
from datetime import datetime, timezone

from backend.app.auth import hash_password
from backend.app.database import get_db, initialize_storage


PASSWORD = "ValidationPass123"
USERS = [
    ("admin-1-id", "admin1", "管理员一", "admin", "active", 0, None),
    ("admin-2-id", "admin2", "管理员二", "admin", "active", 0, None),
    ("user-a-id", "user_a", "用户 A", "user", "active", 0, None),
    ("user-b-id", "user_b", "用户 B", "user", "active", 0, None),
    ("first-login-id", "user_first_login", "首次登录用户", "user", "active", 1, None),
    ("disabled-id", "user_disabled", "停用用户", "user", "disabled", 0, None),
    ("locked-id", "user_locked", "锁定用户", "user", "active", 0, "2999-01-01T00:00:00+00:00"),
]


def recommendation() -> list[dict]:
    return [{
        "partnerId": "partner-1", "partnerName": "验证伙伴", "matchScore": "92",
        "matchedCapabilities": "AI,数据治理", "matchedIndustries": "制造与工业",
        "matchedRegions": "广东", "recommendationReason": "验证推荐",
        "evidenceCases": "制造知识库案例", "evidenceDeliverables": "方案文档",
        "riskNotes": "资料需复核",
    }]


def seed() -> None:
    from backend.tests.support.model_test_boundary import require_test_database
    require_test_database()
    initialize_storage()
    now = datetime.now(timezone.utc).isoformat()
    password_hash = hash_password(PASSWORD)
    with get_db() as conn:
        for user_id, username, name, role, user_status, must_change, locked_until in USERS:
            conn.execute(
                """INSERT INTO users
                   (id, username, hashed_password, display_name, department, role, status,
                    must_change_password, token_version, failed_login_count, locked_until, created_at, updated_at)
                   VALUES (?, ?, ?, ?, '验证部门', ?, ?, ?, 0, 0, ?, ?, ?)""",
                (user_id, username, password_hash, name, role, user_status, must_change, locked_until, now, now),
            )
        conn.execute(
            """INSERT INTO partners
               (id, name, intro, capabilities, service_areas, industries, ai_profile, status, created_at, updated_at)
               VALUES ('partner-1', '验证伙伴', '仅用于自动化验证', 'AI,数据治理', '广东', '制造与工业',
                       '具备制造知识库实施能力', 'active', ?, ?)""",
            (now, now),
        )
        conn.execute(
            """INSERT INTO cases (id, partner_id, title, description, created_at)
               VALUES ('case-1', 'partner-1', '制造知识库案例', '自动化验证案例', ?)""",
            (now,),
        )
        for prefix, owner_id, owner_name in [("a", "user-a-id", "user_a"), ("b", "user-b-id", "user_b")]:
            for task_status in ["ready", "failed", "partial"]:
                task_id = f"task-{prefix}-{task_status}"
                recs = [] if task_status == "failed" else recommendation()
                conn.execute(
                    """INSERT INTO match_records
                       (id, requirement, recommendations_json, created_at, created_by, owner_user_id,
                        archived_at, task_status, last_error_stage, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
                    (
                        task_id, f"{prefix.upper()}-{task_status}", json.dumps(recs, ensure_ascii=False), now,
                        owner_name, owner_id, task_status,
                        "partner_match" if task_status == "failed" else ("project_opportunity" if task_status == "partial" else None),
                        now,
                    ),
                )
            conn.execute(
                """INSERT INTO match_records
                   (id, requirement, recommendations_json, created_at, created_by, owner_user_id,
                    archived_at, task_status, last_error_stage, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'ready', NULL, ?)""",
                (f"task-{prefix}-archived", f"{prefix.upper()}-archived", json.dumps(recommendation(), ensure_ascii=False), now, owner_name, owner_id, now, now),
            )
            conn.execute(
                """INSERT INTO demand_profiles
                   (id, match_record_id, requirement_text, industry_tags, capability_tags,
                    matched_partner_count, supply_status, created_at)
                   VALUES (?, ?, ?, '制造与工业', '数据治理', 1, 'sufficient', ?)""",
                (f"demand-{prefix}", f"task-{prefix}-ready", f"{prefix.upper()}-ready", now),
            )
            conn.execute(
                """INSERT INTO project_opportunities
                   (id, match_record_id, requirement_text, customer_name, project_name,
                    completeness_score, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 80, ?, ?)""",
                (f"opportunity-{prefix}", f"task-{prefix}-ready", f"{prefix.upper()}-ready", f"客户 {prefix.upper()}", f"项目 {prefix.upper()}", now, now),
            )
        fake_base_url = __import__("os").getenv("VALIDATION_FAKE_LLM_BASE_URL", "")
        # UI-only tests have no enabled model and never start a fake service.
        if not fake_base_url:
            conn.execute("UPDATE model_configs SET enabled=0,is_default=0")
            return
        conn.execute(
            """UPDATE model_configs SET base_url = ?, api_key = 'validation-only-key',
                      api_key_source = 'db', model_name = 'validation-fake', enabled = 1, is_default = 1""",
            (fake_base_url,),
        )


if __name__ == "__main__":
    seed()
