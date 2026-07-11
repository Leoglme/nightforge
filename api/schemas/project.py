"""
Project Pydantic schemas.
"""
import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _slugify_name(name: str) -> str:
    """Build a placeholder GitHub repo slug from a project name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "projet"


class ProjectCreate(BaseModel):
    """Schema for creating a project."""

    name: str = Field(..., min_length=1, max_length=200)
    github_repo: Optional[str] = Field(default=None, max_length=400)
    base_branch: str = Field(default="main", max_length=120)

    @field_validator("github_repo", mode="before")
    @classmethod
    def normalize_github_repo(cls, value: object) -> Optional[str]:
        """Treat empty strings as missing so the API can apply a placeholder."""
        if value is None:
            return None
        text = str(value).strip()
        return text or None


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
