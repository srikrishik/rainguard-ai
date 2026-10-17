
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AssetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    society_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=2000)


class AssetResponse(BaseModel):
    id: str
    society_id: str
    name: str
    location: str | None = None
    description: str | None = None


class IncidentResponse(BaseModel):
    id: str
    asset_id: str
    occurred_at: datetime
    summary: str


class GemmaObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=500)
    concern: Literal["low", "moderate", "high", "unknown"]


class GemmaReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=1500)
    observations: list[GemmaObservation] = Field(max_length=20)
    severity: Literal["low", "moderate", "high", "unknown"]
    confidence: Literal["low", "medium", "high", "unknown"]
    recommended_actions: list[str] = Field(max_length=10)
    requires_human_review: bool


class InspectionResponse(BaseModel):
    id: str
    asset_id: str
    status: Literal["pending", "completed", "failed"]
    created_at: datetime
    updated_at: datetime | None = None
    content_type: str | None = None
    byte_size: int | None = None
    sha256: str | None = None
    report: GemmaReport | None = None
    error_code: str | None = None


class InspectionCreateResponse(BaseModel):
    inspection_id: str
    status: Literal["pending", "completed", "failed"]
    report: GemmaReport | None = None
    error_code: str | None = None


class RiskAssessmentResponse(BaseModel):
    id: str
    asset_id: str
    assessed_at: datetime
    priority: Literal["high", "medium", "low"]
    score: int = Field(ge=0)
    evidence: list[str]
    data_quality_warnings: list[str]
    requires_human_review: bool
    method: str
    method_version: str
