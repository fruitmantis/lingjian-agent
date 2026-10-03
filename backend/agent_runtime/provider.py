"""Fixed runtime-side model endpoint; credentials never arrive in task packages."""
import asyncio,json,os,logging
from urllib.parse import urlsplit
import httpx
from .workflows import validate_budget
from .provider_options import provider_request_options
from .contracts import model_route
from .diagnostics import StageFailure, ModelOutput, FINISH_REASONS

async def completion(request,progress):
    name=os.environ.get('BANFEI_RUNTIME_MODEL_NAME','')
    endpoint=os.environ.get('BANFEI_RUNTIME_MODEL_URL','').rstrip('/')
    secret=os.environ.get('BANFEI_RUNTIME_MODEL_KEY','')
    parsed=urlsplit(endpoint)
    local=os.environ.get('BANFEI_RUNTIME_LOCAL_TEST')=='1' and parsed.scheme=='http' and parsed.hostname=='127.0.0.1'
    if request.model.provider_route != model_route(endpoint,name) or not name or name!=request.model.name or not secret or (parsed.scheme!='https' and not local) or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise StageFailure('model_configuration_invalid')
    options=request.model
    messages=validate_budget(request,int(os.environ.get('BANFEI_RUNTIME_CONTEXT_TOKENS','262144')))
    payload={'model':name,'messages':messages,'response_format':{'type':'json_object'},
             'temperature':options.temperature,'top_p':options.top_p,'max_tokens':options.max_tokens}
    payload.update(provider_request_options(endpoint,name))
    # One authorization, one provider attempt. Only VM can authorize a retry.
    progress(1)
    logging.getLogger("uvicorn.error").info("RUNTIME_MODEL_ATTEMPT operation=%s stage=%s",request.operation_id,request.stage)
    async with asyncio.timeout(options.timeout_seconds):
        async with httpx.AsyncClient(timeout=options.timeout_seconds,follow_redirects=False,trust_env=False) as client:
            async with client.stream('POST',endpoint+'/chat/completions',headers={'Authorization':'Bearer '+secret},json=payload) as response:
                response.raise_for_status();parts=[];size=0
                async for part in response.aiter_bytes():
                    size+=len(part)
                    if size>2097152:raise StageFailure('provider_response_too_large', upstream_http_status=response.status_code)
                    parts.append(part)
    try:
        result=json.loads(b''.join(parts));choice=result['choices'][0]
        # Do not keep response bodies on decoding/shape errors.
        finish=choice.get('finish_reason')
        content=choice['message']['content']
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        raise StageFailure('provider_response_invalid', upstream_http_status=response.status_code) from None
    details={'upstream_http_status':response.status_code}
    if finish is not None:
        details['finish_reason']=finish if type(finish) is str and finish in FINISH_REASONS else 'unknown'
    usage={k:v for k,v in result.get('usage',{}).items() if k in ('prompt_tokens','completion_tokens','total_tokens') and isinstance(v,int)}
    logging.getLogger('uvicorn.error').info('RUNTIME_MODEL_USAGE %s',json.dumps({'operation_id':str(request.operation_id),'stage':request.stage,'usage':usage},separators=(',',':')))
    if finish not in ('stop',None):raise StageFailure('model_output_incomplete', **details)
    if not isinstance(content,str) or not content.strip():raise StageFailure('model_output_empty', **details)
    return ModelOutput(content, **details)
