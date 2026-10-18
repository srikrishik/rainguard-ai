
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class ChecklistItem(BaseModel):
    id: str
    prompt: str
    completed: bool = False
    response: str | None = Field(default=None, max_length=1000)


class InspectionMissionResponse(BaseModel):
    id: str
    asset_id: str
    status: Literal["planned", "in_progress", "completed"]
    checklist: list[ChecklistItem]
    notes: str | None = None
    findings: list[dict[str, Any]] = Field(default_factory=list)
    inspection_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MissionFindingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    checklist_item_id: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    inspection_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list, max_length=10)


class MissionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str | None = Field(default=None, max_length=3000)
    checklist: list[ChecklistItem] | None = None
    status: Literal["planned", "in_progress", "completed"] | None = None


class MaintenanceTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    mission_id: str
    finding_id: str
    description: str = Field(min_length=1, max_length=1000)
    priority: Literal["high", "medium", "low"]
    assignee: str | None = Field(default=None, max_length=200)
    due_date: datetime | None = None
    completion_notes: str | None = Field(default=None, max_length=3000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=10)


class MaintenanceTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "in_progress", "completed"] | None = None
    completion_notes: str | None = Field(default=None, max_length=3000)
    evidence_refs: list[str] | None = Field(default=None, max_length=10)


class ReinspectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notes: str | None = Field(default=None, max_length=1000)
    reinspection_due_at: datetime | None = None

    @field_validator("reinspection_due_at")
    @classmethod
    def normalize_due_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("reinspection_due_at must include a timezone")
        return value.astimezone(timezone.utc)


class MaintenanceTaskResponse(BaseModel):
    id: str
    asset_id: str
    mission_id: str
    finding_id: str
    description: str
    priority: Literal["high", "medium", "low"]
    assignee: str | None = None
    due_date: datetime | None = None
    status: Literal["pending", "in_progress", "completed"]
    created_at: datetime
    updated_at: datetime
    completion_notes: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    reinspection_required: bool = False
    reinspection_status: Literal["not_required", "scheduled", "completed"] = "not_required"
    reinspection_notes: str | None = None
    reinspection_due_at: datetime | None = None


class MaintenanceTaskWorkflowStartResponse(BaseModel):
    task_id: str
    workflow_id: str
    status: Literal["started", "already_started"]
