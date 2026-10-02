"""Strict request and generated plan contracts. Unknown fields never reach persistence."""
from typing import Annotated, Literal
from pydantic import Field, StrictBool, StringConstraints, field_validator
from .enablement import StrictModel

RawInput = Annotated[str, StringConstraints(strip_whitespace=False)]

class Target(StrictModel):
    capability_tag_id: str
    requirement: str=Field(min_length=1,max_length=1000)
    confirmed_gap: bool=False
    confirmation_note: str=Field(default='',max_length=1000)

class DevelopmentRequest(StrictModel):
    target_partner_id: str | None=None

    @field_validator('target_partner_id', mode='before')
    @classmethod
    def optional_partner(cls, value):
        # Legacy empty selections mean no association; nonempty IDs still require authorization.
        return None if isinstance(value, str) and not value.strip() else value

    development_direction: RawInput=Field(default='',max_length=4000)
    request_source: Literal['partner','partner_manager','jointly_confirmed']='partner_manager'
    raw_demand: RawInput=Field(default='',max_length=4000)
    development_goal: RawInput=Field(default='',max_length=2000)
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
    instruction: RawInput=Field(min_length=1,max_length=2000)
    request: DevelopmentRequest | None=None

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

class ResourceItem(Ref):
    focus: str=Field(default='',max_length=200)
    reason: str=Field(min_length=1,max_length=2000)
    estimated_hours: float=Field(gt=0,le=10000)
    note: str=Field(default='',max_length=2000)

class Item(ResourceItem):
    # Historical/manual edits retain their explicit tag validity check.
    capability_tag_id: str=''

class Stage(StrictModel):
    title: str=Field(min_length=1,max_length=200)
    items: list[Item]=Field(default_factory=list,max_length=50)

class RequestAdjustment(StrictModel):
    development_goal: str | None=Field(default=None,min_length=1,max_length=2000)
    duration_weeks: int | None=Field(default=None,ge=1,le=104)
    hours_per_week: float | None=Field(default=None,gt=0,le=80)
    constraints: dict[str,str] | None=Field(default=None,max_length=8)

class DiagnosisOutput(StrictModel):
    request_adjustment: RequestAdjustment | None=None
    target_partner_id: str | None
    diagnoses: list[Diagnosis]=Field(min_length=1,max_length=20)

class PlanOutput(StrictModel):
    target_partner_id: str | None
    stages: list[Stage]=Field(min_length=1,max_length=20)
    limitations: list[str]=Field(default_factory=list,max_length=30)
    resource_gaps: list[str]=Field(default_factory=list,max_length=30,description='仅说明候选目录未覆盖的目标主题；不得假设用户未说明的零基础或无经验人群，不评价伙伴能力缺口。')

class Edit(StrictModel):
    based_on_version_id: str
    stages: list[Stage]=Field(min_length=1,max_length=20)
    corrections: dict[str,str]=Field(default_factory=dict,max_length=20)

class VersionAction(StrictModel):
    version_id: str

# V1.2 analysis is advice, never a certification or a prerequisite diagnosis.
class Focus(StrictModel):
    reusable_basis: list[str]=Field(default_factory=list,max_length=8,description='仅列用户当前明确自述或资料明确记载的可复用基础，标明来源；没有依据时为空数组，不从目标或资源反推能力。')
    name: str=Field(min_length=1,max_length=200)
    reason: str=Field(min_length=1,max_length=1500,description='只解释该方向与发展目标的关系，不在此判断伙伴已有或缺乏什么能力；当前基础放 reusable_basis，未知信息放 basis_limitations。')
    capability_tag_id: str | None=None
    search_terms: list[str]=Field(default_factory=list,max_length=12)

class DirectionAnalysis(StrictModel):
    partner_assessment: str=Field(default='',max_length=2000,description='仅根据当前明确自述及资料说明基础与目标的关系；未提及写未知，不写没有经验、零基础或缺乏能力。')
    target_partner_id: str | None
    intent: Literal['development','explore','resources']
    interpretation: str=Field(min_length=1,max_length=2000)
    reusable_basis: list[str]=Field(default_factory=list,max_length=12)
    priorities: list[Focus]=Field(default_factory=list,max_length=12)
    basis_limitations: list[str]=Field(default_factory=list,max_length=10)
    resource_types: list[Literal['course','lab','case']]=Field(default_factory=list,max_length=3)
    excluded_levels: list[Literal['basic','advanced']]=Field(default_factory=list,max_length=2)

class AdviceStage(StrictModel):
    title: str=Field(min_length=1,max_length=200)
    items: list[ResourceItem]=Field(default_factory=list,max_length=50)

class AdviceOutput(PlanOutput):
    stages: list[AdviceStage]=Field(default_factory=list,max_length=20)
    answer: str=Field(default='',max_length=5000)
    next_steps: list[str]=Field(default_factory=list,max_length=10)

class Conversation(StrictModel):
    submission_id: str=Field(min_length=8,max_length=128)
    based_on_version_id: str
    message: RawInput=Field(min_length=1,max_length=2000)

class ConversationOutput(StrictModel):
    target_partner_id: str | None
    kind: Literal['explain','revise']
    answer: str=Field(default='',max_length=5000)
    references: list[Ref]=Field(default_factory=list,max_length=30)


class Understanding(DirectionAnalysis):
    in_scope: StrictBool
    action: Literal['answer','generate','patch','regenerate']
    effective_direction: str=Field(max_length=4000)
    # Required on every new understanding; empty string explicitly withdraws a self-report.
    effective_baseline: str=Field(max_length=2000,description='当前有效用户自述，合并明确补充并替换被纠正事实；未提及不等于不会，不从推荐理由或历史模型文字加入事实。')
    effective_constraints: dict[str,str]=Field(default_factory=dict,max_length=8)
    answer: str=Field(default='',max_length=5000)
    references: list[Ref]=Field(default_factory=list,max_length=30)
    edit_item_ids: list[str]=Field(default_factory=list,max_length=50)
    edit_answer_spans: list[str]=Field(default_factory=list,max_length=20)


class ItemChange(StrictModel):
    action: Literal['remove','replace','add_after']
    item_id: str
    items: list[ResourceItem]=Field(default_factory=list,max_length=10)


class AnswerChange(StrictModel):
    before: str=Field(min_length=1,max_length=5000)
    after: str=Field(max_length=5000)


class AdvicePatch(StrictModel):
    target_partner_id: str | None
    changes: list[ItemChange]=Field(default_factory=list,max_length=50)
    answer_changes: list[AnswerChange]=Field(default_factory=list,max_length=20)
    answer: str=Field(min_length=1,max_length=3000)
    # Every new patch explicitly refreshes dependent advice; omitted fields must not retain stale facts.
    limitations: list[str]=Field(max_length=30)
    resource_gaps: list[str]=Field(max_length=30,description='修改后仍存在的目录覆盖缺口，不推断用户未说明的零基础或无经验。')
    next_steps: list[str]=Field(max_length=10)
