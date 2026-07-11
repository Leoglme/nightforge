"""
Claude session schemas — resumable conversations on a machine.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ClaudeSessionResponse(BaseModel):
    """A Claude Code session available on a machine."""

    session_id: str
    title: Optional[str] = None
    cwd: Optional[str] = None
    updated_at: datetime


class ClaudeSessionListResponse(BaseModel):
    """List of sessions returned by an agent."""

    sessions: List[ClaudeSessionResponse] = Field(default_factory=list)
