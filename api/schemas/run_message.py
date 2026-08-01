"""
Run message (execution snapshot) Pydantic schemas.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Hard cap on a single base64 image payload (~9 MB decoded); images are compressed client-side.
MAX_IMAGE_BASE64_CHARS = 12_000_000

#: Maximum number of images attached to one message (mirrors Claude's picker limit).
MAX_IMAGES_PER_MESSAGE = 5


class RunMessageImageInput(BaseModel):
    """A single compressed image attached to a message from the mobile PWA."""

    mime: str = Field(..., max_length=64)
    data: str = Field(..., description="Base64-encoded image bytes, without the data: prefix")
    filename: Optional[str] = Field(default="image", max_length=255)

    @field_validator("mime")
    @classmethod
    def _mime_must_be_image(cls, value: str) -> str:
        """Reject anything that is not an image MIME type."""
        if not value.lower().startswith("image/"):
            raise ValueError("mime must be an image/* type")
        return value

    @field_validator("data")
    @classmethod
    def _data_within_limit(cls, value: str) -> str:
        """Guard against oversized payloads before they hit the database."""
        if not value or len(value) > MAX_IMAGE_BASE64_CHARS:
            raise ValueError("image data is empty or too large")
        return value


class RunMessageResponse(BaseModel):
    """Schema for a run message (execution snapshot)."""

    id: int
    run_id: int
    project_id: int
    order_index: int
    content: str
    claude_session_id: Optional[str] = None
    claude_model: Optional[str] = None
    provider: Optional[str] = None
    effort: Optional[str] = None
    fast_mode: bool = False
    status: str
    error: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunMessageRetry(BaseModel):
    """Payload for re-queuing a run message."""

    content: Optional[str] = Field(
        default=None,
        description="Optional prompt override; defaults to a continue prompt when a session is set",
    )
    claude_session_id: Optional[str] = Field(
        default=None,
        description="Optional Claude session UUID to resume",
    )
    claude_model: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Optional model alias",
    )
    provider: Optional[str] = Field(default=None, max_length=20)
    effort: Optional[str] = Field(default=None, max_length=16)
    fast_mode: Optional[bool] = None


class RunMessageCreate(BaseModel):
    """Payload for appending a message to an active run."""

    project_id: int
    content: str = Field(..., min_length=1)
    claude_session_id: Optional[str] = Field(default=None, max_length=64)
    claude_model: Optional[str] = Field(default=None, max_length=64)
    provider: Optional[str] = Field(default=None, max_length=20)
    effort: Optional[str] = Field(default=None, max_length=16)
    fast_mode: bool = Field(default=False)
    images: List[RunMessageImageInput] = Field(
        default_factory=list, max_length=MAX_IMAGES_PER_MESSAGE
    )


class RunProjectSummary(BaseModel):
    """A project attached to a run."""

    project_id: int
    name: str
    order_index: int
    local_path: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
