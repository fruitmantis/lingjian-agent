"""One worker per Runtime session. Restart requires a new VM run, never blind replay."""
import asyncio,hmac,os,uuid,time,logging
import httpx
from contextlib import asynccontextmanager
from datetime import datetime,timezone
from fastapi import FastAPI,HTTPException,Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from .contracts import PROTOCOL,StageRequest,RetryAuthorization,digest,model_route
from .workflows import validate_output
from . import provider
from .diagnostics import StageFailure, ModelOutput, diagnose, diagnostic

def now():return datetime.now(timezone.utc).isoformat()

def create_app(workflow=None):
    incarnation=str(uuid.uuid4());jobs={};pending=set();handles={};binding=None
    @asynccontextmanager
    async def lifespan(app):
        yield
        for task in pending:task.cancel()
        await asyncio.gather(*pending,return_exceptions=True)
    app=FastAPI(lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
    app.state.jobs=jobs;app.state.incarnation=incarnation;app.state.pending=pending

    @app.middleware('http')
    async def secure(request,call_next):
        if request.url.path!='/ping':
            secret=os.environ.get('BANFEI_RUNTIME_SHARED_KEY','')
            supplied=request.headers.get('X-Banfei-Runtime-Key')
            # Fixed diagnostics only: never return credential values, hashes, lengths or headers.
            reason=None
            if not secret:reason='runtime_shared_key_unconfigured'
            elif len(secret)<32:reason='runtime_shared_key_too_short'
            elif supplied is None:reason='runtime_key_header_missing'
            else:
                try:matches=hmac.compare_digest(supplied,secret)
                except TypeError:matches=False
                if not matches:reason='runtime_key_mismatch'
            if reason:return JSONResponse({'detail':'Unauthorized','reason_code':reason},status_code=401)
            try:uuid.UUID(request.headers.get('X-Hw-Agentarts-Session-Id',''))
            except ValueError:return JSONResponse({'detail':'Session required'},status_code=400)
        return await call_next(request)

    @app.get('/ping')
    def ping():
        if len(os.environ.get('BANFEI_RUNTIME_SHARED_KEY',''))<32 or not all(os.environ.get(k) for k in ('BANFEI_MODEL_PROXY_API_KEY',)):
            return JSONResponse({'status':'Unhealthy'},status_code=503)
        try:provider.endpoint()
        except StageFailure:return JSONResponse({'status':'Unhealthy'},status_code=503)
        return {'status':'HealthyBusy' if pending else 'Healthy'}

    @app.get('/runtime-info')
    def info():return {'protocol':PROTOCOL,'incarnation':incarnation,
        'workflow':workflow,'provider_endpoint':digest(provider.endpoint())}

    def view(job):return {k:v for k,v in job.items() if k!='request_hash' and not k.startswith('_')}

    async def execute(packet,attempt_number=1):
        job=jobs[str(packet.operation_id)]
        job.update(status='running',attempt=attempt_number,updated_at=now())
        job.pop('diagnostic',None);job.pop('error',None)
        details={}
        def progress(attempt):job.update(attempt=attempt_number,updated_at=now())
        model_task=asyncio.create_task(provider.completion(packet,progress))
        try:
            while not model_task.done():
                await asyncio.wait({model_task},timeout=1)
                if time.monotonic()>job['_lease']:
                    model_task.cancel()
                    raise StageFailure('vm_lease_expired')
            raw=await model_task
            if isinstance(raw,ModelOutput):details=raw.runtime_metadata
            output=validate_output(packet,raw)
            job.update(status='completed',result=output,updated_at=now())
        except (TimeoutError,httpx.TimeoutException):
            if attempt_number <= packet.model.timeout_retries:
                job.update(status='awaiting_retry',error='model_timeout',diagnostic=diagnostic('model_timeout',retryable=True),updated_at=now())
            else:
                job.update(status='failed',error='model_timeout_exhausted',diagnostic=diagnostic('model_timeout_exhausted'),updated_at=now())
        except asyncio.CancelledError:
            job.update(status='interrupted',error='runtime_interrupted',diagnostic=diagnostic('runtime_interrupted'),updated_at=now());raise
        except Exception as error:
            safe=diagnose(error,details)
            logging.getLogger("banfei.runtime").error("Runtime stage failed operation=%s stage=%s diagnostic=%s",packet.operation_id,packet.stage,safe)
            # Fixed enums and bounded numeric metadata only; no exception/body text.
            job.update(status='failed',error='runtime_execution_failed',diagnostic=safe,updated_at=now())
        finally:
            if not model_task.done():
                model_task.cancel()
                await asyncio.gather(model_task,return_exceptions=True)

    @app.post('/jobs',status_code=202)
    async def submit(request:Request):
        nonlocal binding
        body=bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body)>1048576:raise HTTPException(413,'Package too large')
        try:packet=StageRequest.model_validate_json(body)
        except (ValidationError,ValueError):raise HTTPException(422,'Invalid task package') from None
        if workflow is not None and packet.workflow!=workflow:raise HTTPException(422,'Wrong Runtime workflow')
        if str(packet.incarnation)!=incarnation:raise HTTPException(409,'Runtime restarted; explicit VM retry required')
        if str(packet.session_id)!=request.headers['X-Hw-Agentarts-Session-Id']:raise HTTPException(409,'Session mismatch')
        identity=(str(packet.task_id),str(packet.run_id),str(packet.session_id))
        if binding is not None and identity!=binding:raise HTTPException(409,'Runtime session already bound')
        op=str(packet.operation_id);request_hash=digest(packet.model_dump(mode='json'))
        if op in jobs:
            if jobs[op]['request_hash']!=request_hash:raise HTTPException(409,'Operation payload conflict')
            return view(jobs[op])
        if pending or any(job['status']=='awaiting_retry' for job in jobs.values()):raise HTTPException(409,'A stage is already running or awaiting retry authorization')
        if len(jobs)>=16:raise HTTPException(429,'Session operation limit reached')
        binding=identity
        job={key:str(getattr(packet,key)) for key in ('task_id','run_id','session_id','operation_id','incarnation')}
        job.update(protocol=PROTOCOL,workflow=packet.workflow,stage=packet.stage,snapshot=packet.snapshot,
                   model_fingerprint=packet.model_fingerprint,request_hash=request_hash,status='accepted',attempt=0,updated_at=now(),_lease=time.monotonic()+30,_packet=packet,_retry_authorized=0)
        jobs[op]=job
        task=asyncio.create_task(execute(packet));handles[op]=task;pending.add(task);task.add_done_callback(pending.discard)
        return view(job)

    @app.post('/jobs/{operation_id}/retry',status_code=202)
    async def retry(operation_id:uuid.UUID,authorization:RetryAuthorization,request:Request):
        job=jobs.get(str(operation_id))
        if not job or job['session_id']!=request.headers['X-Hw-Agentarts-Session-Id']:
            raise HTTPException(404,'Operation not present in this session')
        if str(authorization.incarnation)!=incarnation:raise HTTPException(409,'Runtime restarted')
        after=authorization.after_attempt
        # A lost acknowledgement can only reconcile this exact grant, never issue it twice.
        if after<=job['_retry_authorized']:return view(job)
        if job['status']!='awaiting_retry' or job['attempt']!=after or after>job['_packet'].model.timeout_retries:
            raise HTTPException(409,'Retry is not awaiting authorization')
        if time.monotonic()>job['_lease']:
            job.update(status='interrupted',error='vm_lease_expired',diagnostic=diagnostic('vm_lease_expired'),updated_at=now())
            raise HTTPException(409,'VM lease expired')
        job['_retry_authorized']=after
        job.update(status='running',attempt=after+1,updated_at=now())
        job.pop('diagnostic',None);job.pop('error',None)
        task=asyncio.create_task(execute(job['_packet'],after+1))
        handles[str(operation_id)]=task;pending.add(task);task.add_done_callback(pending.discard)
        return view(job)

    @app.get('/jobs/{operation_id}')
    def poll(operation_id:uuid.UUID,request:Request):
        job=jobs.get(str(operation_id))
        if not job or job['session_id']!=request.headers['X-Hw-Agentarts-Session-Id']:raise HTTPException(404,'Operation not present in this session')
        job['_lease']=time.monotonic()+30
        return view(job)

    @app.delete('/jobs/{operation_id}')
    def cancel(operation_id:uuid.UUID,request:Request):
        job=jobs.get(str(operation_id))
        if not job or job['session_id']!=request.headers['X-Hw-Agentarts-Session-Id']:raise HTTPException(404,'Operation not present in this session')
        if job['status'] in ('accepted','running','awaiting_retry'):
            job.update(status='interrupted',error='vm_cancelled',diagnostic=diagnostic('vm_cancelled'),updated_at=now())
            handles[str(operation_id)].cancel()
        return view(job)
    return app

app=create_app()
