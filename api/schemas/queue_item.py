"""
Queue item Pydantic schemas.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class QueueItemCreate(BaseModel):
    """Schema for adding a prompt to a project's queue."""

    prompt: str = Field(..., min_length=1)
    title: Optional[str] = Field(default=None, max_length=120)
    provider: Optional[str] = Field(default=None, max_length=20)
    model: Optional[str] = Field(default=None, max_length=64)
    effort: Optional[str] = Field(default=None, max_length=16)
    fast_mode: bool = Field(default=False)
    priority: int = Field(default=100)
    created_from: Optional[str] = Field(default=None, max_length=20)


class QueueItemUpdate(BaseModel):
    """Schema for editing a queued prompt."""

    prompt: Optional[str] = Field(None, min_length=1)
    title: Optional[str] = Field(default=None, max_length=120)
    provider: Optional[str] = Field(default=None, max_length=20)
    model: Optional[str] = Field(default=None, max_length=64)
    effort: Optional[str] = Field(default=None, max_length=16)
    fast_mode: Optional[bool] = None
    priority: Optional[int] = None


class QueueItemResponse(BaseModel):
    """Schema for a queue item response."""

    id: int
    project_id: int
    prompt: str
    title: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    effort: Optional[str] = None
    fast_mode: bool = False
    priority: int
    status: str
    created_from: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
