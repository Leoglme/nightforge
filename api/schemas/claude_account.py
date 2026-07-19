"""
Schemas for Claude account vault + usage overview.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ClaudeAccountCreate(BaseModel):
    """Create a vaulted Claude account (OAuth session — email/password optional)."""

    email: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, max_length=500)
    oauth: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Full OAuth block captured via login (accessToken/refreshToken/expiresAt)",
    )
    oauth_json: Optional[str] = Field(
        default=None, max_length=8000, description="Advanced: paste raw OAuth JSON"
    )
    access_token: Optional[str] = Field(
        default=None, max_length=8000, description="Advanced: paste a bare OAuth access token"
    )
    label: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Optional display name; defaults to email or « Compte Claude »",
    )


class ClaudeAccountUpdate(BaseModel):
    """Partial update of a vaulted Claude account."""

    email: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, max_length=500)
    oauth: Optional[Dict[str, Any]] = None
    oauth_json: Optional[str] = Field(default=None, max_length=8000)
    access_token: Optional[str] = Field(default=None, max_length=8000)
    is_active: Optional[bool] = None
    clear_password: bool = False
    clear_oauth: bool = False
    label: Optional[str] = Field(default=None, min_length=1, max_length=120)


class ClaudeAccountResponse(BaseModel):
    """Public account view — never includes decrypted secrets."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    email: Optional[str] = None
    has_password: bool = False
    has_oauth: bool = False
    five_hour_utilization: Optional[float] = None
    seven_day_utilization: Optional[float] = None
    seven_day_opus_utilization: Optional[float] = None
    resets_at: Optional[datetime] = None
    last_checked_at: Optional[datetime] = None
    last_error: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None


class ClaudeAccountCredentials(BaseModel):
    """Decrypted login reminder — only returned on explicit request."""

    id: int
    label: str
    email: Optional[str] = None
    password: Optional[str] = None


class MachineClaudeUsage(BaseModel):
    """Live Claude Max usage from the currently logged-in machine session."""

    pinned: bool = True
    label: str = "Machine actuelle"
    email: Optional[str] = None
    five_hour_utilization: Optional[float] = None
    seven_day_utilization: Optional[float] = None
    seven_day_opus_utilization: Optional[float] = None
    resets_at: Optional[datetime] = None
    source: str = "live"
    error: Optional[str] = None
    buckets: List[dict] = Field(default_factory=list)


class ClaudeAccountsOverview(BaseModel):
    """Page payload: pinned machine usage + vault accounts."""

    machine: Optional[MachineClaudeUsage] = None
    accounts: List[ClaudeAccountResponse]
    selected_account_id: Optional[int] = None
    machine_imported: bool = False
    machine_preferred: bool = False
