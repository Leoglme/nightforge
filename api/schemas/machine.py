"""
Machine Pydantic schemas.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MachineCreate(BaseModel):
    """Schema for registering a new machine (returns a one-time token)."""

    name: str = Field(..., min_length=1, max_length=120)


class MachineResponse(BaseModel):
    """Schema for a machine as seen in the dashboard."""

    id: int
    name: str
    status: str
    online: bool
    last_seen_at: Optional[datetime] = None
    claude_version: Optional[str] = None
    cursor_version: Optional[str] = None
    agent_version: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MachineCreated(MachineResponse):
    """Machine response including the plaintext agent token (shown once)."""

    agent_token: str
