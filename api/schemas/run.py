"""
Run Pydantic schemas.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class RunCreate(BaseModel):
    """Schema for scheduling a night run."""

    machine_id: int = Field(...)
    project_ids: List[int] = Field(..., min_length=1)
    quota_count: int = Field(default=1, ge=1, le=10)
    parallel: bool = Field(default=False)
    scheduled_at: Optional[datetime] = Field(
        default=None, description="When to start; null = start as soon as possible"
    )
    window_end: Optional[datetime] = Field(
        default=None, description="Hard stop; no new quota is started past this time"
    )


class RunAddQuotas(BaseModel):
    """Extend the quota budget of an active run."""

    add: int = Field(..., ge=1, le=9, description="Number of extra 5-hour quotas to allow")


class RunResponse(BaseModel):
    """Schema for a run response."""

    id: int
    machine_id: int
    status: str
    quota_count: int
    parallel: bool
    planned_timeline: Optional[dict] = None
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    window_end: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunEventResponse(BaseModel):
    """Schema for a run event / log line."""

    id: int
    level: str
    message: str
    queue_item_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
