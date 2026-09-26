"""Pydantic models."""

from typing import Literal

from pydantic import BaseModel, Field, ConfigDict
from .business_taxonomy import ClassificationInput, ClassificationOutput


class PartnerCreate(ClassificationInput):
    name: str = Field(..., min_length=1, max_length=200)
    intro: str | None = None
    capabilities: str | None = Field(None, description="能力标签，逗号分隔")
    service_areas: str | None = Field(None, description="服务区域，逗号分隔")
    industries: str | None = Field(None, description="行业经验，逗号分隔")


class PartnerOut(ClassificationOutput):
    id: str
    name: str
    intro: str | None
    capabilities: str | None
    service_areas: str | None
    industries: str | None
    ai_profile: str | None
    status: Literal["active", "disabled"] = "active"
    profile_needs_update: bool = False
    created_at: str
    updated_at: str | None = None


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category_id: str
    visible: bool = False
    partner_id: str
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = None


class CaseOut(BaseModel):
    category_id: str | None = None
    visible: bool = False
    updated_at: str | None = None
    id: str
    partner_id: str
    title: str
    description: str | None
    created_at: str


class MaterialOut(BaseModel):
    file_type: str = ''
    processing_status: Literal['processing', 'ready', 'empty', 'failed'] = 'processing'
    processing_error: str | None = None
    preview_error: str | None = None
    processed_at: str | None = None


class DeliverableOut(MaterialOut):
    id: str
    case_id: str
    filename: str
    created_at: str


class ProfileOut(BaseModel):
    partner_id: str
    ai_profile: str


class PartnerDocumentOut(MaterialOut):
    id: str
    partner_id: str
    filename: str
    file_type: str
    doc_category: str | None
    extracted_text: str | None = None
    created_at: str


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str = Field(..., min_length=1, max_length=100)
    department: str | None = Field(None, max_length=100)
    role: Literal["admin", "user"] = "user"


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str | None
    department: str | None = None
    role: Literal["admin", "user"]
    status: Literal["active", "disabled"] = "active"
    identity_method: str | None = None
    must_change_password: bool = False
    created_at: str
    updated_at: str | None = None
    last_login_at: str | None = None
    locked_until: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class MatchRequest(BaseModel):
    requirement: str = Field(..., min_length=1)


class PartnerRecommendation(BaseModel):
    partner_id: str
    partner_name: str
    match_score: str
    recommendation_reason: str
    supporting_cases: str
    supporting_deliverables: str
    risk_or_gap_notes: str


class MatchResponse(BaseModel):
    requirement: str
    recommendations: list[PartnerRecommendation]
