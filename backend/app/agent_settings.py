"""Two fixed business agents and one processing model; no execution registry."""
import json
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal
from urllib.parse import urlsplit
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from .database import get_db, get_readonly_db

KEY = 'agent_settings_v1'
LEGACY_KEY = 'agent_settings_legacy_v1'
SELECTABLE_KEY = 'model_user_selectable_v1'
AGENT_IDS = ('partner_match', 'partner_development')
OLD_SCENES = (*AGENT_IDS, 'default', 'partner_profile', 'demand_profile', 'tag_suggestion', 'recommendation_summary')
_EXECUTION = ContextVar('agent_execution', default=None)


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)
    modelConfigId: str | None = None
    thinking: StrictBool = True
    timeoutSeconds: float = Field(default=300, gt=0, allow_inf_nan=False, strict=True)
    timeoutRetries: int = Field(default=3, ge=0, strict=True)


class AgentSettings(ModelSettings):
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(max_length=300)
    icon: Literal['users', 'trend', 'search', 'puzzle', 'building', 'toolbox', 'spark']
    enabled: StrictBool = True


def owner(scene):
    return scene if scene in AGENT_IDS else 'processing'


def _legacy(conn):
    from .model_timeout_settings import TimeoutSettings
    row=conn.execute("SELECT value FROM app_metadata WHERE key='model_timeout_settings'").fetchone()
    timeout=TimeoutSettings.model_validate_json(row[0]) if row else TimeoutSettings()
    models=[dict(r) for r in conn.execute('SELECT m.id,p.base_url,m.model_name,m.is_default FROM model_configs m JOIN model_providers p ON p.id=m.provider_id WHERE m.enabled=1 ORDER BY m.is_default DESC,m.created_at,m.id')]
    available={m['id'] for m in models}
    bindings={r['scene_key']:r['model_config_id'] for r in conn.execute('SELECT scene_key,model_config_id FROM model_usage_configs')}
    flash=next((m['id'] for m in models if urlsplit(m['base_url'] or '').hostname=='api.deepseek.com' and m['model_name'] in ('deepseek-flash','deepseek-v4-flash')),None)
    default=next((m['id'] for m in models if m['is_default']),None)
    def model(scene):
        # Existing official Flash connection is reused; never copy its credentials.
        chosen=flash or next((bindings[k] for k in (scene,'default') if bindings.get(k) in available),default)
        return ModelSettings(modelConfigId=chosen,**timeout.model_dump()).model_dump()
    return {'agents':{
        'partner_match':{**model('partner_match'),'name':'伙伴推荐','description':'结合项目需求和已有伙伴资料，寻找合适的交付伙伴。','icon':'users','enabled':True},
        'partner_development':{**model('partner_development'),'name':'伙伴发展','description':'围绕发展目标，提供能力建议与合适的课程、实验资源。','icon':'trend','enabled':True},
    },'processing':model('partner_profile')}


def _display_settings(settings):
    # Read projection for the previous system default only; never write it back.
    agent = settings['agents'].get('partner_match')
    if agent and agent.get('name') == '伙伴匹配':
        return {**settings, 'agents': {**settings['agents'],
                'partner_match': {**agent, 'name': '伙伴推荐'}}}
    return settings


def read(conn=None):
    if conn is None:
        with get_readonly_db() as connection:return read(connection)
    row=conn.execute('SELECT value FROM app_metadata WHERE key=?',(KEY,)).fetchone()
    return _display_settings(json.loads(row[0]) if row else _legacy(conn))


def migrate(conn):
    """Idempotent metadata migration inside the caller's transaction; no schema change."""
    existing=conn.execute('SELECT value FROM app_metadata WHERE key=?',(KEY,)).fetchone()
    if existing:return json.loads(existing[0])
    settings=_legacy(conn)
    old=[dict(r) for r in conn.execute('SELECT * FROM model_usage_configs') if r['scene_key'] in OLD_SCENES]
    timeout=conn.execute("SELECT value FROM app_metadata WHERE key='model_timeout_settings'").fetchone()
    archive={'bindings':old,'timeout':json.loads(timeout[0]) if timeout else None}
    conn.execute('INSERT INTO app_metadata(key,value) VALUES (?,?) ON CONFLICT(key) DO NOTHING',(LEGACY_KEY,json.dumps(archive,ensure_ascii=False)))
    conn.execute('INSERT INTO app_metadata(key,value) VALUES (?,?)',(KEY,json.dumps(settings,ensure_ascii=False)))
    for scene in OLD_SCENES:conn.execute('DELETE FROM model_usage_configs WHERE scene_key=?',(scene,))
    conn.execute("DELETE FROM app_metadata WHERE key='model_timeout_settings'")
    return settings


