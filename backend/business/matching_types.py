"""Existing matching stage contracts; shared without application imports."""
from typing import Literal
from pydantic import Field, StrictBool
from .common import ModelOutput, StrictModel


class ProjectFacts(ModelOutput):
    customerName: str='未知'
    projectName: str='未知'
    industry: str='未知'
    region: str='未知'
    projectStage: str='未知'
    businessNeeds: str='未知'
    technicalNeeds: str='未知'
    deliveryNeeds: str=Field(default='未知',description='项目需要完成的工作及用户明示的承接范围；不把全部工作转成每家伙伴必备资格。')
    qualificationRequirements: str=Field(default='未知',description='用户明确限定合作方本身的资质或资格及其限定对象；一般项目工作不是每家资格，未明示保持未知，不增加条件或凭证形式。')
    caseRequirements: str=Field(default='未知',description='用户明确限定合作方本身的经验、案例或交付依据要求及其限定对象；须由对应资料支持，未明示保持未知，不增加用户未要求的合同或验收凭证形式。')
    onsiteRequirement: str='未知'
    timelineRequirement: str='未知'
    cloudPlatformPreference: str='未知'
    capabilityTags: list[str]=Field(default_factory=list,max_length=30)
    deliveryTypeTags: str=''
    complexityLevel: Literal['高','中','低','未知']='未知'
    urgencyLevel: Literal['高','中','低','未知']='未知'
    projectKeywords: str=''


class TagSuggestion(ModelOutput):
    suggestedName: str=Field(min_length=1,max_length=100)
    suggestedCategoryName: Literal['AI与智能体','云平台与迁移','数据与数据库','应用开发与现代化','运维与安全','咨询与项目管理','其他']='其他'
    description: str=''
    evidenceText: str=''
    confidence: float=Field(default=0.5,ge=0,le=1)


class MatchUnderstanding(ModelOutput):
    in_scope: StrictBool
    facts: ProjectFacts=Field(default_factory=ProjectFacts)
    tag_suggestions: list[TagSuggestion]=Field(default_factory=list,max_length=20)


class ProfileEvidence(StrictModel):
    source: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=2, max_length=25000)


class AnalysisReference(ModelOutput):
    partnerId: str = Field(min_length=1)
    profileEvidence: list[str] = Field(max_length=5)
    evidenceCases: list[str]
    evidenceDeliverables: list[str]


class Candidate(AnalysisReference):
    partnerId: str
    matchScore: str
    matchedCapabilities: str = ''
    matchedIndustries: str = ''
    matchedRegions: str = ''
    recommendationReason: str = Field(description='先写资料依据，再写建议承担的角色；内容较长时空行分成两个短段，短内容不硬拆；不使用标题或列表符号。')
    evidenceType: Literal['current_capability','delivered_project','planning_only','unrelated'] = 'current_capability'
    riskNotes: str = Field(default='',description='只写与该伙伴有关且会改变当前取舍的必要事项，无则空；多项时每项单独一行。')


class MatchAnswer(ModelOutput):
    recommendations: list[Candidate]=Field(default_factory=list,max_length=5)
    supplyStatus: Literal['sufficient','partial','gap','unknown']
    gapAnalysis: str=Field(default='',max_length=2000,description='整体分工、比较及影响取舍的具体未覆盖工作，不逐项罗列所有未知。按整体分工、取舍比较、未覆盖工作与接洽要点的顺序写，用空行分段，通常每段1～2句，无实质内容的主题省略，不重复卡片理由。')
    analysisRefs: list[AnalysisReference]


class InitialCandidate(StrictModel):
    partnerId: str=Field(min_length=1)
    verificationFocus: str=Field(min_length=1,max_length=150)


class InitialSelection(StrictModel):
    candidates: list[InitialCandidate]=Field(default_factory=list,max_length=12)
