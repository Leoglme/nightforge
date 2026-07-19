"""
Local git repo inspection response (via agent).
"""
from typing import Optional

from pydantic import BaseModel, Field


class RepoInspectResponse(BaseModel):
    """Metadata detected from a local clone path on a machine."""

    exists: bool = False
    is_git: bool = False
    name: Optional[str] = None
    github_repo: Optional[str] = None
    base_branch: Optional[str] = None
    error: Optional[str] = Field(default=None)
