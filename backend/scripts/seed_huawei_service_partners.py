"""Seed verified Huawei Cloud service partner data into the local SQLite DB.

The records below are limited to facts published on official Huawei Cloud pages.
Capabilities summarize explicitly described case work; they are not represented as
Huawei Cloud certification-label lists unless the source page enumerates them.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "app.db"
COLLECTED_ON = "2026-07-04"


PARTNERS = (
    {
        "name": "软通动力",
        "source": "https://www.huaweicloud.com/partners/case/service_partner/isoftstone/sgmw.html",
        "intro": (
            "华为云官网案例显示，软通动力于2022年成为华为云首家CTSP服务伙伴，"
            "并为先进云咨询与集成伙伴、盘古大模型合作伙伴；官网明确其服务覆盖"
            "中国大陆、亚太和中东。能力项根据官网案例中明确描述的服务内容归纳，"
            "不等同于华为云官方能力标签认证清单。"
        ),
        "capabilities": (
            "多云管理,公有云云运维,ITSM流程管理,全链路可观测,"
            "FinOps云成本治理,云原生改造,云安全与合规"
        ),
        "service_areas": "中国大陆,亚太,中东",
        "industries": "汽车,制造,零售,金融,医疗",
        "case_title": "上汽通用五菱多云场景智慧运维",
        "case_description": (
            "基于轻量级ITSM与华为云AOM、SMN、Prometheus等构建多云智能运维体系，"
            "覆盖流程规范、全链路监控、WarRoom、FinOps成本治理和安全合规。"
        ),
    },
    {
        "name": "天宽",
        "source": "https://www.huaweicloud.com/partners/case/service_partner/tiankuan/index.html",
        "intro": (
            "华为云官网将杭州天宽列为华为云核心服务伙伴和CTSP，官网案例明确描述其"
            "面向能源、制造行业提供AI及大模型落地服务。能力项根据官网案例中明确描述"
            "的服务内容归纳，不等同于华为云官方能力标签认证清单；官网未披露服务区域。"
        ),
        "capabilities": (
            "AI场景咨询,数据治理,数据采集,AI场景定制开发,企业知识库RAG,"
            "AI合同审核,AI应用运维优化,华为云MaaS"
        ),
        "service_areas": None,
        "industries": "能源,制造",
        "case_title": "新界泵业AI知识库与合同审核",
        "case_description": (
            "基于华为云MaaS、RAG与企业数据构建知识库、智能问答和合同审核能力，"
            "并通过工作流自动化支撑企业AI应用持续运营。"
        ),
    },
    {
        "name": "知行志成",
        "source": "https://www.huaweicloud.com/partners/case/service_partner/actwill/index.html",
        "intro": (
            "华为云官网介绍，四川知行志成聚焦公有云与混合云平台咨询、部署、迁移、"
            "运维及软件开发，提供云全生命周期服务。能力项根据官网案例中明确描述的"
            "服务内容归纳，不等同于华为云官方能力标签认证清单；官网未披露服务区域。"
        ),
        "capabilities": (
            "公有云咨询与部署,混合云咨询与部署,云迁移,云运维,软件开发,"
            "混合云容灾,数据备份与恢复,跨云数据同步"
        ),
        "service_areas": None,
        "industries": "医药",
        "case_title": "医药企业异云容灾备份",
        "case_description": (
            "采用多Region、多AZ高可用架构以及VPN或专线、数据库同步、CBR备份等能力，"
            "实现跨云Redis、Elasticsearch、MySQL数据同步与业务连续性保障。"
        ),
    },
)


def sourced(text: str, source: str) -> str:
    return f"{text} 数据来源：{source}（采集日期：{COLLECTED_ON}）。"


def seed() -> tuple[int, int, int, int]:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    partner_inserted = partner_updated = case_inserted = case_updated = 0
    now = datetime.now().isoformat(timespec="seconds")

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        for item in PARTNERS:
            partner = conn.execute(
                "SELECT id FROM partners WHERE name = ? ORDER BY created_at LIMIT 1",
                (item["name"],),
            ).fetchone()

            intro = sourced(item["intro"], item["source"])
            if partner:
                partner_id = partner["id"]
                conn.execute(
                    """
                    UPDATE partners
                    SET intro = ?, capabilities = ?, service_areas = ?, industries = ?
                    WHERE id = ?
                    """,
                    (
                        intro,
                        item["capabilities"],
                        item["service_areas"],
                        item["industries"],
                        partner_id,
                    ),
                )
                partner_updated += 1
            else:
                partner_id = str(uuid4())
                conn.execute(
                    """
                    INSERT INTO partners
                        (id, name, intro, created_at, capabilities, service_areas, industries, ai_profile)
                    VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    (
                        partner_id,
                        item["name"],
                        intro,
                        now,
                        item["capabilities"],
                        item["service_areas"],
                        item["industries"],
                    ),
                )
                partner_inserted += 1

            description = sourced(item["case_description"], item["source"])
            case = conn.execute(
                "SELECT id FROM cases WHERE partner_id = ? AND title = ? LIMIT 1",
                (partner_id, item["case_title"]),
            ).fetchone()
            if case:
                conn.execute(
                    "UPDATE cases SET description = ? WHERE id = ?",
                    (description, case["id"]),
                )
                case_updated += 1
            else:
                conn.execute(
                    """
                    INSERT INTO cases (id, partner_id, title, description, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (str(uuid4()), partner_id, item["case_title"], description, now),
                )
                case_inserted += 1

    return partner_inserted, partner_updated, case_inserted, case_updated


if __name__ == "__main__":
    counts = seed()
    print(
        "Huawei Cloud service partner seed complete: "
        f"partners inserted={counts[0]}, updated={counts[1]}; "
        f"cases inserted={counts[2]}, updated={counts[3]}"
    )
