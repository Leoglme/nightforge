"""
Web Push subscription schemas.
"""
from typing import Optional

from pydantic import BaseModel, Field


class PushKeys(BaseModel):
    """Client encryption keys from a browser PushSubscription."""

    p256dh: str
    auth: str


class PushSubscriptionCreate(BaseModel):
    """A browser push subscription registered by the PWA."""

    endpoint: str = Field(..., max_length=500)
    keys: PushKeys
    user_agent: str = Field(default="", max_length=400)


class PushSubscriptionDelete(BaseModel):
    """Endpoint to unregister."""

    endpoint: str = Field(..., max_length=500)


class VapidKeyResponse(BaseModel):
    """Public VAPID key exposed to the browser to subscribe."""

    public_key: Optional[str] = None
    configured: bool = False
