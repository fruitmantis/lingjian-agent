"""Initial defaults for a NEW PostgreSQL schema only; never run on an existing database."""
import os
import uuid
from datetime import datetime, timezone

def seed_defaults(connection):
    from .capability_hierarchy import CATALOG

    now = datetime.now(timezone.utc).isoformat()
    existing_cats = {row[0] for row in connection.execute("SELECT name FROM capability_tag_categories")}
    for cat in CATALOG['categories']:
        if cat['name'] not in existing_cats:
            connection.execute(
                "INSERT INTO capability_tag_categories (id, name, code, description, enabled, sort_order, is_preset, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, 1, ?, ?)",
                (str(uuid.uuid4()), cat['name'], cat['code'], cat.get('description', ''), cat['sort_order'], now, now)
            )

    existing_l1 = {
        row[0]: row[1]
        for row in connection.execute("SELECT name, id FROM capability_tags WHERE level = 1")
    }
    for item in CATALOG['tags']:
        l1_id = existing_l1.get(item['name'])
        if not l1_id:
            l1_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO capability_tags (id, name, category, level, parent_id, description, enabled, sort_order, is_preset, created_at, updated_at) VALUES (?, ?, ?, 1, NULL, ?, 1, ?, 1, ?, ?)",
                (l1_id, item['name'], item['category'], "", item['sort_order'], now, now)
            )
            existing_l1[item['name']] = l1_id
        existing_l2 = {
            row[0]
            for row in connection.execute("SELECT name FROM capability_tags WHERE level = 2 AND parent_id = ?", (l1_id,))
        }
        for idx, child_name in enumerate(item['children'], 1):
            if child_name not in existing_l2:
                connection.execute(
                    "INSERT INTO capability_tags (id, name, category, level, parent_id, description, enabled, sort_order, is_preset, created_at, updated_at) VALUES (?, ?, ?, 2, ?, ?, 1, ?, 1, ?, ?)",
                    (str(uuid.uuid4()), child_name, item['category'], l1_id, "", idx, now, now)
                )

    connection.execute("INSERT INTO app_metadata(key,value) VALUES ('schema_version','26')")
    provider_id = str(uuid.uuid4())
    connection.execute("""INSERT INTO model_providers
        (id,name,base_url,protocol,api_key_source,api_key_env_name,created_at,updated_at)
        VALUES (?,'OpenAI Compatible',?,'openai_chat_completions','env','LLM_API_KEY',?,?)""",
        (provider_id,os.getenv('LLM_BASE_URL','https://api.deepseek.com'),now,now))
    connection.execute("""INSERT INTO model_configs
        (id,name,provider_id,model_name,temperature,top_p,max_tokens,enabled,is_default,created_at,updated_at)
        VALUES (?,?,?, ?,0.2,1.0,131072,1,1,?,?)""",
        (str(uuid.uuid4()),'当前默认模型配置',provider_id,os.getenv('LLM_MODEL','deepseek-flash'),now,now))
    for key,name in [('partner_profile','伙伴画像生成'),('partner_match','智能匹配'),('demand_profile','需求画像分析'),('tag_suggestion','AI 标签建议'),('recommendation_summary','推荐说明生成'),('partner_development','伙伴能力发展'),('default','系统默认')]:
        connection.execute("INSERT INTO model_usage_configs(scene_key,scene_name,model_config_id,description,updated_at) VALUES (?,?,NULL,'',?)",(key,name,now))
    from .resource_categories import initialize
    initialize(connection)
    from .model_timeout_settings import KEY, TimeoutSettings
    connection.execute('INSERT INTO app_metadata(key,value) VALUES (?,?)',(KEY,TimeoutSettings().model_dump_json()))
