"""Pydantic models for the partner domain."""

from pydantic import BaseModel, Field


class PartnerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    intro: str | None = None
    capabilities: str | None = Field(None, description="能力标签，逗号分隔")
    service_areas: str | None = Field(None, description="服务区域，逗号分隔")
    industries: str | None = Field(None, description="行业经验，逗号分隔")


class PartnerOut(BaseModel):
    id: str
    name: str
    intro: str | None
    capabilities: str | None
    service_areas: str | None
    industries: str | None
    ai_profile: str | None
    created_at: str


class CaseCreate(BaseModel):
    partner_id: str
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = None


class CaseOut(BaseModel):
    id: str
    partner_id: str
    title: str
    description: str | None
    created_at: str


class DeliverableOut(BaseModel):
    id: str
    case_id: str
    filename: str
    file_path: str
    created_at: str


class ProfileOut(BaseModel):
    partner_id: str
    ai_profile: str
