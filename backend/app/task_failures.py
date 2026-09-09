"""Fixed public failure diagnostics. Never persist exception strings or provider bodies."""
import json,sqlite3
import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from .model_resolver import ModelConfigurationError
from .ai_client import ModelResponseError

STAGES={'partner_match':'伙伴匹配','partner_data':'伙伴数据读取','demand_profile':'需求画像','project_opportunity':'项目机会','recommendation_data':'推荐结果','persistence':'结果保存','interrupted':'执行中断','configuration':'模型配置','analysis':'方向分析','retrieval':'资源检索','generation':'建议生成','run_timeout':'执行时限'}
REASONS={
 'timeout':('模型响应超时，本次处理未完成','稍后重试'),
 'rate_limit':('模型服务当前繁忙或请求受限','稍后重试'),
 'configuration':('当前模型配置不可用','联系管理员检查模型配置'),
 'authentication':('模型服务认证失败','联系管理员检查模型访问凭据'),
 'connection':('暂时无法连接模型服务','稍后重试；持续失败请联系管理员'),
 'provider':('模型服务返回异常','稍后重试；持续失败请联系管理员'),
 'invalid_result':('返回的结果不符合要求，未保存本次结果','重试'),
 'persistence':('处理结果未能成功保存','稍后重试；持续失败请联系管理员'),
 'interrupted':('本次处理已中断','重试'),
 'run_timeout':('本次处理超过执行时限，已中断','重试'),
 'unknown':('具体原因未记录','重试或联系管理员'),
}
class PublicTaskError(HTTPException):
 def __init__(self,error,status_code=502):
  self.failure_code=classify(error)
  super().__init__(status_code,REASONS[self.failure_code][0])

def classify(error=None,stage=None):
 if isinstance(error,PublicTaskError):return error.failure_code
 if stage=='run_timeout':return 'run_timeout'
 if stage=='interrupted':return 'interrupted'
 if isinstance(error,ModelConfigurationError):return 'configuration'
 if isinstance(error,(httpx.TimeoutException,TimeoutError)):return 'timeout'
 if isinstance(error,httpx.HTTPStatusError):
  return {401:'authentication',403:'authentication',429:'rate_limit'}.get(error.response.status_code,'provider')
 if isinstance(error,httpx.RequestError):return 'connection'
 if isinstance(error,(SQLAlchemyError,sqlite3.DatabaseError)):return 'persistence'
 if isinstance(error,(ModelResponseError,ValueError,ValidationError)):return 'invalid_result'
 return 'unknown'

def failure(stage,error=None,code=None):
 code=code if code in REASONS else classify(error,stage)
 return {'stage':stage if stage in STAGES else 'unknown','stageLabel':STAGES.get(stage,'后续处理'),'code':code,'message':REASONS[code][0],'action':REASONS[code][1]}

def public_failures(stages,stored=None):
 stages=(stages or '').split(',');records=[]
 try:
  parsed=json.loads(stored or '[]')
  if isinstance(parsed,list):records=parsed
 except (ValueError,TypeError):pass
 result=[]
 for stage in filter(None,stages):
  code=next((r.get('code') for r in records if isinstance(r,dict) and r.get('stage')==stage),None)
  if code not in REASONS:code=next((k for k,(message,_) in REASONS.items() if message==stored),None)
  result.append(failure(stage,code=code))
 return result or [failure('unknown')]
