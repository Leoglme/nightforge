"""
Quota Pydantic schemas — planner input/output and snapshots.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class QuotaPlanRequest(BaseModel):
    """Input for the quota planner."""

    quota_count: int = Field(..., ge=1, le=10, description="Number of 5-hour quotas to burn")
    start_at: Optional[datetime] = Field(
        default=None, description="Planned launch time; null = now"
    )
    wake_at: Optional[datetime] = Field(
        default=None, description="Optional wake / availability time to compare against"
    )
    machine_id: Optional[int] = Field(
        default=None, description="Anchor estimates on this machine's latest real reset data"
    )
    wait_for_fresh_quota: bool = Field(
        default=True,
        description="When true, wait for the next bucket reset before window 1 if the current bucket is in use",
    )


class QuotaWindow(BaseModel):
    """One quota window in the planned timeline."""

    index: int = Field(..., description="1-based quota number")
    starts_at: datetime
    resets_at: datetime = Field(..., description="When this burned quota window ends (starts_at + 5h)")
    estimated: bool = Field(
        default=True,
        description="False when window 1 start is anchored on real machine quota data",
    )


class QuotaPlanResponse(BaseModel):
    """Output of the quota planner."""

    windows: List[QuotaWindow]
    fresh_quota_available_at: datetime = Field(
        ..., description="When a full, empty quota is available after all planned windows"
    )
    wait_until: Optional[datetime] = Field(
        default=None,
        description="When window 1 actually starts (after waiting for a fresh bucket reset)",
    )
    anchor_source: Optional[str] = Field(
        default=None,
        description="How window 1 was anchored: live, snapshot, or none (pure estimate)",
    )
    hours_after_wake: Optional[float] = Field(
        default=None, description="Delay between fresh quota and wake_at (negative = before wake)"
    )
    weekly_warning: Optional[str] = Field(
        default=None, description="Warning if a weekly cap may bite before all windows complete"
    )
    quota_auth_error: Optional[str] = Field(
        default=None,
        description="When set, Claude OAuth could not be read on the machine (re-login required)",
    )


class QuotaSnapshotResponse(BaseModel):
    """A stored quota reading."""

    bucket: str
    utilization: float
    resets_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
