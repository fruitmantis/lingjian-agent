"""Fixed agent settings; existing model connections own all credentials."""
from fastapi import APIRouter, Depends, Response, HTTPException
from ..auth import require_admin, require_active_user
from .. import agent_settings

router=APIRouter(prefix='/admin/agents',tags=['agents'],dependencies=[Depends(require_admin)])
public_router=APIRouter(tags=['agents'],dependencies=[Depends(require_active_user)])

def private(response:Response):response.headers['Cache-Control']='no-store'
router.dependencies.append(Depends(private));public_router.dependencies.append(Depends(private))

@public_router.get('/agents')
def public_agents():return agent_settings.public_agents()

@router.get('')
def settings():return agent_settings.read()

@router.put('/processing')
def save_processing(payload:agent_settings.ModelSettings):return agent_settings.save('processing',payload)

@router.put('/{agent_id}')
def save_agent(agent_id:str,payload:agent_settings.AgentSettings):
    if agent_id not in agent_settings.AGENT_IDS:raise HTTPException(404,'智能体不存在')
    return agent_settings.save(agent_id,payload)
