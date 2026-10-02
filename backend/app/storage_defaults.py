"""Initial defaults for a NEW PostgreSQL schema only; never run on an existing database."""
import os
import uuid
from datetime import datetime, timezone

def seed_defaults(connection):
    now = datetime.now(timezone.utc).isoformat()
    existing_cats = {row[0] for row in connection.execute("SELECT name FROM capability_tag_categories")}
    preset_cats = [
        ("AI 与智能体", "ai"), ("云平台与迁移", "cloud"), ("数据与数据库", "data"),
        ("应用开发与现代化", "dev"), ("运维与安全", "ops"), ("咨询与项目管理", "consulting"), ("其他", "other"),
    ]
    for cname, ccode in preset_cats:
        if cname not in existing_cats:
            connection.execute(
                "INSERT INTO capability_tag_categories (id, name, code, description, enabled, sort_order, is_preset, created_at, updated_at) VALUES (?, ?, ?, ?, 1, 0, 1, ?, ?)",
                (str(uuid.uuid4()), cname, ccode, "", now, now)
            )

    # Seed preset capability tags
    existing_tags = {row[0] for row in connection.execute("SELECT name FROM capability_tags")}
    preset_tags = [
        ("数据库", "数据与数据库"), ("昇腾云", "云平台与迁移"), ("盘古大模型", "AI 与智能体"),
        ("软件开发生产线（CodeArts）", "应用开发与现代化"), ("智能物联与制造平台", "其他"),
        ("数据仓库", "数据与数据库"), ("大数据", "数据与数据库"), ("集成与治理", "数据与数据库"),
        ("工业智能平台", "其他"), ("云桌面（Workspace）", "云平台与迁移"),
        ("上云规划实施", "云平台与迁移"), ("应用现代化", "应用开发与现代化"),
        ("解决方案集成实施", "应用开发与现代化"), ("容器", "应用开发与现代化"),
        ("数据管理分析与流通", "数据与数据库"), ("安全", "运维与安全"),
        ("公有云云运维", "运维与安全"), ("卓越运营", "运维与安全"),
        ("数字化转型咨询规划", "咨询与项目管理"), ("HCS基础设施规划设计与实施", "云平台与迁移"),
        ("HCS云运维", "运维与安全"), ("开发者技术支持", "咨询与项目管理"),
        ("SAP", "应用开发与现代化"), ("企业协同", "应用开发与现代化"),
    ]
    for name, category in preset_tags:
        if name not in existing_tags:
            connection.execute(
                "INSERT INTO capability_tags (id, name, category, description, enabled, sort_order, is_preset, created_at, updated_at) VALUES (?, ?, ?, ?, 1, 0, 1, ?, ?)",
                (str(uuid.uuid4()), name, category, "", now, now)
            )

    connection.execute("INSERT INTO app_metadata(key,value) VALUES ('schema_version','19')")
    connection.execute("""INSERT INTO model_configs
        (id,name,provider,base_url,api_key_source,api_key_env_name,model_name,temperature,top_p,max_tokens,enabled,is_default,created_at,updated_at)
        VALUES (?,?,'OpenAI Compatible',?,'env','LLM_API_KEY',?,0.3,1.0,131072,1,1,?,?)""",
        (str(uuid.uuid4()),'当前默认模型配置',os.getenv('LLM_BASE_URL','https://api.openai.com/v1'),os.getenv('LLM_MODEL','gpt-4o'),now,now))
    for key,name in [('partner_profile','伙伴画像生成'),('partner_match','智能匹配'),('demand_profile','需求画像分析'),('tag_suggestion','AI 标签建议'),('recommendation_summary','推荐说明生成'),('partner_development','伙伴能力发展'),('default','系统默认')]:
        connection.execute("INSERT INTO model_usage_configs(scene_key,scene_name,model_config_id,description,updated_at) VALUES (?,?,NULL,'',?)",(key,name,now))
    from .resource_categories import initialize
    initialize(connection)
    from .model_timeout_settings import KEY, TimeoutSettings
    connection.execute('INSERT INTO app_metadata(key,value) VALUES (?,?)',(KEY,TimeoutSettings().model_dump_json()))
