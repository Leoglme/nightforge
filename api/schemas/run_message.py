"""
Run message (execution snapshot) Pydantic schemas.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RunMessageResponse(BaseModel):
    """Schema for a run message (execution snapshot)."""

    id: int
    run_id: int
    project_id: int
    order_index: int
    content: str
    claude_session_id: Optional[str] = None
    claude_model: Optional[str] = None
    provider: Optional[str] = None
    effort: Optional[str] = None
    fast_mode: bool = False
    status: str
    error: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunMessageRetry(BaseModel):
    """Payload for re-queuing a run message."""

    content: Optional[str] = Field(
        default=None,
        description="Optional prompt override; defaults to a continue prompt when a session is set",
    )
    claude_session_id: Optional[str] = Field(
        default=None,
        description="Optional Claude session UUID to resume",
    )
    claude_model: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Optional model alias",
    )
    provider: Optional[str] = Field(default=None, max_length=20)
    effort: Optional[str] = Field(default=None, max_length=16)
    fast_mode: Optional[bool] = None


class RunMessageCreate(BaseModel):
    """Payload for appending a message to an active run."""

    project_id: int
    content: str = Field(..., min_length=1)
    claude_session_id: Optional[str] = Field(default=None, max_length=64)
    claude_model: Optional[str] = Field(default=None, max_length=64)
    provider: Optional[str] = Field(default=None, max_length=20)
    effort: Optional[str] = Field(default=None, max_length=16)
    fast_mode: bool = Field(default=False)


class RunProjectSummary(BaseModel):
    """A project attached to a run."""

    project_id: int
    name: str
    order_index: int
    local_path: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
