"""Existing matching stage contracts; shared without application imports."""
from typing import Literal
from pydantic import Field, StrictBool
from .common import ModelOutput, StrictModel


class PartnerRequirement(ModelOutput):
    mode: Literal['required','preferred','excluded']
    match: Literal['all','any'] = 'all'
    capabilityTags: list[str] = Field(default_factory=list, max_length=30, description='仅用户明确要求持有、优先或排除的正式认证或正式标签；不从工作内容、能力或部署环境推导认证条件。')
    identities: list[str] = Field(default_factory=list, max_length=6)
    evidenceText: str = Field(min_length=2)


class ProjectFacts(ModelOutput):
    customerName: str='未知'
    projectName: str='未知'
    industry: str='未知'
    region: str='未知'
    projectStage: str='未知'
    businessNeeds: str='未知'
    technicalNeeds: str='未知'
    deliveryNeeds: str=Field(default='未知',description='完整保留项目工作及用户明示的交付范围，供逐家针对完整需求独立评估；不拆成伙伴间分工，不增加必备认证或资格。')
    qualificationRequirements: str=Field(default='未知',description='用户明确限定合作方本身的资质或资格及其限定对象；一般项目工作不是每家资格，未明示保持未知，不增加条件或凭证形式。')
    caseRequirements: str=Field(default='未知',description='用户明确限定合作方本身的经验、案例或交付依据要求及其限定对象；须由对应资料支持，未明示保持未知，不增加用户未要求的合同或验收凭证形式。')
    onsiteRequirement: str='未知'
    timelineRequirement: str='未知'
    cloudPlatformPreference: str='未知'
    capabilityTags: list[str]=Field(default_factory=list,max_length=30,description='本次工作相关的标准能力标签，用于认证优先召回，不表示必须持有认证；部署环境不推导为指定产品平台或其专项认证。')
    capabilityEvidence: dict[str,str] = Field(default_factory=dict, description='每个相关标准能力标签对应的需求原文；仅正向工作，不将明确排除的能力作为目标。')
    workEvidence: list[str] | None = Field(default=None, description='本次正向工作主题的连续需求原文，不含单独的行业、区域、身份、排除条件或追问；无工作主题返回空数组。')
    partnerRequirements: list[PartnerRequirement] = Field(default_factory=list, description='仅用户明确提出的正式认证、正式标签或六类身份条件；必须完成的工作和部署要求不转成认证门槛，无明确认证或身份条件返回空数组，业务硬要求仍交给详评。保留必须/优先/排除及或/同时，复杂条件原文交给详评，不生成嵌套规则。')
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
    recommendationReason: str = Field(description='先写该伙伴资料依据，再写其对完整需求的独立适配判断；不生成伙伴间分工、牵头、总集或责任安排，真实历史角色事实保留。用业务语言，不复述实现字段或枚举。内容较长时空行分成两个短段，短内容不硬拆；不使用标题或列表符号。')
    evidenceType: Literal['current_capability','delivered_project','planning_only','unrelated'] = 'current_capability'
    riskNotes: str = Field(default='',description='只写与该伙伴有关且会改变当前取舍的必要事项，无则空；用户未要求的身份不因未维护而增加核验或风险。用业务语言，多项时每项单独一行。')


class MatchAnswer(ModelOutput):
    recommendations: list[Candidate]=Field(default_factory=list,max_length=5,description='只列对应资料支持用户明确必备条件且不触发排除的伙伴；明确必备条件未证实或冲突时不列入，放在gapAnalysis说明，降低分数或风险备注待确认不能替代入选条件。不把普通未知增加为门槛。')
    supplyStatus: Literal['sufficient','partial','gap','unknown']
    gapAnalysis: str=Field(default='',max_length=2000,description='逐家针对完整需求独立适配的比较及影响取舍的具体缺口，可说明因明确必备条件未证实或冲突而未推荐的伙伴；资料未知不等于实际不具备。用业务语言，不复述实现字段或枚举，不拼接多家能力或生成伙伴间责任安排，不逐项罗列所有未知。按独立适配比较、具体缺口与接洽要点的顺序写，用空行分段，通常每段1～2句，无实质内容的主题省略，不重复卡片理由。')
    analysisRefs: list[AnalysisReference]


class InitialCandidate(StrictModel):
    partnerId: str=Field(min_length=1)
    verificationFocus: str=Field(min_length=1,max_length=150)


class InitialSelection(StrictModel):
    candidates: list[InitialCandidate]=Field(default_factory=list,max_length=12)
