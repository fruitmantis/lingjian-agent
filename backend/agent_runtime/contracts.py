"""Versioned, bounded wire protocol. Never carries DB credentials or model keys."""
import hashlib,json
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator, StrictBool
from .strict import StrictModel

PROTOCOL = 'banfei-runtime-v2'
STAGES = {'match': {'understanding','initial_selection','detailed_review'},
          'development': {'analyze','plan','patch'}}

def packed(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def digest(value):
    return hashlib.sha256(packed(value).encode()).hexdigest()

def model_route(endpoint, name):
    # Non-secret deployment identity; credentials stay separately on each server.
    return digest({'endpoint': endpoint.rstrip('/'), 'model': name})

class RetryAuthorization(StrictModel):
    incarnation: UUID
    after_attempt: int = Field(ge=1, strict=True)

class ModelOptions(StrictModel):
    provider_route: str = Field(pattern=r'^[a-f0-9]{64}$')
    thinking: StrictBool
    name: str = Field(min_length=1,max_length=200)
    temperature: float = Field(ge=0,le=2,allow_inf_nan=False)
    top_p: float = Field(gt=0,le=1,allow_inf_nan=False)
    max_tokens: int = Field(ge=1,le=131072)
    timeout_seconds: float = Field(gt=0,allow_inf_nan=False,strict=True)
    timeout_retries: int = Field(ge=0,strict=True)

class Source(StrictModel):
    kind: str = Field(max_length=40)
    source_id: str = Field(min_length=1,max_length=200)
    version: int | None = Field(default=None,ge=1)
    snapshot: str = Field(pattern=r'^[a-f0-9]{64}$')


def source_manifest(data):
    result={}
    def visit(value):
        if isinstance(value,dict):
            if 'source_id' in value and 'source_type' in value:
                item=Source(kind=value['source_type'],source_id=value['source_id'],version=value.get('source_version'),snapshot=digest(value))
                result[(item.kind,item.source_id,item.version)]=item
            elif 'partnerId' in value:
                item=Source(kind='partner',source_id=value['partnerId'],snapshot=digest(value))
                result[(item.kind,item.source_id,None)]=item
            for child in value.values():visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    visit(data)
    return list(result.values())

class StageRequest(StrictModel):
    protocol: Literal['banfei-runtime-v2'] = PROTOCOL
    task_id: UUID
    run_id: UUID
    session_id: UUID
    operation_id: UUID
    incarnation: UUID
    workflow: Literal['match','development']
    stage: str
    snapshot: str = Field(pattern=r'^[a-f0-9]{64}$')
    model_fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    input_token_budget: int = Field(ge=1024,le=262144)
    data: dict
    sources: list[Source] = Field(default_factory=list,max_length=500)
    material_notice: str = "仅使用 VM 按权限预选的有限资料；未提供的能力与证据待核实，不代表能力缺失。"
    model: ModelOptions

    @model_validator(mode='after')
    def bounded(self):
        if len({self.task_id,self.run_id,self.session_id})!=3:raise ValueError('Task, run and session IDs must be distinct')
        if self.stage not in STAGES[self.workflow]:raise ValueError('Unknown stage')
        if self.sources != source_manifest(self.data):raise ValueError('Source manifest mismatch')
        if self.snapshot != digest(self.data):raise ValueError('Snapshot mismatch')
        # UTF-8 byte count is deliberately conservative, not a billed-token claim.
        if len(packed(self.data).encode()) > self.input_token_budget:raise ValueError('Task package exceeds budget')
        allowed = {
            'understanding': {'requirement','standard_tags'},
            'initial_selection': {'facts','partners'},
            'detailed_review': {'facts','candidates'},
            'analyze': {'request','constraints','profile','formal_tags','current','recent_exchanges','message'},
            'plan': {'request','constraints','profile','formal_tags','current','recent_exchanges','message','analysis','understanding','candidates'},
            'patch': {'request','constraints','profile','formal_tags','current','recent_exchanges','message','analysis','understanding','candidates'},
        }[self.stage]
        if set(self.data)-allowed:raise ValueError('Unexpected task package fields')
        return self
