"""Loopback-only test emulation of platform per-session containers. Never deploy."""
from contextlib import asynccontextmanager
import asyncio,uuid
import httpx
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import Response
from backend.tests.support.model_test_boundary import require_test_database
require_test_database()
from backend.agent_runtime.server import create_app
sessions={}
@asynccontextmanager
async def lifespan(app):
    yield
    for runtime in sessions.values():
        for task in runtime.state.pending:task.cancel()
        await asyncio.gather(*runtime.state.pending,return_exceptions=True)
app=FastAPI(lifespan=lifespan)
@app.get('/health')
def health():return {'status':'ok','test_only':True}
@app.api_route('/{path:path}',methods=['GET','POST','DELETE'])
async def proxy(path:str,request:Request):
    session=request.headers.get('X-Hw-Agentarts-Session-Id','')
    try:uuid.UUID(session)
    except ValueError:raise HTTPException(400,'Invalid session')
    if session not in sessions:
        if len(sessions)>=100:raise HTTPException(429,'Test session limit')
        sessions[session]=create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=sessions[session]),base_url='http://runtime.test') as client:
        result=await client.request(request.method,'/'+path,headers=request.headers,content=await request.body())
    return Response(result.content,status_code=result.status_code,media_type='application/json')