def save(agent_id,payload):
    if agent_id not in (*AGENT_IDS,'processing'):raise HTTPException(404,'智能体不存在')
    with get_db() as conn:
        conn.lock_writer();settings=migrate(conn)
        if payload.modelConfigId is not None:
            row=conn.execute('SELECT id FROM model_configs WHERE id=? AND enabled=1',(payload.modelConfigId,)).fetchone()
            if not row:raise HTTPException(422,'请选择已启用的模型连接')
        if agent_id=='processing':settings['processing']=payload.model_dump()
        else:settings['agents'][agent_id]=payload.model_dump()
        conn.execute('UPDATE app_metadata SET value=? WHERE key=?',(json.dumps(settings,ensure_ascii=False),KEY))
    return _display_settings(settings)


def selectable(conn):
    row=conn.execute('SELECT value FROM app_metadata WHERE key=?',(SELECTABLE_KEY,)).fetchone()
    return json.loads(row[0]) if row else {}


def set_selectable(conn,model_id,value):
    values=selectable(conn)
    if value is None:values.pop(model_id,None)
    else:values[model_id]=value
    conn.execute('INSERT INTO app_metadata(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(SELECTABLE_KEY,json.dumps(values)))


def model_options(agent_id,conn=None):
    if agent_id not in AGENT_IDS:raise HTTPException(404,'智能体不存在')
    if conn is None:
        with get_readonly_db() as connection:return model_options(agent_id,connection)
    agent=read(conn)['agents'][agent_id];allowed=selectable(conn)
    rows=conn.execute('SELECT m.id,m.name,m.provider_id,p.name AS provider_name FROM model_configs m JOIN model_providers p ON p.id=m.provider_id WHERE m.enabled=1 ORDER BY m.created_at,m.id').fetchall()
    models=[{'id':r['id'],'name':r['name'],'isDefault':r['id']==agent['modelConfigId'],'providerId':r['provider_id'],'providerName':r['provider_name']} for r in rows if r['id']==agent['modelConfigId'] or allowed.get(r['id']) is True]
    return {'models':models,'defaultModelConfigId':agent['modelConfigId'],'agentEnabled':agent['enabled'],
            'unavailableReason':'该智能体已停用' if not agent['enabled'] else ('没有可用模型，请联系管理员。' if not models else None)}


def connection_usage(model_id,conn=None):
    if conn is None:
        with get_readonly_db() as connection:return connection_usage(model_id,connection)
    settings=read(conn)
    bindings=[key for key,value in settings['agents'].items() if value['modelConfigId']==model_id]
    if settings['processing']['modelConfigId']==model_id:bindings.append('processing')
    return {'userSelectable':selectable(conn).get(model_id) is True,'defaultBindings':bindings}


def execution(conn,agent_id,*,accept=False,model_config_id=None):
    settings=migrate(conn) if accept else read(conn)
    selected=settings['processing'] if agent_id=='processing' else settings['agents'][agent_id]
    if accept and agent_id!='processing' and not selected['enabled']:raise HTTPException(409,'该智能体已停用，暂不能发起新的执行；历史结果仍可查看')
    snapshot={'agentId':agent_id,**ModelSettings.model_validate({k:selected[k] for k in ModelSettings.model_fields}).model_dump()}
    if model_config_id is not None:
        if not any(m['id']==model_config_id for m in model_options(agent_id,conn)['models']):
            raise HTTPException(422,'所选模型当前不可用，请重新选择。')
        snapshot['modelConfigId']=model_config_id
    if accept:
        row=conn.execute('SELECT name FROM model_configs WHERE id=?',(snapshot['modelConfigId'],)).fetchone()
        snapshot['modelConfigName']=row['name'] if row else None
    return snapshot


def public_selection(snapshot):
    if not snapshot:return None
    return {'id':snapshot.get('modelConfigId'),'name':snapshot.get('modelConfigName')}


def current_execution():return _EXECUTION.get()


@contextmanager
def execution_scope(snapshot):
    token=_EXECUTION.set(snapshot)
    try:yield
    finally:_EXECUTION.reset(token)


def public_agents():
    settings=read()
    return [{'id':key,**{k:value[k] for k in ('name','description','icon','enabled')}} for key,value in settings['agents'].items()]
