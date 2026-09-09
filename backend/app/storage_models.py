"""SQLAlchemy Core mapping of the existing v12 storage schema.

Column types intentionally preserve existing TEXT JSON/ISO timestamps and INTEGER flags.
No business model redesign or runtime schema creation occurs.
"""
from sqlalchemy import MetaData, Table, Column, Text, Integer, Float, LargeBinary, Identity, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index, text

metadata = MetaData()

_health_check = Table('_health_check', metadata,
    Column('id', Integer, primary_key=False, nullable=True),
)


app_metadata = Table('app_metadata', metadata,
    Column('key', Text, primary_key=True, nullable=False),
    Column('value', Text, primary_key=False, nullable=False),
)


capability_tag_categories = Table('capability_tag_categories', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('name', Text, primary_key=False, nullable=False),
    Column('code', Text, primary_key=False, nullable=True),
    Column('description', Text, primary_key=False, nullable=True),
    Column('enabled', Integer, primary_key=False, nullable=True, server_default=text('1')),
    Column('sort_order', Integer, primary_key=False, nullable=True, server_default=text('0')),
    Column('is_preset', Integer, primary_key=False, nullable=True, server_default=text('0')),
    Column('created_at', Text, primary_key=False, nullable=False),
    Column('updated_at', Text, primary_key=False, nullable=False),
    UniqueConstraint('name', name='uq_capability_tag_categories_0'),
)


capability_tag_suggestions = Table('capability_tag_suggestions', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('suggested_name', Text, primary_key=False, nullable=False),
    Column('suggested_category_id', Text, primary_key=False, nullable=True),
    Column('suggested_category_name', Text, primary_key=False, nullable=True),
    Column('description', Text, primary_key=False, nullable=True),
    Column('evidence_text', Text, primary_key=False, nullable=True),
    Column('source_requirement', Text, primary_key=False, nullable=True),
    Column('source_match_record_id', Text, primary_key=False, nullable=True),
    Column('confidence', Float, primary_key=False, nullable=True, server_default=text('0.5')),
    Column('occurrence_count', Integer, primary_key=False, nullable=True, server_default=text('1')),
    Column('status', Text, primary_key=False, nullable=True, server_default=text("'pending'")),
    Column('created_at', Text, primary_key=False, nullable=False),
    Column('updated_at', Text, primary_key=False, nullable=False),
    Column('adopted_at', Text, primary_key=False, nullable=True),
    ForeignKeyConstraint(['source_match_record_id'], ['match_records.id'], name='fk_capability_tag_suggestions_0', deferrable=True, initially='IMMEDIATE', use_alter=True, ondelete='RESTRICT', onupdate='RESTRICT'),
)


capability_tags = Table('capability_tags', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('name', Text, primary_key=False, nullable=False),
    Column('category', Text, primary_key=False, nullable=False),
    Column('description', Text, primary_key=False, nullable=True),
    Column('enabled', Integer, primary_key=False, nullable=True, server_default=text('1')),
    Column('sort_order', Integer, primary_key=False, nullable=True, server_default=text('0')),
    Column('is_preset', Integer, primary_key=False, nullable=True, server_default=text('0')),
    Column('created_at', Text, primary_key=False, nullable=False),
    Column('updated_at', Text, primary_key=False, nullable=False),
    UniqueConstraint('name', name='uq_capability_tags_0'),
)


case_share_configs = Table('case_share_configs', metadata,
    Column('case_id', Text, primary_key=True, nullable=False),
    Column('draft_json', Text, primary_key=False, nullable=False),
    Column('revision', Integer, primary_key=False, nullable=False, server_default=text('1')),
    Column('status', Text, primary_key=False, nullable=False, server_default=text("'draft'")),
    Column('published_version', Integer, primary_key=False, nullable=True),
    Column('system_visible', Integer, primary_key=False, nullable=False, server_default=text('0')),
    Column('model_allowed', Integer, primary_key=False, nullable=False, server_default=text('0')),
    Column('partner_allowed', Integer, primary_key=False, nullable=False, server_default=text('0')),
    Column('authorization_epoch', Integer, primary_key=False, nullable=False, server_default=text('1')),
    Column('created_by', Text, primary_key=False, nullable=False),
    Column('created_at', Text, primary_key=False, nullable=False),
    Column('updated_at', Text, primary_key=False, nullable=False),
    CheckConstraint('revision > 0', name='ck_case_share_configs_0'),
    CheckConstraint("status IN ('draft','published','unpublished','revoked')", name='ck_case_share_configs_1'),
    CheckConstraint('system_visible IN (0,1)', name='ck_case_share_configs_2'),
    CheckConstraint('model_allowed IN (0,1)', name='ck_case_share_configs_3'),
    CheckConstraint('partner_allowed IN (0,1)', name='ck_case_share_configs_4'),
    ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_case_share_configs_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_case_share_configs_1', deferrable=True, initially='IMMEDIATE', use_alter=True),
)


