"""
Schemas for Cursor account vault + usage overview.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CursorAccountCreate(BaseModel):
    """Create a vaulted Cursor account (display identity = email)."""

    email: str = Field(..., min_length=3, max_length=255)
    password: Optional[str] = Field(default=None, max_length=500)
    session_token: Optional[str] = Field(
        default=None,
        max_length=8000,
        description="WorkosCursorSessionToken or JWT access token",
    )
    api_key: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional CURSOR_API_KEY for CLI auth",
    )
    label: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Optional; defaults to email",
    )


class CursorAccountUpdate(BaseModel):
    """Partial update of a vaulted Cursor account."""

    email: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, max_length=500)
    session_token: Optional[str] = Field(default=None, max_length=8000)
    api_key: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None
    clear_password: bool = False
    clear_session_token: bool = False
    clear_api_key: bool = False
    label: Optional[str] = Field(default=None, min_length=1, max_length=120)


class CursorAccountResponse(BaseModel):
    """Public account view — never includes decrypted secrets."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    email: Optional[str] = None
    has_password: bool = False
    has_session_token: bool = False
    has_api_key: bool = False
    auto_utilization: Optional[float] = None
    api_utilization: Optional[float] = None
    average_utilization: Optional[float] = None
    resets_at: Optional[datetime] = None
    last_checked_at: Optional[datetime] = None
    last_error: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None


class CursorAccountCredentials(BaseModel):
    """Decrypted login reminder — only returned on explicit request."""

    id: int
    label: str
    email: Optional[str] = None
    password: Optional[str] = None


class MachineCursorUsage(BaseModel):
    """Live Cursor usage from the currently logged-in machine session."""

    pinned: bool = True
    label: str = "Machine actuelle"
    email: Optional[str] = None
    auto_utilization: Optional[float] = None
    api_utilization: Optional[float] = None
    average_utilization: Optional[float] = None
    resets_at: Optional[datetime] = None
    source: str = "live"
    error: Optional[str] = None
    buckets: List[dict] = Field(default_factory=list)


class CursorAccountsOverview(BaseModel):
    """Page payload: pinned machine usage + vault accounts."""

    machine: Optional[MachineCursorUsage] = None
    accounts: List[CursorAccountResponse]
    selected_account_id: Optional[int] = None
    machine_imported: bool = False
    machine_preferred: bool = False
