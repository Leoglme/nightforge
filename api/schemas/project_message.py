"""
Project message (night-message draft) Pydantic schemas.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectMessageCreate(BaseModel):
    """Schema for creating a composed night-message draft."""

    content: str = Field(..., min_length=1)
    claude_session_id: Optional[str] = Field(default=None, max_length=64)
    claude_model: Optional[str] = Field(default=None, max_length=32)
    source_item_ids: Optional[List[int]] = Field(default=None)
    created_from: Optional[str] = Field(default=None, max_length=20)


class ProjectMessageUpdate(BaseModel):
    """Schema for editing a night-message draft."""

    content: Optional[str] = Field(default=None, min_length=1)
    claude_session_id: Optional[str] = Field(default=None, max_length=64)
    claude_model: Optional[str] = Field(default=None, max_length=32)
    source_item_ids: Optional[List[int]] = Field(default=None)


class ProjectMessageReorder(BaseModel):
    """Schema for reordering a project's night-message drafts."""

    ordered_ids: List[int] = Field(..., min_length=1)


class ProjectMessageResponse(BaseModel):
    """Schema for a night-message draft."""

    id: int
    project_id: int
    order_index: int
    content: str
    claude_session_id: Optional[str] = None
    claude_model: Optional[str] = None
    source_item_ids: Optional[List[int]] = None
    created_from: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
