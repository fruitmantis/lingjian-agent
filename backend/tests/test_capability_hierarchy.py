"""Tests for the two-tier capability tag hierarchy, schema 25 -> 26 migration, APIs, Excel transfer, matching, and demand reports."""
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from openpyxl import load_workbook
import pytest
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from backend.app import (
    development_model,
    match_understanding,
    partner_match_context as match_context,
    partner_transfer,
)
from backend.app.capability_hierarchy import CATALOG, l1_l2_hierarchy_map
from backend.app.capability_hierarchy_schema import migrate
from backend.app.database import get_db
from backend.app.postgres_storage import engine_for, verify_schema
from backend.app.routers import match
from backend.business import matching
from .conftest import auth_headers, make_partner, make_task, make_user, recommendation
from .postgres_support import snapshot
from .test_partner_transfer import save, upload


def schema25(conn, *, unused_preset_cat="基础设施（旧）"):
    """Reconstruct a realistic schema-25 state inside the disposable test PG schema."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("DROP INDEX IF EXISTS uq_capability_tags_l1_name")
    conn.execute("DROP INDEX IF EXISTS uq_capability_tags_l2_parent_name")
    conn.execute("ALTER TABLE capability_tags DROP CONSTRAINT IF EXISTS fk_capability_tags_parent")
    conn.execute("ALTER TABLE capability_tags DROP CONSTRAINT IF EXISTS ck_capability_tags_hierarchy")
    conn.execute("ALTER TABLE capability_tags DROP CONSTRAINT IF EXISTS ck_capability_tags_level")
    conn.execute("DELETE FROM capability_tags WHERE level = 2")
    conn.execute("DELETE FROM capability_tags WHERE name = 'TZ行业大模型'")
    conn.execute("ALTER TABLE capability_tags DROP COLUMN parent_id")
    conn.execute("ALTER TABLE capability_tags DROP COLUMN level")
    conn.execute("ALTER TABLE capability_tags ADD CONSTRAINT uq_capability_tags_0 UNIQUE (name)")
    conn.execute("ALTER TABLE partners DROP COLUMN sub_capabilities")
    conn.execute(
        "INSERT INTO capability_tag_categories (id, name, code, description, enabled, sort_order, is_preset, created_at, updated_at) "
        "VALUES (?, ?, 'legacy_infra', '旧预设分类', 1, 99, 1, ?, ?)",
        ("cat-legacy-unused", unused_preset_cat, now, now),
    )
    conn.execute("UPDATE app_metadata SET value='25' WHERE key='schema_version'")


def test_fresh_schema_seeds_huawei_two_tier_catalog_and_partial_uniques(client):
    with get_db() as conn:
        assert conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] == "26"
        cats = conn.execute("SELECT name FROM capability_tag_categories ORDER BY sort_order").fetchall()
        assert [c["name"] for c in cats] == ["产品技术能力", "场景化能力"]

        l1_rows = conn.execute("SELECT id, name, category FROM capability_tags WHERE level = 1").fetchall()
        l2_rows = conn.execute("SELECT id, name, category, parent_id FROM capability_tags WHERE level = 2").fetchall()
        assert len(l1_rows) == 25
        assert len(l2_rows) == 88

        # Duplicate L2 names across 盘古大模型 and TZ行业大模型 coexist cleanly.
        pangu_id = conn.execute("SELECT id FROM capability_tags WHERE level=1 AND name='盘古大模型'").fetchone()["id"]
        tz_id = conn.execute("SELECT id FROM capability_tags WHERE level=1 AND name='TZ行业大模型'").fetchone()["id"]
        for shared_l2 in ("调研与规划设计", "数据工程", "模型预训练/微调", "应用工程", "模型实施与运维"):
            assert conn.execute(
                "SELECT id FROM capability_tags WHERE level=2 AND parent_id=? AND name=?", (pangu_id, shared_l2)
            ).fetchone()
            assert conn.execute(
                "SELECT id FROM capability_tags WHERE level=2 AND parent_id=? AND name=?", (tz_id, shared_l2)
            ).fetchone()

        # L1 and L2 can share a name (上云规划实施 under 上云规划实施).
        cloud_l1 = conn.execute("SELECT id FROM capability_tags WHERE level=1 AND name='上云规划实施'").fetchone()["id"]
        assert conn.execute(
            "SELECT id FROM capability_tags WHERE level=2 AND parent_id=? AND name='上云规划实施'", (cloud_l1,)
        ).fetchone()

    # Duplicate L1 name violates partial unique index.
    with pytest.raises(IntegrityError):
        with get_db() as conn:
            conn.execute(
                "INSERT INTO capability_tags (id, name, category, level, parent_id, enabled, sort_order, is_preset, created_at, updated_at) "
                "VALUES ('dup-l1', '大数据', '产品技术能力', 1, NULL, 1, 99, 0, '2026-01-01', '2026-01-01')"
            )

    # Duplicate L2 name under the same L1 violates partial unique index.
    with pytest.raises(IntegrityError):
        with get_db() as conn:
            conn.execute(
                "INSERT INTO capability_tags (id, name, category, level, parent_id, enabled, sort_order, is_preset, created_at, updated_at) "
                "VALUES ('dup-l2', '模型预训练/微调', '产品技术能力', 2, ?, 1, 99, 0, '2026-01-01', '2026-01-01')",
                (pangu_id,),
            )


def test_schema25_to_26_migration_separates_l2_preserves_fks_and_rolls_back(client):
    now = datetime.now(timezone.utc).isoformat()
    fk_admin = make_user("fk-admin", role="admin")
    make_partner("p-mix", "翼海云峰测试")
    make_partner("p-pangu", "中软盘古测试")
    with get_db() as conn:
        db_l1_id = conn.execute("SELECT id FROM capability_tags WHERE level=1 AND name='数据库'").fetchone()["id"]
        conn.execute(
            "INSERT INTO enablement_resources (id, draft_json, revision, status, system_visible, model_allowed, partner_allowed, authorization_epoch, created_by, created_at, updated_at) "
            "VALUES ('res-1', '{}', 1, 'published', 1, 1, 1, 1, ?, ?, ?)",
            (fk_admin["id"], now, now),
        )
        conn.execute(
            "INSERT INTO resource_capability_map (resource_id, capability_tag_id) VALUES ('res-1', ?)",
            (db_l1_id,),
        )
        schema25(conn)
        conn.execute(
            "UPDATE partners SET capabilities='大数据,开发现代化,应用现代化,架构现代化,自定义特殊能力' WHERE id='p-mix'",
        )
        conn.execute(
            "UPDATE partners SET capabilities='盘古大模型,模型预训练/微调,数据工程' WHERE id='p-pangu'",
        )
        before = snapshot(conn)

    # 1. Rollback on exception leaves schema 25 untouched.
    with pytest.raises(RuntimeError, match="synthetic abort"):
        with get_db() as conn:
            migrate(conn)
            raise RuntimeError("synthetic abort")
    with get_db() as conn:
        assert snapshot(conn) == before
        assert "level" not in {c["name"] for c in inspect(conn.connection).get_columns("capability_tags")}
        assert "sub_capabilities" not in {c["name"] for c in inspect(conn.connection).get_columns("partners")}

    # 2. Startup verify_schema rejects schema 25 and incomplete schema 26 without writes.
    with pytest.raises(RuntimeError, match="version is not 26"):
        verify_schema(os.environ["DATABASE_URL"])
    with get_db() as conn:
        assert snapshot(conn) == before
        conn.execute("UPDATE app_metadata SET value='26' WHERE key='schema_version'")
    with pytest.raises(RuntimeError, match="explicit schema-26 migration"):
        verify_schema(os.environ["DATABASE_URL"])
    with get_db() as conn:
        conn.execute("UPDATE app_metadata SET value='25' WHERE key='schema_version'")
        assert snapshot(conn) == before

    # 3. Wrong schema versions refuse migration without writes.
    for wrong in ("24", "27"):
        with get_db() as conn:
            conn.execute("UPDATE app_metadata SET value=? WHERE key='schema_version'", (wrong,))
            wrong_before = snapshot(conn)
        with pytest.raises(RuntimeError, match="requires schema 25"):
            with get_db() as conn:
                migrate(conn)
        with get_db() as conn:
            assert snapshot(conn) == wrong_before
    with get_db() as conn:
        conn.execute("UPDATE app_metadata SET value='25' WHERE key='schema_version'")

    # 4. Run actual migration and verify L1 UUID preservation, FK, cleanup, L2 split, and alias.
    with get_db() as conn:
        res = migrate(conn)
        assert res["schema_version"] == 26
        assert res["categories_count"] == 2
        assert res["l1_count"] == 25
        assert res["l2_count"] == 88
        assert res["legacy_aliases_applied"] == 1
        assert conn.execute("SELECT id FROM capability_tags WHERE level=1 AND name='数据库'").fetchone()["id"] == db_l1_id
        assert conn.execute("SELECT capability_tag_id FROM resource_capability_map WHERE resource_id='res-1'").fetchone()["capability_tag_id"] == db_l1_id
        assert conn.execute("SELECT id FROM capability_tag_categories WHERE id='cat-legacy-unused'").fetchone() is None

        mix_row = conn.execute("SELECT capabilities, sub_capabilities FROM partners WHERE id='p-mix'").fetchone()
        assert mix_row["capabilities"] == "大数据,应用现代化,自定义特殊能力"
        assert json.loads(mix_row["sub_capabilities"]) == [{"parent": "应用现代化", "name": "开发现代化"}]

        pangu_row = conn.execute("SELECT capabilities, sub_capabilities FROM partners WHERE id='p-pangu'").fetchone()
        assert pangu_row["capabilities"] == "盘古大模型"
        assert json.loads(pangu_row["sub_capabilities"]) == [
            {"parent": "盘古大模型", "name": "模型预训练/微调"},
            {"parent": "盘古大模型", "name": "数据工程"},
        ]

        saved = snapshot(conn)
        assert migrate(conn) == {"schema_version": 26, "already_current": True}
        assert snapshot(conn) == saved

    verify_schema(os.environ["DATABASE_URL"])


def test_schema25_ambiguous_l2_raises_without_guessing(client):
    make_partner("p-ambig", "歧义测试伙伴")
    with get_db() as conn:
        schema25(conn)
        # Partner has shared L2 '数据工程' with NO parent L1 ('盘古大模型' or 'TZ行业大模型').
        conn.execute("UPDATE partners SET capabilities='大数据,数据工程' WHERE id='p-ambig'")
    with pytest.raises(RuntimeError, match="Ambiguous Level-2 capability '数据工程'"):
        with get_db() as conn:
            migrate(conn)


def test_cli_migration_requires_verified_backup_and_preserves_counts(client, tmp_path):
    make_partner("cli-p1", "CLI伙伴")
    with get_db() as conn:
        schema25(conn)
        conn.execute("UPDATE partners SET capabilities='大数据,架构现代化,开发现代化' WHERE id='cli-p1'")
        before = snapshot(conn)

    url = make_url(os.environ["DATABASE_URL"])
    backup = tmp_path / "cap-backup"
    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[2] / "scripts/migrate_capability_hierarchy.py"),
            "--database-name",
            url.database,
            "--backup-dir",
            str(backup),
        ],
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["schema_version"] == 26 and payload["business_row_counts_unchanged"] is True
    assert (backup / "before.pgdump").stat().st_size > 0
    verify_schema(os.environ["DATABASE_URL"])
    with get_db() as conn:
        assert conn.execute("SELECT capabilities FROM partners WHERE id='cli-p1'").fetchone()[0] == "大数据,应用现代化"
        assert conn.execute("SELECT count(*) FROM partners").fetchone()[0] == before["partners"]["count"]


def test_admin_capability_tree_crud_sync_permissions_and_suggestion_adopt(client):
    admin = auth_headers(make_user("cap-admin", role="admin"))
    reader = auth_headers(make_user("cap-user", role="user"))

    # Permissions
    assert client.get("/partners/capability-tree", headers=reader).status_code == 200
    for method, url, body in [
        ("GET", "/admin/capability-tags/tree", None),
        ("GET", "/admin/capability-tags", None),
        ("POST", "/admin/capability-tags", {"name": "非法", "category": "产品技术能力"}),
    ]:
        assert client.request(method, url, headers=reader, json=body).status_code == 403

    tree = client.get("/admin/capability-tags/tree", headers=admin).json()
    assert [c["name"] for c in tree] == ["产品技术能力", "场景化能力"]

    # Create L1 under 场景化能力 and L2s under it
    l1_resp = client.post(
        "/admin/capability-tags",
        headers=admin,
        json={"name": "新一级能力", "category": "场景化能力", "level": 1},
    )
    assert l1_resp.status_code == 201
    l1_id = l1_resp.json()["id"]

    l2_resp = client.post(
        "/admin/capability-tags",
        headers=admin,
        json={"name": "新二级能力A", "level": 2, "parentId": l1_id},
    )
    assert l2_resp.status_code == 201 and l2_resp.json()["category"] == "场景化能力"
    l2_id = l2_resp.json()["id"]

    # Duplicate L2 under same L1 returns 409; same name under another L1 succeeds
    assert client.post(
        "/admin/capability-tags",
        headers=admin,
        json={"name": "新二级能力A", "level": 2, "parentId": l1_id},
    ).status_code == 409
    other_l1 = next(t for t in tree[0]["tags"] if t["name"] == "大数据")
    assert client.post(
        "/admin/capability-tags",
        headers=admin,
        json={"name": "新二级能力A", "level": 2, "parentId": other_l1["id"]},
    ).status_code == 201

    # Assign partner with L2 -> auto-ensures parent L1
    p_resp = client.post(
        "/partners",
        headers=admin,
        json={"name": "同步测试伙伴", "capabilities": "大数据", "sub_capabilities": [{"parent": "新一级能力", "name": "新二级能力A"}]},
    )
    assert p_resp.status_code == 201
    pid = p_resp.json()["id"]
    assert set(p_resp.json()["capabilities"].split(",")) == {"大数据", "新一级能力"}

    # Rename L1 syncs partner capabilities & sub_capabilities
    assert client.put(f"/admin/capability-tags/{l1_id}", headers=admin, json={"name": "改名后一级"}).status_code == 200
    partner_after_l1_rename = client.get(f"/partners/{pid}", headers=admin).json()
    assert "改名后一级" in partner_after_l1_rename["capabilities"].split(",")
    assert partner_after_l1_rename["sub_capabilities"] == [{"parent": "改名后一级", "name": "新二级能力A"}]

    # Disable L2 hides it from /partners/capability-tree
    assert client.patch(f"/admin/capability-tags/{l2_id}/enable", headers=admin, json={"enabled": False}).status_code == 200
    public_tree = client.get("/partners/capability-tree", headers=reader).json()
    renamed_l1 = next(t for c in public_tree for t in c["tags"] if t["id"] == l1_id)
    assert all(child["id"] != l2_id for child in renamed_l1["children"])

    # Move L2 under 容器 -> updates category & partner sub_capabilities + parent L1
    container_l1 = next(t for t in tree[1]["tags"] if t["name"] == "容器")
    move_resp = client.put(
        f"/admin/capability-tags/{l2_id}",
        headers=admin,
        json={"name": "迁入二级能力", "parentId": container_l1["id"]},
    )
    assert move_resp.status_code == 200 and move_resp.json()["parentName"] == "容器"
    partner_after_move = client.get(f"/partners/{pid}", headers=admin).json()
    assert "容器" in partner_after_move["capabilities"].split(",")
    assert partner_after_move["sub_capabilities"] == [{"parent": "容器", "name": "迁入二级能力"}]

    # Adopt suggestion as L2 and as L1
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO capability_tag_suggestions (id, suggested_name, suggested_category_name, description, confidence, occurrence_count, status, created_at, updated_at) "
            "VALUES ('sug-l2', '建议二级', '场景化能力', 'desc', 0.9, 2, 'pending', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO capability_tag_suggestions (id, suggested_name, suggested_category_name, description, confidence, occurrence_count, status, created_at, updated_at) "
            "VALUES ('sug-l1', '建议一级', '产品技术能力', 'desc', 0.8, 1, 'pending', ?, ?)",
            (now, now),
        )
    adopt_l2 = client.post(
        "/admin/capability-tags/suggestions/sug-l2/adopt",
        headers=admin,
        json={"name": "建议二级", "level": 2, "parentId": container_l1["id"]},
    )
    assert adopt_l2.status_code == 200 and adopt_l2.json()["level"] == 2 and adopt_l2.json()["parentId"] == container_l1["id"]
    adopt_l1 = client.post(
        "/admin/capability-tags/suggestions/sug-l1/adopt",
        headers=admin,
        json={"name": "建议一级", "level": 1, "categoryId": "产品技术能力"},
    )
    assert adopt_l1.status_code == 200 and adopt_l1.json()["level"] == 1 and adopt_l1.json()["category"] == "产品技术能力"


def test_partner_crud_and_excel_roundtrip_with_sub_capabilities_and_legacy_template(client):
    admin = auth_headers(make_user("excel-sub-admin", role="admin"))

    # Reject unknown L2 (422)
    bad = client.post(
        "/partners",
        headers=admin,
        json={"name": "非法二级伙伴", "sub_capabilities": [{"parent": "盘古大模型", "name": "不存在二级"}]},
    )
    assert bad.status_code == 422

    # Create valid partner with shared/slash L2 name under 盘古大模型
    created = client.post(
        "/partners",
        headers=admin,
        json={
            "name": "Excel二层测试伙伴",
            "capabilities": "大数据",
            "sub_capabilities": [{"parent": "盘古大模型", "name": "模型预训练/微调"}],
        },
    )
    assert created.status_code == 201
    assert set(created.json()["capabilities"].split(",")) == {"大数据", "盘古大模型"}
    assert created.json()["sub_capabilities"] == [{"parent": "盘古大模型", "name": "模型预训练/微调"}]

    # Export and verify reference sheet + roundtrip + create another row via Excel
    exported = client.get("/partners/export", headers=admin)
    assert exported.status_code == 200
    book = load_workbook(BytesIO(exported.content))
    ref_rows = [tuple(r) for r in book["行业区域参考"].iter_rows(min_row=2, values_only=True)]
    assert ("一级能力标签", "TZ行业大模型") in ref_rows
    assert ("二级能力标签", "盘古大模型/模型预训练/微调") in ref_rows
    assert upload(client, admin, book).json() == {"created": 0, "updated": 0, "unchanged": 1}

    # Add a new partner row importing slash L2 name under TZ行业大模型 without explicit L1
    sheet = book["伙伴信息"]
    cols = list(partner_transfer.COLUMNS)
    row_vals = [None] * len(cols)
    row_vals[cols.index("name")] = "导入TZ伙伴"
    row_vals[cols.index("sub_capabilities")] = "TZ行业大模型/模型预训练/微调"
    sheet.append(row_vals)
    assert upload(client, admin, book).json()["created"] == 1

    # Backward-compatible old template (no 二级能力标签 column) preserves existing sub_capabilities
    old_book = load_workbook(BytesIO(exported.content))
    sub_col_idx = cols.index("sub_capabilities") + 1
    old_book["伙伴信息"].delete_cols(sub_col_idx, 1)
    intro_idx = cols.index("intro") + 1
    old_book["伙伴信息"].cell(2, intro_idx).value = "旧模板更新简介"
    assert upload(client, admin, old_book).json() == {"created": 0, "updated": 1, "unchanged": 0}
    partners = {p["name"]: p for p in client.get("/partners", headers=admin).json()}
    assert partners["Excel二层测试伙伴"]["sub_capabilities"] == [{"parent": "盘古大模型", "name": "模型预训练/微调"}]
    assert partners["导入TZ伙伴"]["capabilities"] == "TZ行业大模型"
    assert partners["导入TZ伙伴"]["sub_capabilities"] == [{"parent": "TZ行业大模型", "name": "模型预训练/微调"}]


def test_matching_recalls_l2_populates_certification_snapshot_and_demand_aggregates(client, monkeypatch):
    admin = auth_headers(make_user("match-l2-admin", role="admin"))
    owner = make_user("match-l2-owner")

    p_resp = client.post(
        "/partners",
        headers=admin,
        json={
            "name": "安全专项测试伙伴",
            "capabilities": "安全",
            "sub_capabilities": [{"parent": "安全", "name": "上云安全-规划实施"}],
        },
    )
    assert p_resp.status_code == 201
    pid = p_resp.json()["id"]

    # Recall via L2 keyword even though prompt says nothing else about partner
    requirement = "需要上云安全-规划实施落地部署"
    l1_names = [item["name"] for item in CATALOG["tags"]]
    understood, _ = matching.parse_understanding(
        json.dumps(
            {
                "in_scope": True,
                "facts": {
                    "capabilityTags": ["安全"],
                    "capabilityEvidence": {"安全": "上云安全-规划实施"},
                    "workEvidence": ["上云安全-规划实施"],
                    "partnerRequirements": [],
                },
            },
            ensure_ascii=False,
        ),
        requirement,
        l1_names,
    )
    with get_db() as conn:
        selected = match_context.recall_candidates(conn, requirement, understood["facts"])
        assert [c["partnerId"] for c in selected] == [pid]
        cert = selected[0]["certification"]
        assert cert["capabilityTags"] == ["安全"]
        assert cert["relatedCapabilityTags"] == ["安全"]
        assert cert["subCapabilityTags"] == [{"parent": "安全", "name": "上云安全-规划实施"}]
        assert cert["relatedSubCapabilityTags"] == []
        row = match_context.detailed_candidate(conn, pid, "安全", requirement, facts=understood["facts"], hits=selected[0]["hits"])
        rec_stub = {
            **recommendation(pid, "安全专项测试伙伴"),
            "profileEvidence": [],
            "evidenceCases": [],
            "evidenceDeliverables": [],
        }
        assert match._current_reference_valid(conn, rec_stub, row) is True
        # Changing sub_capabilities invalidates snapshot dependency check.
        conn.execute("UPDATE partners SET sub_capabilities=NULL WHERE id=?", (pid,))
        assert match._current_reference_valid(conn, rec_stub, row) is False

    # Demand report counts L1 cleanly (partner with 2 L2 children under 应用现代化 counts once)
    p2_resp = client.post(
        "/partners",
        headers=admin,
        json={
            "name": "应用现代化测试伙伴",
            "capabilities": "应用现代化",
            "sub_capabilities": [
                {"parent": "应用现代化", "name": "开发现代化"},
                {"parent": "应用现代化", "name": "微服务治理"},
            ],
        },
    )
    assert p2_resp.status_code == 201
    now = datetime.now(timezone.utc).isoformat()
    task_id = make_task(owner, "应用现代化需求", recommendations=[recommendation(p2_resp.json()["id"], "应用现代化测试伙伴")])
    with get_db() as conn:
        conn.execute(
            "INSERT INTO demand_profiles (id, match_record_id, requirement_text, industry_tags, region_tags, capability_tags, matched_partner_count, supply_status, created_at) "
            "VALUES ('dp-l2', ?, '应用现代化', '金融', '广东', '应用现代化', 1, 'partial', ?)",
            (task_id, now),
        )
    report = client.get("/admin/reports", headers=admin).json()
    top_tags = {item["label"]: item["count"] for item in report["topFormalTags"]}
    assert top_tags["应用现代化"] == 1
    assert "开发现代化" not in top_tags
    filtered_report = client.get("/admin/reports?capability=应用现代化", headers=admin).json()
    assert filtered_report["overview"]["totalDemands"] == 1


def _l1_and_hierarchy():
    with get_db() as conn:
        return l1_l2_hierarchy_map(conn)


def _seed_partner(pid, name, caps, subs=None, identities=None):
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO partners (id, name, capabilities, sub_capabilities, identities, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
            (
                pid,
                name,
                caps,
                json.dumps(subs, ensure_ascii=False) if subs is not None else None,
                json.dumps(identities, ensure_ascii=False) if identities is not None else None,
                now,
                now,
            ),
        )


def test_l2_certification_persists_through_task_detail_owner_only_and_supports_legacy_tasks(client, monkeypatch):
    admin = auth_headers(make_user("p11-admin", role="admin"))
    owner = make_user("p11-owner")
    other = make_user("p11-other")

    p_resp = client.post(
        "/partners",
        headers=admin,
        json={
            "name": "持久化二级测试伙伴",
            "capabilities": "盘古大模型",
            "sub_capabilities": [
                {"parent": "盘古大模型", "name": "数据工程"},
                {"parent": "盘古大模型", "name": "应用工程"},
            ],
        },
    )
    assert p_resp.status_code == 201
    pid = p_resp.json()["id"]

    requirement = "必须持有盘古大模型下的数据工程认证，交付金融行业知识库项目。"
    l1_names, hierarchy = _l1_and_hierarchy()
    understood, rejected = matching.parse_understanding(
        json.dumps(
            {
                "in_scope": True,
                "facts": {
                    "capabilityTags": ["盘古大模型"],
                    "capabilityEvidence": {"盘古大模型": "盘古大模型下的数据工程认证"},
                    "subCapabilityTags": [{"parent": "盘古大模型", "name": "数据工程"}],
                    "subCapabilityEvidence": {"盘古大模型/数据工程": "盘古大模型下的数据工程认证"},
                    "workEvidence": ["交付金融行业知识库项目"],
                    "partnerRequirements": [
                        {
                            "mode": "required",
                            "match": "all",
                            "capabilityTags": [],
                            "subCapabilityTags": [{"parent": "盘古大模型", "name": "数据工程"}],
                            "identities": [],
                            "evidenceText": "必须持有盘古大模型下的数据工程认证",
                        }
                    ],
                },
            },
            ensure_ascii=False,
        ),
        requirement,
        l1_names,
        hierarchy=hierarchy,
    )
    assert rejected == []

    def complete(config, messages, schema):
        if schema["title"] == "MatchUnderstanding":
            return json.dumps({"in_scope": True, "facts": understood["facts"]}, ensure_ascii=False)
        data = json.loads(messages[-1]["content"])
        assert len(data["candidates"]) == 1
        return json.dumps(
            {
                "recommendations": [
                    {
                        **recommendation(pid, "持久化二级测试伙伴"),
                        "matchedCapabilities": "盘古大模型, 数据工程",
                        "recommendationReason": "持有盘古大模型数据工程正式认证，满足需求条件。",
                        "evidenceCases": [],
                        "evidenceDeliverables": [],
                        "profileEvidence": [],
                    }
                ],
                "analysisRefs": [],
                "gapAnalysis": "该伙伴具备盘古大模型数据工程正式能力认证。",
                "supplyStatus": "partial",
            },
            ensure_ascii=False,
        )

    with get_db() as conn:
        conn.execute("UPDATE model_providers SET api_key_source='db', api_key='synthetic-only'")
    monkeypatch.setattr(development_model, "completion", complete)

    accepted = match.create_task(match.TaskCreateRequest(requestId=uuid4(), requirement=requirement), owner)
    match.executor.shutdown(wait=True)

    with get_db() as conn:
        row = dict(conn.execute("SELECT * FROM match_records WHERE id=?", (accepted.recordId,)).fetchone())
        assert row["task_status"] == "ready"
        saved_recs = json.loads(row["recommendations_json"])
        saved_cert = saved_recs[0]["certification"]
        assert saved_cert["subCapabilityTags"] == [
            {"parent": "盘古大模型", "name": "数据工程"},
            {"parent": "盘古大模型", "name": "应用工程"},
        ]
        # Exact L2 target must NOT spuriously include unrelated sibling L2s (应用工程).
        assert saved_cert["relatedSubCapabilityTags"] == [{"parent": "盘古大模型", "name": "数据工程"}]

    # Owner gets full subCapabilityTags / relatedSubCapabilityTags; other user gets 404.
    owner_detail = client.get(f"/agent/tasks/{accepted.recordId}", headers=auth_headers(owner))
    assert owner_detail.status_code == 200
    api_cert = owner_detail.json()["recommendations"][0]["certification"]
    assert api_cert["subCapabilityTags"] == [
        {"parent": "盘古大模型", "name": "数据工程"},
        {"parent": "盘古大模型", "name": "应用工程"},
    ]
    assert api_cert["relatedSubCapabilityTags"] == [{"parent": "盘古大模型", "name": "数据工程"}]
    assert client.get(f"/agent/tasks/{accepted.recordId}", headers=auth_headers(other)).status_code == 404

    # Legacy task JSON lacking subCapabilityTags/relatedSubCapabilityTags still returns cleanly.
    legacy_rec = {
        **recommendation(pid, "旧版快照伙伴"),
        "certification": {
            "capabilityTags": ["数据库"],
            "relatedCapabilityTags": ["数据库"],
            "servicePartnerBasis": "capability_tag",
            "identities": [],
        },
    }
    legacy_task_id = make_task(owner, "旧版推荐快照", recommendations=[legacy_rec])
    legacy_resp = client.get(f"/agent/tasks/{legacy_task_id}", headers=auth_headers(owner))
    assert legacy_resp.status_code == 200
    assert legacy_resp.json()["recommendations"][0]["certification"]["subCapabilityTags"] == []
    assert legacy_resp.json()["recommendations"][0]["certification"]["relatedSubCapabilityTags"] == []


def test_explicit_l2_required_preferred_excluded_conditions_and_overflow_tiers():
    l1_names, hierarchy = _l1_and_hierarchy()

    # Duplicate L2 names across 盘古大模型 & TZ行业大模型, plus L1=L2 (上云规划实施) + 14 overflow candidates.
    _seed_partner(
        "p-tz-pref",
        "TZ双持优先伙伴",
        "盘古大模型,TZ行业大模型,上云规划实施",
        [
            {"parent": "TZ行业大模型", "name": "数据工程"},
            {"parent": "上云规划实施", "name": "上云规划实施"},
        ],
    )
    _seed_partner(
        "p-tz-only",
        "仅TZ伙伴",
        "TZ行业大模型",
        [{"parent": "TZ行业大模型", "name": "数据工程"}],
    )
    _seed_partner(
        "p-pangu-only",
        "仅盘古伙伴",
        "盘古大模型",
        [{"parent": "盘古大模型", "name": "数据工程"}],
    )
    _seed_partner(
        "p-both-excluded",
        "同时持有需排除L2伙伴",
        "TZ行业大模型,盘古大模型",
        [
            {"parent": "TZ行业大模型", "name": "数据工程"},
            {"parent": "盘古大模型", "name": "数据工程"},
        ],
    )
    _seed_partner("p-l1-cloud-only", "仅上云一级伙伴", "上云规划实施", [])
    for idx in range(14):
        _seed_partner(
            f"p-tz-overflow-{idx:02d}",
            f"TZ扩容伙伴-{idx:02d}",
            "TZ行业大模型",
            [{"parent": "TZ行业大模型", "name": "数据工程"}],
        )

    # Reject bad/mis-parented L2 in partnerRequirements.
    from backend.business.development import InvalidOutput

    with pytest.raises(InvalidOutput):
        matching.parse_understanding(
            json.dumps(
                {
                    "in_scope": True,
                    "facts": {
                        "partnerRequirements": [
                            {
                                "mode": "required",
                                "match": "all",
                                "capabilityTags": [],
                                "subCapabilityTags": [{"parent": "容器", "name": "数据工程"}],
                                "identities": [],
                                "evidenceText": "必须TZ数据工程",
                            }
                        ]
                    },
                },
                ensure_ascii=False,
            ),
            "必须TZ数据工程",
            l1_names,
            hierarchy=hierarchy,
        )

    # Test 1: Required TZ行业大模型/数据工程 + Excluded 盘古大模型/数据工程 + Preferred 上云规划实施/上云规划实施
    req1 = "必须具备TZ行业大模型/数据工程认证，排除盘古大模型/数据工程，优先具备上云规划实施/上云规划实施二级认证。"
    u1, _ = matching.parse_understanding(
        json.dumps(
            {
                "in_scope": True,
                "facts": {
                    "capabilityTags": [],
                    "workEvidence": [],
                    "partnerRequirements": [
                        {
                            "mode": "required",
                            "match": "all",
                            "capabilityTags": [],
                            "subCapabilityTags": [{"parent": "TZ行业大模型", "name": "数据工程"}],
                            "identities": [],
                            "evidenceText": "必须具备TZ行业大模型/数据工程认证",
                        },
                        {
                            "mode": "excluded",
                            "match": "all",
                            "capabilityTags": [],
                            "subCapabilityTags": [{"parent": "盘古大模型", "name": "数据工程"}],
                            "identities": [],
                            "evidenceText": "排除盘古大模型/数据工程",
                        },
                        {
                            "mode": "preferred",
                            "match": "all",
                            "capabilityTags": [],
                            "subCapabilityTags": [{"parent": "上云规划实施", "name": "上云规划实施"}],
                            "identities": [],
                            "evidenceText": "优先具备上云规划实施/上云规划实施二级认证",
                        },
                    ],
                },
            },
            ensure_ascii=False,
        ),
        req1,
        l1_names,
        hierarchy=hierarchy,
    )
    with get_db() as conn:
        recalled1 = match_context.recall_candidates(conn, req1, u1["facts"], limit=12)
        ids1 = [item["partnerId"] for item in recalled1]
        assert len(ids1) == 12
        assert ids1[0] == "p-tz-pref"
        assert "p-pangu-only" not in ids1
        assert "p-both-excluded" not in ids1
        assert "p-l1-cloud-only" not in ids1
        assert set(item["name"] for item in recalled1[0]["certification"]["relatedSubCapabilityTags"]) == {"数据工程", "上云规划实施"}

    # Test 2: L1=L2 distinction — require L2 上云规划实施/上云规划实施 rejects L1-only p-l1-cloud-only.
    req2 = "必须具备上云规划实施下的上云规划实施二级认证。"
    u2, _ = matching.parse_understanding(
        json.dumps(
            {
                "in_scope": True,
                "facts": {
                    "workEvidence": [],
                    "partnerRequirements": [
                        {
                            "mode": "required",
                            "match": "all",
                            "capabilityTags": [],
                            "subCapabilityTags": [{"parent": "上云规划实施", "name": "上云规划实施"}],
                            "identities": [],
                            "evidenceText": req2,
                        }
                    ],
                },
            },
            ensure_ascii=False,
        ),
        req2,
        l1_names,
        hierarchy=hierarchy,
    )
    with get_db() as conn:
        recalled2 = match_context.recall_candidates(conn, req2, u2["facts"])
        assert [c["partnerId"] for c in recalled2] == ["p-tz-pref"]


def test_disabling_tags_excludes_new_runs_invalidates_saving_and_keeps_historical_snapshots(client):
    admin = auth_headers(make_user("disable-admin", role="admin"))
    owner = make_user("disable-owner")
    _seed_partner(
        "p-disable-l2",
        "安全停用二级伙伴",
        "安全",
        [{"parent": "安全", "name": "上云安全-规划实施"}],
    )
    _seed_partner("p-disable-l1", "专项停用测试乙公司", "容器", [])

    # Historical saved snapshot must remain untouched when tags are later disabled.
    historical_rec = {
        **recommendation("p-disable-l2", "安全停用二级伙伴"),
        "certification": {
            "capabilityTags": ["安全"],
            "relatedCapabilityTags": ["安全"],
            "subCapabilityTags": [{"parent": "安全", "name": "上云安全-规划实施"}],
            "relatedSubCapabilityTags": [{"parent": "安全", "name": "上云安全-规划实施"}],
            "servicePartnerBasis": "capability_tag",
            "identities": [],
        },
    }
    hist_task_id = make_task(owner, "历史停用前任务", recommendations=[historical_rec])

    requirement = "需要上云安全-规划实施以及容器实施"
    l1_names, hierarchy = _l1_and_hierarchy()
    understood, _ = matching.parse_understanding(
        json.dumps(
            {
                "in_scope": True,
                "facts": {
                    "capabilityTags": ["安全", "容器"],
                    "capabilityEvidence": {"安全": "上云安全-规划实施", "容器": "容器实施"},
                    "subCapabilityTags": [{"parent": "安全", "name": "上云安全-规划实施"}],
                    "subCapabilityEvidence": {"安全/上云安全-规划实施": "上云安全-规划实施"},
                    "workEvidence": ["上云安全-规划实施", "容器实施"],
                    "partnerRequirements": [],
                },
            },
            ensure_ascii=False,
        ),
        requirement,
        l1_names,
        hierarchy=hierarchy,
    )

    with get_db() as conn:
        selected = match_context.recall_candidates(conn, requirement, understood["facts"])
        by_pid = {c["partnerId"]: c for c in selected}
        assert set(by_pid) == {"p-disable-l2", "p-disable-l1"}
        row_l2 = match_context.detailed_candidate(conn, "p-disable-l2", "安全", requirement, facts=understood["facts"], hits=by_pid["p-disable-l2"]["hits"])
        row_l1 = match_context.detailed_candidate(conn, "p-disable-l1", "容器", requirement, facts=understood["facts"], hits=by_pid["p-disable-l1"]["hits"])
        stub_l2 = {**recommendation("p-disable-l2", "安全停用二级伙伴"), "profileEvidence": [], "evidenceCases": [], "evidenceDeliverables": []}
        stub_l1 = {**recommendation("p-disable-l1", "专项停用测试乙公司"), "profileEvidence": [], "evidenceCases": [], "evidenceDeliverables": []}
        assert match._current_reference_valid(conn, stub_l2, row_l2) is True
        assert match._current_reference_valid(conn, stub_l1, row_l1) is True
        stamp_before = match._candidate_stamp(conn)

        l2_id = conn.execute(
            "SELECT c.id FROM capability_tags c JOIN capability_tags p ON p.id=c.parent_id WHERE c.level=2 AND p.name='安全' AND c.name='上云安全-规划实施'"
        ).fetchone()["id"]
        l1_container_id = conn.execute("SELECT id FROM capability_tags WHERE level=1 AND name='容器'").fetchone()["id"]

    # Disable L2 and L1 mid-review via admin API.
    assert client.patch(f"/admin/capability-tags/{l2_id}/enable", headers=admin, json={"enabled": False}).status_code == 200
    assert client.patch(f"/admin/capability-tags/{l1_container_id}/enable", headers=admin, json={"enabled": False}).status_code == 200

    with get_db() as conn:
        assert match._candidate_stamp(conn) != stamp_before
        assert match._current_reference_valid(conn, stub_l2, row_l2) is False
        assert match._current_reference_valid(conn, stub_l1, row_l1) is False

        # New run excludes disabled L1/L2 from certification snapshot and corpus.
        new_selected = match_context.recall_candidates(conn, requirement, understood["facts"])
        assert all(c["partnerId"] != "p-disable-l1" for c in new_selected)
        l2_cand = next(c for c in new_selected if c["partnerId"] == "p-disable-l2")
        assert l2_cand["certification"]["subCapabilityTags"] == []
        assert l2_cand["certification"]["relatedSubCapabilityTags"] == []

    # Historical saved snapshot remains readable verbatim.
    hist_resp = client.get(f"/agent/tasks/{hist_task_id}", headers=auth_headers(owner))
    assert hist_resp.status_code == 200
    assert hist_resp.json()["recommendations"][0]["certification"]["relatedSubCapabilityTags"] == [
        {"parent": "安全", "name": "上云安全-规划实施"}
    ]


def test_l1_assignment_validation_name_rules_and_excel_parent_consistency(client):
    admin = auth_headers(make_user("rules-admin", role="admin"))

    # 1. Invalid tag names rejected cleanly with 422 while L2 with '/' allowed.
    for bad_payload in [
        {"name": "一级/带斜杠", "category": "产品技术能力", "level": 1},
        {"name": "一级,带逗号", "category": "产品技术能力", "level": 1},
        {"name": "一级\n换行", "category": "产品技术能力", "level": 1},
    ]:
        assert client.post("/admin/capability-tags", headers=admin, json=bad_payload).status_code == 422
    with get_db() as conn:
        pangu_id = conn.execute("SELECT id FROM capability_tags WHERE level=1 AND name='盘古大模型'").fetchone()["id"]
    assert client.post("/admin/capability-tags", headers=admin, json={"name": "二级、顿号", "level": 2, "parentId": pangu_id}).status_code == 422
    assert client.post("/admin/capability-tags", headers=admin, json={"name": "专项/合法二级", "level": 2, "parentId": pangu_id}).status_code == 201

    # 2. Partner assignment rejects new unknown/disabled L1, preserves legacy/disabled L1 on unrelated update,
    #    and preserves parent L1 on partial PUT & legacy Excel without sub_capabilities column.
    assert client.post("/partners", headers=admin, json={"name": "未知一级", "capabilities": "不存在一级"}).status_code == 422
    with get_db() as conn:
        sap_id = conn.execute("SELECT id FROM capability_tags WHERE level=1 AND name='SAP'").fetchone()["id"]
    assert client.patch(f"/admin/capability-tags/{sap_id}/enable", headers=admin, json={"enabled": False}).status_code == 200
    assert client.post("/partners", headers=admin, json={"name": "停用一级", "capabilities": "SAP"}).status_code == 422

    # Legacy partner with pre-existing disabled SAP + custom '历史自留' and existing L2 盘古大模型/数据工程
    _seed_partner(
        "p-legacy-kept",
        "历史保留伙伴",
        "SAP,历史自留,盘古大模型",
        [{"parent": "盘古大模型", "name": "数据工程"}],
    )
    # Updating capabilities to keep existing 'SAP,历史自留' (dropping '盘古大模型') automatically re-attaches 盘古大模型.
    upd = client.put("/partners/p-legacy-kept", headers=admin, json={"capabilities": "SAP,历史自留,大数据"})
    assert upd.status_code == 200
    assert set(upd.json()["capabilities"].split(",")) == {"SAP", "历史自留", "大数据", "盘古大模型"}
    assert upd.json()["sub_capabilities"] == [{"parent": "盘古大模型", "name": "数据工程"}]

    # Old Excel template without sub_capabilities column cannot leave orphan L2 without parent L1,
    # while new Excel export/import roundtrips existing disabled L1/L2 and clears L2 when cell is emptied.
    exported = client.get("/partners/export", headers=admin)
    assert exported.status_code == 200
    cols = list(partner_transfer.COLUMNS)

    old_book = load_workbook(BytesIO(exported.content))
    cap_col = cols.index("capabilities") + 1
    sub_col = cols.index("sub_capabilities") + 1
    old_book["伙伴信息"].cell(2, cap_col).value = "大数据"
    old_book["伙伴信息"].delete_cols(sub_col, 1)
    assert upload(client, admin, old_book).json()["updated"] == 1
    after_old = client.get("/partners/p-legacy-kept", headers=admin).json()
    assert set(after_old["capabilities"].split(",")) == {"大数据", "盘古大模型"}
    assert after_old["sub_capabilities"] == [{"parent": "盘古大模型", "name": "数据工程"}]

    # Re-export, clear sub_capabilities in new template -> clears sub_capabilities cleanly.
    exported2 = client.get("/partners/export", headers=admin)
    new_book = load_workbook(BytesIO(exported2.content))
    new_book["伙伴信息"].cell(2, sub_col).value = None
    new_book["伙伴信息"].cell(2, cap_col).value = "大数据"
    assert upload(client, admin, new_book).json()["updated"] == 1
    after_clear = client.get("/partners/p-legacy-kept", headers=admin).json()
    assert after_clear["capabilities"] == "大数据" and after_clear["sub_capabilities"] == []


def test_demand_report_normalizes_legacy_alias_without_rewriting_history(client):
    admin = auth_headers(make_user("alias-report-admin", role="admin"))
    owner = make_user("alias-report-owner")
    _seed_partner("p-mod", "现代供给伙伴", "应用现代化", [{"parent": "应用现代化", "name": "开发现代化"}])
    now = datetime.now(timezone.utc).isoformat()
    t1 = make_task(owner, "历史架构现代化需求", recommendations=[])
    t2 = make_task(owner, "混合别名需求", recommendations=[])
    with get_db() as conn:
        conn.execute(
            "INSERT INTO demand_profiles (id, match_record_id, requirement_text, industry_tags, region_tags, capability_tags, matched_partner_count, supply_status, created_at) "
            "VALUES ('dp-arch-only', ?, '架构现代化需求', '金融', '广东', '架构现代化', 0, 'gap', ?)",
            (t1, now),
        )
        conn.execute(
            "INSERT INTO demand_profiles (id, match_record_id, requirement_text, industry_tags, region_tags, capability_tags, matched_partner_count, supply_status, created_at) "
            "VALUES ('dp-arch-mixed', ?, '混合需求', '金融', '广东', '架构现代化, 应用现代化', 0, 'gap', ?)",
            (t2, now),
        )

    for query in ("/admin/reports", "/admin/reports?capability=应用现代化", "/admin/reports?capability=架构现代化"):
        report = client.get(query, headers=admin).json()
        gaps = {item["capability"]: item for item in report["supplyGaps"]}
        assert "架构现代化" not in gaps
        assert gaps["应用现代化"]["demandCount"] == 2
        assert gaps["应用现代化"]["partnerCount"] == 1
        assert gaps["应用现代化"]["supplyStatus"] == "partial"

    profiles = client.get("/admin/demand-profiles", headers=admin).json()
    assert profiles["capabilityDistribution"] == {"应用现代化": 2}
    with get_db() as conn:
        stored = {r["id"]: r["capability_tags"] for r in conn.execute("SELECT id, capability_tags FROM demand_profiles")}
        assert stored["dp-arch-only"] == "架构现代化"
        assert stored["dp-arch-mixed"] == "架构现代化, 应用现代化"


def test_cli_backup_restore_to_schema25_and_failure_modes(client, tmp_path):
    from scripts import migrate_capability_hierarchy as cli

    admin = make_user("cli-fail-admin", role="admin")
    make_partner("cli-r1", "备份还原伙伴")
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        db_l1_id = conn.execute("SELECT id FROM capability_tags WHERE level=1 AND name='数据库'").fetchone()["id"]
        conn.execute(
            "INSERT INTO enablement_resources (id, draft_json, revision, status, system_visible, model_allowed, partner_allowed, authorization_epoch, created_by, created_at, updated_at) "
            "VALUES ('res-cli', '{}', 1, 'published', 1, 1, 1, 1, ?, ?, ?)",
            (admin["id"], now, now),
        )
        conn.execute(
            "INSERT INTO resource_capability_map (resource_id, capability_tag_id) VALUES ('res-cli', ?)",
            (db_l1_id,),
        )
        schema25(conn)
        conn.execute("UPDATE partners SET capabilities='大数据,开发现代化,架构现代化' WHERE id='cli-r1'")
        before = snapshot(conn)
        current_schema = conn.execute("SELECT current_schema()").fetchone()[0]

    url = make_url(os.environ["DATABASE_URL"])
    cli_path = Path(__file__).resolve().parents[2] / "scripts/migrate_capability_hierarchy.py"

    # 1. Pre-commit verify_schema_connection failure rolls back schema to 25 cleanly.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cli, "verify_schema_connection", lambda *a: (_ for _ in ()).throw(RuntimeError("synthetic pre-commit verify fail")))
        mp.setattr(
            sys,
            "argv",
            ["migrate_capability_hierarchy", "--database-name", url.database, "--backup-dir", str(tmp_path / "verify-fail-backup")],
        )
        with pytest.raises(SystemExit) as excinfo:
            try:
                cli.main()
            except Exception as err:
                print(err, file=sys.stderr)
                sys.exit(1)
        assert excinfo.value.code == 1
    with get_db() as conn:
        assert snapshot(conn) == before
        assert conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] == "25"

    # 2. Backup failure refuses migration without touching DB.
    def fail_dump(args, **kwargs):
        if args[0] == "pg_dump":
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(cli.subprocess, "run", fail_dump)
        mp.setattr(cli, "migrate", lambda *a: pytest.fail("must not migrate when pg_dump fails"))
        mp.setattr(
            sys,
            "argv",
            ["migrate_capability_hierarchy", "--database-name", url.database, "--backup-dir", str(tmp_path / "dump-fail-backup")],
        )
        with pytest.raises(subprocess.CalledProcessError):
            cli.main()
    with get_db() as conn:
        assert snapshot(conn) == before

    # 3. Post-commit report write failure exits with code 2 and distinct post-commit message.
    report_fail_dir = tmp_path / "report-fail-backup"
    orig_write_text = Path.write_text

    def fail_result_json(self, data, *args, **kwargs):
        if self.name == "result.json":
            raise OSError("disk full writing report")
        return orig_write_text(self, data, *args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(Path, "write_text", fail_result_json)
        mp.setattr(
            sys,
            "argv",
            ["migrate_capability_hierarchy", "--database-name", url.database, "--backup-dir", str(report_fail_dir)],
        )
        with pytest.raises(SystemExit) as exc2:
            cli.main()
        assert exc2.value.code == 2
    verify_schema(os.environ["DATABASE_URL"])

    # 4. Restore schema-25 dump into the isolated test schema via pg_restore --schema and verify UUID/FK/version.
    pg_env = dict(
        os.environ,
        PGHOST=url.host,
        PGPORT=str(url.port or 5432),
        PGDATABASE=url.database,
        PGUSER=url.username or "",
        PGPASSWORD=url.password or "",
    )
    dump_file = report_fail_dir / "before.pgdump"
    engine_for(os.environ["DATABASE_URL"]).dispose()
    with engine_for(os.environ["DATABASE_URL"]).begin() as raw:
        raw.exec_driver_sql(f"DROP SCHEMA {current_schema} CASCADE")
        raw.exec_driver_sql(f"CREATE SCHEMA {current_schema}")
    engine_for(os.environ["DATABASE_URL"]).dispose()
    restore = subprocess.run(
        ["pg_restore", "--no-owner", "--no-acl", "--exit-on-error", "--schema", current_schema, "-d", url.database, str(dump_file)],
        env=pg_env,
        capture_output=True,
        text=True,
    )
    assert restore.returncode == 0, restore.stderr
    with get_db() as conn:
        assert conn.execute("SELECT value FROM app_metadata WHERE key='schema_version'").fetchone()[0] == "25"
        assert conn.execute("SELECT id FROM capability_tags WHERE name='数据库'").fetchone()["id"] == db_l1_id
        assert conn.execute("SELECT capability_tag_id FROM resource_capability_map WHERE resource_id='res-cli'").fetchone()["capability_tag_id"] == db_l1_id
    # Re-run CLI cleanly so fresh_database teardown and normal schema-26 exit cleanly.
    ok_backup = tmp_path / "clean-reapply-backup"
    res_cli = subprocess.run(
        [sys.executable, str(cli_path), "--database-name", url.database, "--backup-dir", str(ok_backup)],
        capture_output=True,
        text=True,
        env=dict(os.environ),
    )
    assert res_cli.returncode == 0, res_cli.stderr
    assert json.loads((ok_backup / "result.json").read_text())["schema_version"] == 26


def test_match_disabled_l1_redacted_and_empty_analysis_refs_rechecked(client):
    admin = auth_headers(make_user("b-match-admin", role="admin"))
    _seed_partner(
        "p-b1",
        "停用与空引用专项伙伴",
        "安全,容器",
        [{"parent": "安全", "name": "上云安全-规划实施"}],
    )
    with get_db() as conn:
        l1_container_id = conn.execute("SELECT id FROM capability_tags WHERE level=1 AND name='容器'").fetchone()["id"]
    assert client.patch(f"/admin/capability-tags/{l1_container_id}/enable", headers=admin, json={"enabled": False}).status_code == 200

    l1_names, hierarchy = _l1_and_hierarchy()
    l1_only_facts, _ = matching.parse_understanding(
        json.dumps(
            {
                "in_scope": True,
                "facts": {
                    "capabilityTags": ["安全"],
                    "capabilityEvidence": {"安全": "上云安全建设"},
                    "workEvidence": ["上云安全建设"],
                    "partnerRequirements": [],
                },
            },
            ensure_ascii=False,
        ),
        "需要上云安全建设能力",
        l1_names,
        hierarchy=hierarchy,
    )
    with_l2_facts, _ = matching.parse_understanding(
        json.dumps(
            {
                "in_scope": True,
                "facts": {
                    "capabilityTags": ["安全"],
                    "capabilityEvidence": {"安全": "上云安全-规划实施"},
                    "subCapabilityTags": [{"parent": "安全", "name": "上云安全-规划实施"}],
                    "subCapabilityEvidence": {"安全/上云安全-规划实施": "上云安全-规划实施"},
                    "workEvidence": ["上云安全-规划实施"],
                    "partnerRequirements": [],
                },
            },
            ensure_ascii=False,
        ),
        "需要上云安全-规划实施能力",
        l1_names,
        hierarchy=hierarchy,
    )

    with get_db() as conn:
        # Bug ①a & ④: disabled L1 omitted from detailed_candidate context['capabilities'], and L1-only hits keep relatedSubCapabilityTags=[].
        row_l1_only = match_context.detailed_candidate(conn, "p-b1", "安全", "需要上云安全建设能力", facts=l1_only_facts["facts"])
        assert "容器" not in row_l1_only[1]["capabilities"]
        assert "安全" in row_l1_only[1]["capabilities"]
        assert row_l1_only[1]["certification"]["subCapabilityTags"] == [{"parent": "安全", "name": "上云安全-规划实施"}]
        assert row_l1_only[1]["certification"]["relatedSubCapabilityTags"] == []

        row = match_context.detailed_candidate(conn, "p-b1", "安全", "需要上云安全-规划实施能力", facts=with_l2_facts["facts"])
        assert row[1]["certification"]["relatedSubCapabilityTags"] == [{"parent": "安全", "name": "上云安全-规划实施"}]

        output = {
            "_analysis_shape_valid": True,
            "analysisRefs": [],
            "supplyStatus": "sufficient",
            "gapAnalysis": "既有候选可满足安全需求。",
            "recommendations": [],
        }
        unchanged = match._validated_outcome([], dict(output), [], [row], connection=conn)
        assert unchanged["analysis_adopted"] is True
        assert unchanged["supplyStatus"] == "sufficient"
        assert "既有候选" in unchanged["gapAnalysis"]

        # Bug ①b: empty analysisRefs must still invalidate gapAnalysis/supplyStatus if candidate certification drifted mid-review.
        conn.execute("UPDATE partners SET sub_capabilities='[]' WHERE id='p-b1'")
        drifted = match._validated_outcome([], dict(output), [], [row], connection=conn)
        assert drifted["analysis_adopted"] is False
        assert drifted["supplyStatus"] == "unknown"
        assert drifted["gapAnalysis"] == ""


def test_tag_length_category_lock_and_demand_filter_guards(client):
    admin_user = make_user("b-guard-admin", role="admin")
    admin = auth_headers(admin_user)
    long_name = "超长能力名称" + "X" * 95  # 101 chars (>100 limit)

    # Bug ③: >100-char L1/L2 rejected at tag creation and partner sub_capabilities write, while legacy >100 DB values remain readable.
    assert client.post(
        "/admin/capability-tags",
        headers=admin,
        json={"name": long_name, "category": "场景化能力", "level": 1},
    ).status_code == 422
    with get_db() as conn:
        sec_id = conn.execute("SELECT id FROM capability_tags WHERE level=1 AND name='安全'").fetchone()["id"]
    assert client.post(
        "/admin/capability-tags",
        headers=admin,
        json={"name": long_name, "level": 2, "parentId": sec_id},
    ).status_code == 422
    assert client.post(
        "/partners",
        headers=admin,
        json={"name": "超长能力拦截测试", "capabilities": "安全", "sub_capabilities": [{"parent": "安全", "name": long_name}]},
    ).status_code == 422

    legacy_partner = make_partner("p-long-sub", "历史超长二级读取伙伴")
    with get_db() as conn:
        conn.execute(
            "UPDATE partners SET capabilities='安全', sub_capabilities=? WHERE id=?",
            (json.dumps([{"parent": "安全", "name": long_name}], ensure_ascii=False), legacy_partner["id"]),
        )
    list_resp = client.get("/partners?search=历史超长二级读取伙伴", headers=admin)
    assert list_resp.status_code == 200
    assert list_resp.json()[0]["sub_capabilities"] == [{"parent": "安全", "name": long_name}]
    detail_resp = client.get(f"/partners/{legacy_partner['id']}", headers=admin)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["sub_capabilities"] == [{"parent": "安全", "name": long_name}]

    # Bug ⑤: creating/updating L1 tag validates category exists, and category rename syncs child tags under write lock.
    assert client.post(
        "/admin/capability-tags",
        headers=admin,
        json={"name": "无效分类一级", "category": "不存在分类", "level": 1},
    ).status_code == 422
    cat_resp = client.post("/admin/capability-tags/categories", headers=admin, json={"name": "临时专题分类"})
    assert cat_resp.status_code == 201
    cat_id = cat_resp.json()["id"]
    cat_l1 = client.post(
        "/admin/capability-tags",
        headers=admin,
        json={"name": "分类同步一级", "category": "临时专题分类", "level": 1},
    )
    assert cat_l1.status_code == 201
    cat_l1_id = cat_l1.json()["id"]
    cat_l2 = client.post(
        "/admin/capability-tags",
        headers=admin,
        json={"name": "分类同步二级", "level": 2, "parentId": cat_l1_id},
    )
    assert cat_l2.status_code == 201
    assert client.put(
        f"/admin/capability-tags/{cat_l1_id}",
        headers=admin,
        json={"category": "不存在分类"},
    ).status_code == 422
    assert client.put(
        f"/admin/capability-tags/categories/{cat_id}",
        headers=admin,
        json={"name": "改名专题分类"},
    ).status_code == 200
    with get_db() as conn:
        cats = {
            r["level"]: r["category"]
            for r in conn.execute("SELECT level, category FROM capability_tags WHERE id IN (?, ?)", (cat_l1_id, cat_l2.json()["id"])).fetchall()
        }
        assert cats == {1: "改名专题分类", 2: "改名专题分类"}

    # Bug ②: whitespace capability filter returns 200 without SQL error and exact match does not substring-match sibling tags.
    now = datetime.now(timezone.utc).isoformat()
    t1 = make_task(admin_user, "数据库需求")
    t2 = make_task(admin_user, "架构现代化需求")
    with get_db() as conn:
        conn.execute(
            "INSERT INTO demand_profiles (id, match_record_id, requirement_text, industry_tags, region_tags, capability_tags, matched_partner_count, supply_status, created_at) "
            "VALUES ('dp-b2-db', ?, '数据库建设', '金融', '北京', '数据库,大数据', 0, 'gap', ?)",
            (t1, now),
        )
        conn.execute(
            "INSERT INTO demand_profiles (id, match_record_id, requirement_text, industry_tags, region_tags, capability_tags, matched_partner_count, supply_status, created_at) "
            "VALUES ('dp-b2-arch', ?, '架构改造', '金融', '北京', '架构现代化', 0, 'gap', ?)",
            (t2, now),
        )
    blank_resp = client.get("/admin/reports?capability=%20%20%20", headers=admin)
    assert blank_resp.status_code == 200
    assert blank_resp.json()["overview"]["totalDemands"] == 2
    sub_resp = client.get("/admin/reports?capability=数据", headers=admin)
    assert sub_resp.status_code == 200
    assert sub_resp.json()["overview"]["totalDemands"] == 0
    exact_resp = client.get("/admin/reports?capability=应用现代化", headers=admin)
    assert exact_resp.status_code == 200
    assert exact_resp.json()["overview"]["totalDemands"] == 1


def test_adopt_suggestion_follows_renamed_scenario_category_and_rejects_unknown(client):
    admin = auth_headers(make_user("adopt-rename-admin", role="admin"))
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        scenario_cat = conn.execute(
            "SELECT id FROM capability_tag_categories WHERE name = '场景化能力'"
        ).fetchone()
        assert scenario_cat is not None
        conn.execute(
            "INSERT INTO capability_tag_suggestions (id, suggested_name, suggested_category_name, description, confidence, occurrence_count, status, created_at, updated_at) "
            "VALUES ('sug-before-rename', '改名前场景建议', '场景化能力', '测试描述', 0.9, 1, 'pending', ?, ?)",
            (now, now),
        )

    rename_resp = client.put(
        f"/admin/capability-tags/categories/{scenario_cat['id']}",
        headers=admin,
        json={"name": "场景专题能力"},
    )
    assert rename_resp.status_code == 200
    assert rename_resp.json()["name"] == "场景专题能力"

    with get_db() as conn:
        updated_sug = conn.execute(
            "SELECT suggested_category_name FROM capability_tag_suggestions WHERE id = 'sug-before-rename'"
        ).fetchone()
        assert updated_sug["suggested_category_name"] == "场景专题能力"

    adopt1 = client.post(
        "/admin/capability-tags/suggestions/sug-before-rename/adopt",
        headers=admin,
        json={"name": "改名前场景建议", "level": 1},
    )
    assert adopt1.status_code == 200
    assert adopt1.json()["category"] == "场景专题能力"

    tree = client.get("/admin/capability-tags/tree", headers=admin).json()
    renamed_group = next(g for g in tree if g["name"] == "场景专题能力")
    assert any(t["name"] == "改名前场景建议" for t in renamed_group["tags"])

    with get_db() as conn:
        conn.execute(
            "INSERT INTO capability_tag_suggestions (id, suggested_name, suggested_category_name, description, confidence, occurrence_count, status, created_at, updated_at) "
            "VALUES ('sug-stale-scenario', '遗留场景建议', '场景化能力', '测试描述', 0.8, 1, 'pending', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO capability_tag_suggestions (id, suggested_name, suggested_category_name, description, confidence, occurrence_count, status, created_at, updated_at) "
            "VALUES ('sug-bad-cat', '无效分类建议', '场景化能力', '测试描述', 0.7, 1, 'pending', ?, ?)",
            (now, now),
        )

    adopt2 = client.post(
        "/admin/capability-tags/suggestions/sug-stale-scenario/adopt",
        headers=admin,
        json={"name": "遗留场景建议", "level": 1},
    )
    assert adopt2.status_code == 200
    assert adopt2.json()["category"] == "场景专题能力"

    adopt_bad = client.post(
        "/admin/capability-tags/suggestions/sug-bad-cat/adopt",
        headers=admin,
        json={"name": "无效分类建议", "level": 1, "categoryId": "不存在分类"},
    )
    assert adopt_bad.status_code == 422



