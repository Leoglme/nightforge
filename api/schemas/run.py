"""
Run Pydantic schemas.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class RunFirstMessage(BaseModel):
    """First free-text message that seeds a new remote conversation (Discussions hub)."""

    content: str = Field(..., min_length=1)
    claude_session_id: Optional[str] = Field(
        default=None, max_length=64, description="Claude session UUID to resume on the machine"
    )
    claude_model: Optional[str] = Field(default=None, max_length=64)
    provider: Optional[str] = Field(default=None, max_length=20)
    effort: Optional[str] = Field(default=None, max_length=16)
    fast_mode: bool = Field(default=False)


class RunCreate(BaseModel):
    """Schema for scheduling a night run (or an on-the-fly queue / conversation launch)."""

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
    wait_for_fresh_quota: bool = Field(
        default=True,
        description="Wait for the next bucket reset before the first Claude prompt when the current bucket is in use",
    )
    queue_item_ids: Optional[List[int]] = Field(
        default=None,
        description=(
            "When set, snapshot only these queue items as run messages "
            "(on-the-fly launch from the queue page) instead of project_messages / all pending."
        ),
    )
    first_message: Optional[RunFirstMessage] = Field(
        default=None,
        description=(
            "When set, start a quick single-project conversation seeded with this message "
            "(Discussions hub). Mutually exclusive with queue_item_ids; requires exactly one project."
        ),
    )


class RunAddQuotas(BaseModel):
    """Extend the quota budget of an active run."""

    add: int = Field(..., ge=1, le=9, description="Number of extra 5-hour quotas to allow")


class RunResponse(BaseModel):
    """Schema for a run response."""

    id: int
    machine_id: int
    status: str
    kind: str = "night"
    quota_count: int
    parallel: bool
    planned_timeline: Optional[dict] = None
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    window_end: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    # Conversation-hub enrichments (populated by the list endpoint only).
    project_names: List[str] = Field(default_factory=list)
    title: Optional[str] = Field(
        default=None, description="First user message, truncated — the conversation title"
    )
    last_activity_at: Optional[datetime] = Field(
        default=None, description="Most recent event/finish time, for sorting conversations"
    )

    model_config = ConfigDict(from_attributes=True)


class RunEventResponse(BaseModel):
    """Schema for a run event / log line."""

    id: int
    level: str
    message: str
    queue_item_id: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