case_share_versions = Table('case_share_versions', metadata,
    Column('source_id', Text, primary_key=True, nullable=False),
    Column('version', Integer, primary_key=True, nullable=False),
    Column('payload_json', Text, primary_key=False, nullable=False),
    Column('authorization_epoch', Integer, primary_key=False, nullable=False),
    Column('reviewed_revision', Integer, primary_key=False, nullable=False),
    Column('published_by', Text, primary_key=False, nullable=False),
    Column('published_at', Text, primary_key=False, nullable=False),
    CheckConstraint('version > 0', name='ck_case_share_versions_0'),
    ForeignKeyConstraint(['published_by'], ['users.id'], name='fk_case_share_versions_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['source_id'], ['case_share_configs.case_id'], name='fk_case_share_versions_1', deferrable=True, initially='IMMEDIATE', use_alter=True),
)


cases = Table('cases', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('partner_id', Text, primary_key=False, nullable=False),
    Column('title', Text, primary_key=False, nullable=False),
    Column('description', Text, primary_key=False, nullable=True),
    Column('created_at', Text, primary_key=False, nullable=False),
    ForeignKeyConstraint(['partner_id'], ['partners.id'], name='fk_cases_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
)


deliverables = Table('deliverables', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('case_id', Text, primary_key=False, nullable=False),
    Column('filename', Text, primary_key=False, nullable=False),
    Column('file_path', Text, primary_key=False, nullable=False),
    Column('created_at', Text, primary_key=False, nullable=False),
    ForeignKeyConstraint(['case_id'], ['cases.id'], name='fk_deliverables_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
)


demand_profiles = Table('demand_profiles', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('match_record_id', Text, primary_key=False, nullable=True),
    Column('requirement_text', Text, primary_key=False, nullable=False),
    Column('industry_tags', Text, primary_key=False, nullable=True),
    Column('capability_tags', Text, primary_key=False, nullable=True),
    Column('delivery_type_tags', Text, primary_key=False, nullable=True),
    Column('region_tags', Text, primary_key=False, nullable=True),
    Column('complexity_level', Text, primary_key=False, nullable=True),
    Column('urgency_level', Text, primary_key=False, nullable=True),
    Column('project_keywords', Text, primary_key=False, nullable=True),
    Column('matched_partner_count', Integer, primary_key=False, nullable=True),
    Column('top_partner_names', Text, primary_key=False, nullable=True),
    Column('supply_status', Text, primary_key=False, nullable=True),
    Column('gap_analysis', Text, primary_key=False, nullable=True),
    Column('created_at', Text, primary_key=False, nullable=False),
    ForeignKeyConstraint(['match_record_id'], ['match_records.id'], name='fk_demand_profiles_0', deferrable=True, initially='IMMEDIATE', use_alter=True, ondelete='RESTRICT', onupdate='RESTRICT'),
)

Index('idx_demand_profiles_match', demand_profiles.c.match_record_id, unique=0)

development_audit_events = Table('development_audit_events', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('plan_id', Text, primary_key=False, nullable=False),
    Column('version_id', Text, primary_key=False, nullable=True),
    Column('actor_user_id', Text, primary_key=False, nullable=False),
    Column('action', Text, primary_key=False, nullable=False),
    Column('created_at', Text, primary_key=False, nullable=False),
    ForeignKeyConstraint(['actor_user_id'], ['users.id'], name='fk_development_audit_events_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['version_id'], ['development_versions.id'], name='fk_development_audit_events_1', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['plan_id'], ['development_plans.id'], name='fk_development_audit_events_2', deferrable=True, initially='IMMEDIATE', use_alter=True),
)


development_diagnoses = Table('development_diagnoses', metadata,
    Column('version_id', Text, primary_key=True, nullable=False),
    Column('capability_tag_id', Text, primary_key=True, nullable=False),
    Column('payload_json', Text, primary_key=False, nullable=False),
    ForeignKeyConstraint(['capability_tag_id'], ['capability_tags.id'], name='fk_development_diagnoses_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['version_id'], ['development_versions.id'], name='fk_development_diagnoses_1', deferrable=True, initially='IMMEDIATE', use_alter=True),
)


development_plans = Table('development_plans', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('owner_user_id', Text, primary_key=False, nullable=False),
    Column('request_id', Text, primary_key=False, nullable=False),
    Column('target_partner_id', Text, primary_key=False, nullable=False),
    Column('status', Text, primary_key=False, nullable=False),
    Column('archived_at', Text, primary_key=False, nullable=True),
    Column('current_version_id', Text, primary_key=False, nullable=True),
    Column('confirmed_version_id', Text, primary_key=False, nullable=True),
    Column('active_run_id', Text, primary_key=False, nullable=True),
    Column('created_at', Text, primary_key=False, nullable=False),
    Column('updated_at', Text, primary_key=False, nullable=False),
    CheckConstraint("status IN ('active','archived')", name='ck_development_plans_0'),
    UniqueConstraint('request_id', name='uq_development_plans_0'),
    ForeignKeyConstraint(['active_run_id'], ['development_runs.id'], name='fk_development_plans_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['confirmed_version_id'], ['development_versions.id'], name='fk_development_plans_1', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['current_version_id'], ['development_versions.id'], name='fk_development_plans_2', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['target_partner_id'], ['partners.id'], name='fk_development_plans_3', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['request_id'], ['development_requests.id'], name='fk_development_plans_4', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['owner_user_id'], ['users.id'], name='fk_development_plans_5', deferrable=True, initially='IMMEDIATE', use_alter=True),
)

Index('idx_development_owner', development_plans.c.owner_user_id, development_plans.c.status, development_plans.c.created_at, unique=0)

development_requests = Table('development_requests', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('owner_user_id', Text, primary_key=False, nullable=False),
    Column('target_partner_id', Text, primary_key=False, nullable=False),
    Column('payload_json', Text, primary_key=False, nullable=False),
    Column('created_at', Text, primary_key=False, nullable=False),
    Column('created_by', Text, primary_key=False, nullable=False),
    ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_development_requests_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['target_partner_id'], ['partners.id'], name='fk_development_requests_1', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['owner_user_id'], ['users.id'], name='fk_development_requests_2', deferrable=True, initially='IMMEDIATE', use_alter=True),
)


development_runs = Table('development_runs', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('plan_id', Text, primary_key=False, nullable=False),
    Column('owner_user_id', Text, primary_key=False, nullable=False),
    Column('run_type', Text, primary_key=False, nullable=False),
    Column('submission_id', Text, primary_key=False, nullable=False),
    Column('request_hash', Text, primary_key=False, nullable=False),
    Column('based_on_version_id', Text, primary_key=False, nullable=True),
    Column('status', Text, primary_key=False, nullable=False),
    Column('input_snapshot', Text, primary_key=False, nullable=False),
    Column('model_config_id', Text, primary_key=False, nullable=True),
    Column('execution_token', Text, primary_key=False, nullable=True),
    Column('created_at', Text, primary_key=False, nullable=False),
    Column('started_at', Text, primary_key=False, nullable=True),
    Column('ended_at', Text, primary_key=False, nullable=True),
    Column('error_stage', Text, primary_key=False, nullable=True),
    Column('safe_error_message', Text, primary_key=False, nullable=True),
    CheckConstraint("run_type IN ('generate','revise')", name='ck_development_runs_0'),
    CheckConstraint("status IN ('pending','running','ready','partial','failed','interrupted')", name='ck_development_runs_1'),
    UniqueConstraint('owner_user_id', 'submission_id', name='uq_development_runs_0'),
    ForeignKeyConstraint(['model_config_id'], ['model_configs.id'], name='fk_development_runs_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['based_on_version_id'], ['development_versions.id'], name='fk_development_runs_1', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['owner_user_id'], ['users.id'], name='fk_development_runs_2', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['plan_id'], ['development_plans.id'], name='fk_development_runs_3', deferrable=True, initially='IMMEDIATE', use_alter=True),
)

Index('idx_development_one_run', development_runs.c.plan_id, unique=1, postgresql_where=text("status IN ('pending','running')"))

development_version_items = Table('development_version_items', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('version_id', Text, primary_key=False, nullable=False),
    Column('ordinal', Integer, primary_key=False, nullable=False),
    Column('payload_json', Text, primary_key=False, nullable=False),
    UniqueConstraint('version_id', 'ordinal', name='uq_development_version_items_0'),
    ForeignKeyConstraint(['version_id'], ['development_versions.id'], name='fk_development_version_items_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
)


development_versions = Table('development_versions', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('plan_id', Text, primary_key=False, nullable=False),
    Column('version_no', Integer, primary_key=False, nullable=False),
    Column('based_on_version_id', Text, primary_key=False, nullable=True),
    Column('run_id', Text, primary_key=False, nullable=True),
    Column('payload_json', Text, primary_key=False, nullable=False),
    Column('dependency_json', Text, primary_key=False, nullable=False),
    Column('created_by', Text, primary_key=False, nullable=False),
    Column('created_at', Text, primary_key=False, nullable=False),
    CheckConstraint('version_no>0', name='ck_development_versions_0'),
    UniqueConstraint('plan_id', 'version_no', name='uq_development_versions_0'),
    UniqueConstraint('run_id', name='uq_development_versions_1'),
    ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_development_versions_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['run_id'], ['development_runs.id'], name='fk_development_versions_1', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['based_on_version_id'], ['development_versions.id'], name='fk_development_versions_2', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['plan_id'], ['development_plans.id'], name='fk_development_versions_3', deferrable=True, initially='IMMEDIATE', use_alter=True),
)


enablement_audit_events = Table('enablement_audit_events', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('source_kind', Text, primary_key=False, nullable=False),
    Column('source_id', Text, primary_key=False, nullable=False),
    Column('action', Text, primary_key=False, nullable=False),
    Column('actor_id', Text, primary_key=False, nullable=False),
    Column('revision', Integer, primary_key=False, nullable=False),
    Column('authorization_epoch', Integer, primary_key=False, nullable=False),
    Column('reason', Text, primary_key=False, nullable=False, server_default=text("''")),
    Column('created_at', Text, primary_key=False, nullable=False),
    ForeignKeyConstraint(['actor_id'], ['users.id'], name='fk_enablement_audit_events_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
)

Index('idx_enablement_audit_source', enablement_audit_events.c.source_kind, enablement_audit_events.c.source_id, enablement_audit_events.c.created_at, unique=0)

enablement_resource_versions = Table('enablement_resource_versions', metadata,
    Column('source_id', Text, primary_key=True, nullable=False),
    Column('version', Integer, primary_key=True, nullable=False),
    Column('payload_json', Text, primary_key=False, nullable=False),
    Column('authorization_epoch', Integer, primary_key=False, nullable=False),
    Column('reviewed_revision', Integer, primary_key=False, nullable=False),
    Column('published_by', Text, primary_key=False, nullable=False),
    Column('published_at', Text, primary_key=False, nullable=False),
    CheckConstraint('version > 0', name='ck_enablement_resource_versions_0'),
    ForeignKeyConstraint(['published_by'], ['users.id'], name='fk_enablement_resource_versions_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['source_id'], ['enablement_resources.id'], name='fk_enablement_resource_versions_1', deferrable=True, initially='IMMEDIATE', use_alter=True),
)


enablement_resources = Table('enablement_resources', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('draft_json', Text, primary_key=False, nullable=False),
    Column('revision', Integer, primary_key=False, nullable=False, server_default=text('1')),
    Column('status', Text, primary_key=False, nullable=False, server_default=text("'draft'")),
    Column('published_version', Integer, primary_key=False, nullable=True),
    Column('system_visible', Integer, primary_key=False, nullable=False, server_default=text('0')),
    Column('model_allowed', Integer, primary_key=False, nullable=False, server_default=text('0')),
    Column('partner_allowed', Integer, primary_key=False, nullable=False, server_default=text('0')),
    Column('authorization_epoch', Integer, primary_key=False, nullable=False, server_default=text('1')),
    Column('created_by', Text, primary_key=False, nullable=False),
    Column('created_at', Text, primary_key=False, nullable=False),
    Column('updated_at', Text, primary_key=False, nullable=False),
    CheckConstraint('revision > 0', name='ck_enablement_resources_0'),
    CheckConstraint("status IN ('draft','published','unpublished','revoked')", name='ck_enablement_resources_1'),
    CheckConstraint('system_visible IN (0,1)', name='ck_enablement_resources_2'),
    CheckConstraint('model_allowed IN (0,1)', name='ck_enablement_resources_3'),
    CheckConstraint('partner_allowed IN (0,1)', name='ck_enablement_resources_4'),
    ForeignKeyConstraint(['created_by'], ['users.id'], name='fk_enablement_resources_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
)


enablement_reviews = Table('enablement_reviews', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('source_kind', Text, primary_key=False, nullable=False),
    Column('source_id', Text, primary_key=False, nullable=False),
    Column('revision', Integer, primary_key=False, nullable=False),
    Column('reviewer_id', Text, primary_key=False, nullable=False),
    Column('reviewed_at', Text, primary_key=False, nullable=False),
    Column('link_status', Text, primary_key=False, nullable=False),
    Column('content_checked', Integer, primary_key=False, nullable=False),
    Column('authorization_checked', Integer, primary_key=False, nullable=False),
    Column('note', Text, primary_key=False, nullable=False, server_default=text("''")),
    CheckConstraint("source_kind IN ('resource','case')", name='ck_enablement_reviews_0'),
    CheckConstraint("link_status IN ('available','unavailable','unknown')", name='ck_enablement_reviews_1'),
    ForeignKeyConstraint(['reviewer_id'], ['users.id'], name='fk_enablement_reviews_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
)

Index('idx_enablement_reviews_source', enablement_reviews.c.source_kind, enablement_reviews.c.source_id, enablement_reviews.c.revision, unique=0)

match_records = Table('match_records', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('requirement', Text, primary_key=False, nullable=False),
    Column('recommendations_json', Text, primary_key=False, nullable=False),
    Column('created_at', Text, primary_key=False, nullable=False),
    Column('created_by', Text, primary_key=False, nullable=True),
    Column('owner_user_id', Text, primary_key=False, nullable=False),
    Column('archived_at', Text, primary_key=False, nullable=True),
    Column('task_status', Text, primary_key=False, nullable=False, server_default=text("'ready'")),
    Column('last_error_stage', Text, primary_key=False, nullable=True),
    Column('updated_at', Text, primary_key=False, nullable=False),
    Column('last_error_details', Text, nullable=True),
    CheckConstraint("task_status IN ('matching', 'enriching', 'ready', 'partial', 'failed')", name='ck_match_records_0'),
    ForeignKeyConstraint(['owner_user_id'], ['users.id'], name='fk_match_records_0', deferrable=True, initially='IMMEDIATE', use_alter=True, ondelete='RESTRICT', onupdate='RESTRICT'),
)

Index('idx_match_records_archive_created', match_records.c.archived_at, match_records.c.created_at.desc(), unique=0)
Index('idx_match_records_owner_archive_created', match_records.c.owner_user_id, match_records.c.archived_at, match_records.c.created_at.desc(), unique=0)

model_configs = Table('model_configs', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('name', Text, primary_key=False, nullable=False),
    Column('provider', Text, primary_key=False, nullable=True, server_default=text("'OpenAI Compatible'")),
    Column('base_url', Text, primary_key=False, nullable=True),
    Column('api_key', Text, primary_key=False, nullable=True),
    Column('api_key_source', Text, primary_key=False, nullable=True, server_default=text("'env'")),
    Column('api_key_env_name', Text, primary_key=False, nullable=True, server_default=text("'LLM_API_KEY'")),
    Column('model_name', Text, primary_key=False, nullable=True),
    Column('temperature', Float, primary_key=False, nullable=True, server_default=text('0.3')),
    Column('top_p', Float, primary_key=False, nullable=True, server_default=text('1.0')),
    Column('max_tokens', Integer, primary_key=False, nullable=True, server_default=text('4096')),
    Column('timeout_seconds', Integer, primary_key=False, nullable=True, server_default=text('60')),
    Column('enabled', Integer, primary_key=False, nullable=True, server_default=text('1')),
    Column('is_default', Integer, primary_key=False, nullable=True, server_default=text('0')),
    Column('created_at', Text, primary_key=False, nullable=False),
    Column('updated_at', Text, primary_key=False, nullable=False),
)


model_usage_configs = Table('model_usage_configs', metadata,
    Column('scene_key', Text, primary_key=True, nullable=False),
    Column('scene_name', Text, primary_key=False, nullable=False),
    Column('model_config_id', Text, primary_key=False, nullable=True),
    Column('description', Text, primary_key=False, nullable=True),
    Column('updated_at', Text, primary_key=False, nullable=False),
)


partner_documents = Table('partner_documents', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('partner_id', Text, primary_key=False, nullable=False),
    Column('filename', Text, primary_key=False, nullable=False),
    Column('file_path', Text, primary_key=False, nullable=False),
    Column('file_type', Text, primary_key=False, nullable=False),
    Column('doc_category', Text, primary_key=False, nullable=True),
    Column('extracted_text', Text, primary_key=False, nullable=True),
    Column('created_at', Text, primary_key=False, nullable=False),
    ForeignKeyConstraint(['partner_id'], ['partners.id'], name='fk_partner_documents_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
)


partners = Table('partners', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('name', Text, primary_key=False, nullable=False),
    Column('intro', Text, primary_key=False, nullable=True),
    Column('created_at', Text, primary_key=False, nullable=False),
    Column('capabilities', Text, primary_key=False, nullable=True),
    Column('service_areas', Text, primary_key=False, nullable=True),
    Column('industries', Text, primary_key=False, nullable=True),
    Column('ai_profile', Text, primary_key=False, nullable=True),
    Column('status', Text, primary_key=False, nullable=False, server_default=text("'active'")),
    Column('updated_at', Text, primary_key=False, nullable=True),
)


project_opportunities = Table('project_opportunities', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('match_record_id', Text, primary_key=False, nullable=True),
    Column('requirement_text', Text, primary_key=False, nullable=True),
    Column('customer_name', Text, primary_key=False, nullable=True),
    Column('project_name', Text, primary_key=False, nullable=True),
    Column('industry', Text, primary_key=False, nullable=True),
    Column('region', Text, primary_key=False, nullable=True),
    Column('project_stage', Text, primary_key=False, nullable=True),
    Column('business_needs', Text, primary_key=False, nullable=True),
    Column('technical_needs', Text, primary_key=False, nullable=True),
    Column('delivery_needs', Text, primary_key=False, nullable=True),
    Column('qualification_requirements', Text, primary_key=False, nullable=True),
    Column('case_requirements', Text, primary_key=False, nullable=True),
    Column('onsite_requirement', Text, primary_key=False, nullable=True),
    Column('timeline_requirement', Text, primary_key=False, nullable=True),
    Column('cloud_platform_preference', Text, primary_key=False, nullable=True),
    Column('matched_capability_tags', Text, primary_key=False, nullable=True),
    Column('unmatched_capability_signals', Text, primary_key=False, nullable=True),
    Column('recommended_partner_ids', Text, primary_key=False, nullable=True),
    Column('recommended_partner_names', Text, primary_key=False, nullable=True),
    Column('supply_status', Text, primary_key=False, nullable=True),
    Column('completeness_score', Float, primary_key=False, nullable=True),
    Column('missing_fields', Text, primary_key=False, nullable=True),
    Column('follow_up_questions', Text, primary_key=False, nullable=True),
    Column('created_at', Text, primary_key=False, nullable=False),
    Column('updated_at', Text, primary_key=False, nullable=False),
    ForeignKeyConstraint(['match_record_id'], ['match_records.id'], name='fk_project_opportunities_0', deferrable=True, initially='IMMEDIATE', use_alter=True, ondelete='RESTRICT', onupdate='RESTRICT'),
)

Index('idx_project_opportunities_match', project_opportunities.c.match_record_id, unique=0)

resource_capability_map = Table('resource_capability_map', metadata,
    Column('resource_id', Text, primary_key=True, nullable=False),
    Column('capability_tag_id', Text, primary_key=True, nullable=False),
    ForeignKeyConstraint(['capability_tag_id'], ['capability_tags.id'], name='fk_resource_capability_map_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['resource_id'], ['enablement_resources.id'], name='fk_resource_capability_map_1', deferrable=True, initially='IMMEDIATE', use_alter=True),
)


resource_redirect_events = Table('resource_redirect_events', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('actor_user_id', Text, primary_key=False, nullable=False),
    Column('source_type', Text, primary_key=False, nullable=False),
    Column('source_id', Text, primary_key=False, nullable=False),
    Column('source_version', Integer, primary_key=False, nullable=False),
    Column('event_type', Text, primary_key=False, nullable=False),
    Column('created_at', Text, primary_key=False, nullable=False),
    CheckConstraint("source_type IN ('course','lab','case')", name='ck_resource_redirect_events_0'),
    CheckConstraint('source_version > 0', name='ck_resource_redirect_events_1'),
    CheckConstraint("event_type='redirect_initiated'", name='ck_resource_redirect_events_2'),
    ForeignKeyConstraint(['actor_user_id'], ['users.id'], name='fk_resource_redirect_events_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
)

Index('idx_resource_redirect_actor', resource_redirect_events.c.actor_user_id, resource_redirect_events.c.created_at, unique=0)

user_applications = Table('user_applications', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('username', Text, primary_key=False, nullable=False),
    Column('display_name', Text, primary_key=False, nullable=False),
    Column('department', Text, primary_key=False, nullable=True),
    Column('contact', Text, primary_key=False, nullable=True),
    Column('reason', Text, primary_key=False, nullable=True),
    Column('password_hash', Text, primary_key=False, nullable=True),
    Column('status', Text, primary_key=False, nullable=False, server_default=text("'pending'")),
    Column('review_note', Text, primary_key=False, nullable=True),
    Column('reviewed_by', Text, primary_key=False, nullable=True),
    Column('reviewed_at', Text, primary_key=False, nullable=True),
    Column('user_id', Text, primary_key=False, nullable=True),
    Column('applicant_ip', Text, primary_key=False, nullable=True),
    Column('created_at', Text, primary_key=False, nullable=False),
    Column('updated_at', Text, primary_key=False, nullable=False),
    Column('employee_id', Text, primary_key=False, nullable=True),
    Column('email', Text, primary_key=False, nullable=True),
    ForeignKeyConstraint(['reviewed_by'], ['users.id'], name='fk_user_applications_0', deferrable=True, initially='IMMEDIATE', use_alter=True),
    ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_user_applications_1', deferrable=True, initially='IMMEDIATE', use_alter=True),
)

Index('idx_user_applications_status_created', user_applications.c.status, user_applications.c.created_at.desc(), unique=0)
Index('idx_user_applications_username', user_applications.c.username, unique=0)

user_audit_logs = Table('user_audit_logs', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('actor_user_id', Text, primary_key=False, nullable=True),
    Column('action', Text, primary_key=False, nullable=False),
    Column('target_user_id', Text, primary_key=False, nullable=True),
    Column('summary', Text, primary_key=False, nullable=True),
    Column('ip_address', Text, primary_key=False, nullable=True),
    Column('created_at', Text, primary_key=False, nullable=False),
)

Index('idx_user_audit_created', user_audit_logs.c.created_at.desc(), unique=0)

users = Table('users', metadata,
    Column('id', Text, primary_key=True, nullable=False),
    Column('username', Text, primary_key=False, nullable=False),
    Column('hashed_password', Text, primary_key=False, nullable=False),
    Column('display_name', Text, primary_key=False, nullable=True),
    Column('role', Text, primary_key=False, nullable=True, server_default=text("'user'")),
    Column('created_at', Text, primary_key=False, nullable=False),
    Column('department', Text, primary_key=False, nullable=True),
    Column('status', Text, primary_key=False, nullable=False, server_default=text("'active'")),
    Column('must_change_password', Integer, primary_key=False, nullable=False, server_default=text('0')),
    Column('token_version', Integer, primary_key=False, nullable=False, server_default=text('0')),
    Column('last_login_at', Text, primary_key=False, nullable=True),
    Column('failed_login_count', Integer, primary_key=False, nullable=False, server_default=text('0')),
    Column('locked_until', Text, primary_key=False, nullable=True),
    Column('password_changed_at', Text, primary_key=False, nullable=True),
    Column('created_by', Text, primary_key=False, nullable=True),
    Column('updated_at', Text, primary_key=False, nullable=True),
    UniqueConstraint('username', name='uq_users_0'),
)

Index('idx_users_status_role', users.c.status, users.c.role, unique=0)


def create_postgres_schema(connection):
    """Explicit setup/import only. Runtime must find a migrated schema already present."""
    if connection.dialect.name != 'postgresql':
        raise ValueError('PostgreSQL connection required')
    metadata.create_all(connection)
    connection.exec_driver_sql("""CREATE OR REPLACE FUNCTION banfei_immutable_version() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable version data' USING ERRCODE='23514'; END $$""")
    for table, trigger in [('development_versions','development_version_immutable'),
                           ('development_version_items','development_item_immutable'),
                           ('development_diagnoses','development_diagnosis_immutable')]:
        connection.exec_driver_sql(f'CREATE TRIGGER {trigger} BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION banfei_immutable_version()')
