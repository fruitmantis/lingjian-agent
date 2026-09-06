"""Strict request and generated plan contracts. Unknown fields never reach persistence."""
from typing import Literal
from pydantic import Field
from .enablement import StrictModel

class Target(StrictModel):
    capability_tag_id: str
    requirement: str=Field(min_length=1,max_length=1000)
    confirmed_gap: bool=False
    confirmation_note: str=Field(default='',max_length=1000)

class DevelopmentRequest(StrictModel):
    target_partner_id: str=''
    request_source: Literal['partner','partner_manager','jointly_confirmed']='partner_manager'
    raw_demand: str=Field(default='',max_length=4000)
    development_goal: str=Field(default='',max_length=2000)
    trainee_role: str=Field(default='',max_length=300)
    trainee_count: int | None=Field(default=None,ge=1,le=100000)
    known_baseline: str=Field(default='',max_length=2000)
    duration_weeks: int | None=Field(default=None,ge=1,le=104)
    hours_per_week: float | None=Field(default=None,gt=0,le=80)
    constraints: dict[str,str]=Field(default_factory=dict,max_length=8)
    accepted_assumptions: dict[str,str]=Field(default_factory=dict,max_length=20)
    targets: list[Target]=Field(default_factory=list,max_length=20)
    source_task_id: str | None=None
    source_case_id: str | None=None
    source_case_version: int | None=Field(default=None,ge=1)
    model_input_allowed: bool=False
    partner_goal_allowed: bool=False

class Submit(StrictModel):
    submission_id: str=Field(min_length=8,max_length=128)
    request: DevelopmentRequest

class Revise(StrictModel):
    submission_id: str=Field(min_length=8,max_length=128)
    based_on_version_id: str | None
    instruction: str=Field(min_length=1,max_length=2000)
    request: DevelopmentRequest

class Ref(StrictModel):
    source_type: Literal['course','lab','case']
    source_id: str=Field(min_length=1,max_length=128)
    source_version: int=Field(ge=1)

class Diagnosis(StrictModel):
    capability_tag_id: str
    target_requirement: str=Field(min_length=1,max_length=1000)
    target_satisfaction: Literal['satisfied','partially_satisfied','not_satisfied','needs_assessment']
    evidence_status: Literal['sufficient','partial','missing','conflicting']
    judgment_source: Literal['model_inference','user_confirmed','business_correction']
    evidence_refs: list[Ref]=Field(default_factory=list,max_length=50)
    pending_verifications: list[str]=Field(default_factory=list,max_length=20)
    problem_type: Literal['trainable_gap','evidence_gap','non_training_constraint','needs_clarification']

class Item(Ref):
    capability_tag_id: str
    reason: str=Field(min_length=1,max_length=2000)
    estimated_hours: float=Field(gt=0,le=10000)
    note: str=Field(default='',max_length=2000)

class Stage(StrictModel):
    title: str=Field(min_length=1,max_length=200)
    items: list[Item]=Field(default_factory=list,max_length=50)

class DiagnosisOutput(StrictModel):
    target_partner_id: str
    diagnoses: list[Diagnosis]=Field(min_length=1,max_length=20)

class PlanOutput(StrictModel):
    target_partner_id: str
    stages: list[Stage]=Field(min_length=1,max_length=20)
    limitations: list[str]=Field(default_factory=list,max_length=30)
    resource_gaps: list[str]=Field(default_factory=list,max_length=30)

class Edit(StrictModel):
    based_on_version_id: str
    stages: list[Stage]=Field(min_length=1,max_length=20)
    corrections: dict[str,str]=Field(default_factory=dict,max_length=20)

class VersionAction(StrictModel):
    version_id: str
