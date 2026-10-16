from datetime import datetime

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
