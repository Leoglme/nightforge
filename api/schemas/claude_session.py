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
    # Resolved when the session's cwd maps to a registered project path (Discussions hub).
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    # True while NightForge is running a message that resumes this session (live spinner).
    is_running: bool = False


class ClaudeSessionListResponse(BaseModel):
    """List of sessions returned by an agent."""

    sessions: List[ClaudeSessionResponse] = Field(default_factory=list)


class SessionTranscriptEvent(BaseModel):
    """One streamed line of a session turn (assistant text or an encoded tool action)."""

    level: str = "info"
    message: str


class SessionTranscriptTurn(BaseModel):
    """A user prompt followed by the assistant text / tool actions it produced."""

    role: str
    content: str
    events: List[SessionTranscriptEvent] = Field(default_factory=list)


class SessionTranscriptResponse(BaseModel):
    """Full chat history rebuilt from a Claude session transcript on a machine."""

    session_id: str
    cwd: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    active: bool = False
    model: Optional[str] = None
    turns: List[SessionTranscriptTurn] = Field(default_factory=list)
