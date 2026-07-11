"""
Project Pydantic schemas.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    """Schema for creating a project."""

    name: str = Field(..., min_length=1, max_length=200)
    github_repo: str = Field(..., min_length=1, max_length=400)
    base_branch: str = Field(default="main", max_length=120)


class ProjectUpdate(BaseModel):
    """Schema for updating a project."""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    github_repo: Optional[str] = Field(None, min_length=1, max_length=400)
    base_branch: Optional[str] = Field(None, max_length=120)


class ProjectResponse(BaseModel):
    """Schema for a project response."""

    id: int
    name: str
    github_repo: str
    base_branch: str
    created_at: datetime
    pending_count: int = 0

    model_config = ConfigDict(from_attributes=True)
