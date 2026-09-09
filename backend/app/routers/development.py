"""Authenticated development assistant API, integrated with the existing identity system."""
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter,Depends,Response
from ..auth import require_active_user
from ..database import get_db
from .. import development_lifecycle as life,development_engine as engine,development_views as views
from pydantic import BaseModel,Field,ConfigDict
from ..development_types import DevelopmentRequest,Submit,Revise,Edit,VersionAction,Conversation

router=APIRouter(prefix='/development',tags=['development'])
# In-process execution; Database transactions own concurrency/idempotency. Restart recovery interrupts unfinished runs.
executor=ThreadPoolExecutor(max_workers=4,thread_name_prefix='development')

def private(response:Response):response.headers['Cache-Control']='no-store'
router.dependencies.append(Depends(private))

@router.get('/capabilities')
def capabilities(user:dict=Depends(require_active_user)):
    with get_db() as conn:return [dict(r) for r in conn.execute('SELECT id,name FROM capability_tags WHERE enabled=1 ORDER BY name')]

@router.post('/clarify')
def clarify(body:DevelopmentRequest,user:dict=Depends(require_active_user)):return life.clarify(body)

@router.post('/plans',status_code=202)
def create(body:Submit,user:dict=Depends(require_active_user)):
    result=life.create(body,user)
    if not result['replayed']:executor.submit(engine.execute,result['run_id'])
    return result

@router.get('/plans/{plan_id}')
def detail(plan_id:str,version_id:str|None=None,user:dict=Depends(require_active_user)):return views.detail(plan_id,user,version_id)

@router.post('/plans/{plan_id}/revise',status_code=202)
def revise(plan_id:str,body:Revise,user:dict=Depends(require_active_user)):
    result=life.revise(plan_id,body,user)
    if not result['replayed']:executor.submit(engine.execute,result['run_id'])
    return result

@router.post('/plans/{plan_id}/edit')
def edit(plan_id:str,body:Edit,user:dict=Depends(require_active_user)):return views.edit(plan_id,body,user)

@router.get('/plans/{plan_id}/candidates')
def candidates(plan_id:str,user:dict=Depends(require_active_user)):return views.options(plan_id,user)

@router.post('/plans/{plan_id}/confirm',status_code=204)
def confirm(plan_id:str,body:VersionAction,user:dict=Depends(require_active_user)):views.confirm(plan_id,body.version_id,user)

@router.get('/plans/{plan_id}/transferable')
def preview(plan_id:str,user:dict=Depends(require_active_user)):return views.transferable(plan_id,user)

@router.post('/plans/{plan_id}/copy')
def copy(plan_id:str,body:VersionAction,user:dict=Depends(require_active_user)):return views.transferable(plan_id,user,body.version_id,True)


@router.post('/plans/{plan_id}/conversation')
def conversation(plan_id:str,body:Conversation,user:dict=Depends(require_active_user)):
    result=views.converse(plan_id,body,user)
    if result['kind']=='revise' and not result.get('replayed'):executor.submit(engine.execute,result['run_id'])
    return result


class RetryRun(BaseModel):
    model_config=ConfigDict(extra='forbid')
    submission_id:str=Field(min_length=1,max_length=128)
    based_on_version_id:str|None=None
    run_id:str=Field(min_length=1,max_length=128)

@router.post('/plans/{plan_id}/retry',status_code=202)
def retry(plan_id:str,body:RetryRun,user:dict=Depends(require_active_user)):
    result=life.retry(plan_id,body,user)
    if not result['replayed']:executor.submit(engine.execute,result['run_id'])
    return result
