"""Existing matching stage contracts; shared without application imports."""
from typing import Literal
from pydantic import Field, StrictBool
from .common import StrictModel


class ProjectFacts(StrictModel):
    customerName: str='未知'
    projectName: str='未知'
    industry: str='未知'
    region: str='未知'
    projectStage: str='未知'
    businessNeeds: str='未知'
    technicalNeeds: str='未知'
    deliveryNeeds: str='未知'
    qualificationRequirements: str='未知'
    caseRequirements: str='未知'
    onsiteRequirement: str='未知'
    timelineRequirement: str='未知'
    cloudPlatformPreference: str='未知'
    followUpQuestions: list[str]=Field(default_factory=list,max_length=10)
    capabilityTags: list[str]=Field(default_factory=list,max_length=30)
    deliveryTypeTags: str=''
    complexityLevel: Literal['高','中','低','未知']='未知'
    urgencyLevel: Literal['高','中','低','未知']='未知'
    projectKeywords: str=''


class TagSuggestion(StrictModel):
    suggestedName: str=Field(min_length=1,max_length=100)
    suggestedCategoryName: Literal['AI与智能体','云平台与迁移','数据与数据库','应用开发与现代化','运维与安全','咨询与项目管理','其他']='其他'
    description: str=''
    evidenceText: str=''
    confidence: float=Field(default=0.5,ge=0,le=1)


class MatchUnderstanding(StrictModel):
    in_scope: StrictBool
    facts: ProjectFacts=Field(default_factory=ProjectFacts)
    tag_suggestions: list[TagSuggestion]=Field(default_factory=list,max_length=20)


class ProfileEvidence(StrictModel):
    source: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=2, max_length=25000)


class Candidate(StrictModel):
    partnerId: str
    partnerName: str
    matchScore: str
    matchedCapabilities: str
    matchedIndustries: str
    matchedRegions: str
    recommendationReason: str
    evidenceType: Literal['current_capability','delivered_project','planning_only','unrelated'] = 'current_capability'
    profileEvidence: list[ProfileEvidence] = Field(default_factory=list, max_length=5)
    evidenceCases: list[str]=Field(default_factory=list)
    evidenceDeliverables: list[str]=Field(default_factory=list)
    riskNotes: str


class MatchAnswer(StrictModel):
    recommendations: list[Candidate]=Field(default_factory=list,max_length=5)
    supplyStatus: Literal['sufficient','partial','gap','unknown']
    gapAnalysis: str=Field(default='',max_length=2000)


class InitialCandidate(StrictModel):
    partnerId: str=Field(min_length=1)
    verificationFocus: str=Field(min_length=1,max_length=150)


class InitialSelection(StrictModel):
    candidates: list[InitialCandidate]=Field(default_factory=list,max_length=12)
