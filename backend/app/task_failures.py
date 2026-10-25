"""Public task reasons; private diagnostic history lives in the server error log."""
import json
import httpx
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from .model_resolver import ModelConfigurationError, ModelContextCapacityError
from .ai_client import ModelResponseError

STAGES={'understanding':'需求理解','tag_suggestion':'标签建议','partner_match':'伙伴推荐','partner_data':'伙伴数据读取','demand_profile':'需求画像','project_opportunity':'项目机会','recommendation_data':'推荐结果','persistence':'结果保存','interrupted':'执行中断','configuration':'模型配置','analysis':'方向分析','retrieval':'资源检索','generation':'建议生成','run_timeout':'执行时限'}
LEGACY_REASONS={
 'timeout':('模型响应超时，本次处理未完成','稍后重试'),
 'rate_limit':('模型服务当前繁忙或请求受限','稍后重试'),
 'configuration':('当前模型配置不可用','联系管理员检查模型配置'),
 'context_capacity':('该模型尚未配置总上下文容量，请管理员填写后重试，或返回切换模型。','联系管理员'),
 'authentication':('模型服务认证失败','联系管理员检查模型访问凭据'),
 'connection':('暂时无法连接模型服务','稍后重试；持续失败请联系管理员'),
 'provider':('模型服务返回异常','稍后重试；持续失败请联系管理员'),
 'invalid_result':('返回的结果不符合要求，未保存本次结果','重试'),
 'persistence':('处理结果未能成功保存','稍后重试；持续失败请联系管理员'),
 'interrupted':('本次处理已中断','重试'),
 'run_timeout':('本次处理超过执行时限，已中断','重试'),
 'input_budget':('伙伴资料超出模型输入预算，任务已保留；请联系管理员核查资料后重试','联系管理员'),
 'unknown':('具体原因未记录','重试或联系管理员'),
}
GENERAL_FAILURE='本次处理失败，请重试。'
SERVICE_FAILURE='服务异常，请联系管理员。'
UNCERTAIN_RESULT='暂未确认结果，请刷新查看。'
SERVICE_CODES={'configuration','authentication','connection','provider','persistence'}
REASONS={code:(SERVICE_FAILURE if code in SERVICE_CODES else GENERAL_FAILURE, '') for code in LEGACY_REASONS}
REASONS['input_budget']=(LEGACY_REASONS['input_budget'][0],LEGACY_REASONS['input_budget'][1])

MODEL_REASONS={
 'timeout':'模型响应超时。本次分析未完成，你可以返回切换模型后重新提交。',
 'rate_limit':'模型服务请求受限。可以稍后重试，或返回切换模型。',
 'connection':'暂时无法连接模型服务，可以重试或返回切换模型。',
 'provider':'模型服务返回异常，可以重试或返回切换模型。',
 'configuration':'当前模型暂不可用。请切换模型，或联系管理员。',
 'context_capacity':'该模型尚未配置总上下文容量，请管理员填写后重试，或返回切换模型。',
 'authentication':'当前模型暂不可用。请切换模型，或联系管理员。',
 'invalid_result':'模型返回内容未能完成解析。可以重试或切换模型。',
}
REASONS['persistence']=('结果保存失败，已有内容已保留。','重试')
REASONS['run_timeout']=('本次处理超过任务执行时限，已中断。','重试')
REASONS['interrupted']=('本次处理已中断，已有内容已保留。','重试')

def is_model_error(error):
 if isinstance(error,PublicTaskError):return is_model_error(error.original_error)
 return bool(getattr(error,'model_call_failure',False) or isinstance(error,(ModelConfigurationError,ModelResponseError)))

class MatchInputBudgetError(ValueError):
 """The complete staged model input cannot fit the configured safety budget."""

def user_message(error):
 return REASONS[classify(error)][0]

class PublicTaskError(HTTPException):
 def __init__(self,error,status_code=502):
  from .error_diagnostics import record_error
  self.original_error=error
  record_error(error)
  self.failure_code=classify(error)
  super().__init__(status_code,REASONS[self.failure_code][0])

def classify(error=None,stage=None):
 if isinstance(error,PublicTaskError):return error.failure_code
 if isinstance(error,MatchInputBudgetError):return 'input_budget'
 if stage=='run_timeout':return 'run_timeout'
 if stage=='interrupted':return 'interrupted'
 if isinstance(error,ModelContextCapacityError):return 'context_capacity'
 if isinstance(error,ModelConfigurationError):return 'configuration'
 if isinstance(error,(httpx.TimeoutException,TimeoutError)):return 'timeout'
 if isinstance(error,httpx.HTTPStatusError):
  return {401:'authentication',403:'authentication',429:'rate_limit'}.get(error.response.status_code,'provider')
 if isinstance(error,httpx.RequestError):return 'connection'
 if isinstance(error,SQLAlchemyError):return 'persistence'
 if isinstance(error,(ModelResponseError,ValueError,ValidationError)):return 'invalid_result'
 return 'unknown'

def failure(stage,error=None,code=None,model_related=None):
 if error is not None:
  from .error_diagnostics import record_error
  record_error(error,stage)
 code=code if code in REASONS else classify(error,stage)
 related=is_model_error(error) if model_related is None else model_related
 related=bool(related and code in MODEL_REASONS and stage not in ('persistence','run_timeout','interrupted'))
 return {'stage':stage if stage in STAGES else 'unknown','stageLabel':STAGES.get(stage,'后续处理'),'code':code,'message':MODEL_REASONS[code] if related else REASONS[code][0],'action':'返回并切换模型' if related else REASONS[code][1],'modelRelated':related}

def public_failures(stages,stored=None):
 stages=(stages or '').split(',');records=[]
 try:
  parsed=json.loads(stored or '[]')
  if isinstance(parsed,list):records=parsed
 except (ValueError,TypeError):pass
 result=[]
 for stage in filter(None,stages):
  code=next((r.get('code') for r in records if isinstance(r,dict) and r.get('stage')==stage),None)
  if code not in REASONS:code=next((k for k,(message,_) in LEGACY_REASONS.items() if message==stored),None)
  origin=next((r.get('modelRelated') is True for r in records if isinstance(r,dict) and r.get('stage')==stage),False)
  result.append(failure(stage,code=code,model_related=origin))
 return result or [failure('unknown')]
