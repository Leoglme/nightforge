"""
Schemas for the ideas → queue expansion flow.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from schemas.queue_item import QueueItemResponse


class IdeasExpandRequest(BaseModel):
    """Input: free-form ideas / keywords to turn into queue prompts."""

    ideas: str = Field(..., min_length=1, max_length=20000)
    machine_id: Optional[int] = Field(
        default=None,
        description="Online machine used to run Cursor/Claude for smart expansion",
    )
    prefer_provider: Optional[Literal["cursor", "claude"]] = Field(
        default="cursor",
        description="Preferred LLM for expansion (Composer 2.5 / Haiku)",
    )


class ExpandedIdeaDraft(BaseModel):
    """One planned prompt before (or after) persistence."""

    title: Optional[str] = Field(default=None, max_length=120)
    prompt: str = Field(..., min_length=1)
    provider: Optional[str] = Field(default="cursor", max_length=20)
    model: Optional[str] = Field(default="composer-2.5", max_length=64)
    effort: Optional[str] = Field(default=None, max_length=16)
    fast_mode: bool = False


class IdeasExpandResponse(BaseModel):
    """Result of expanding ideas into queue items."""

    summary: Optional[str] = None
    source: Literal["agent", "groq", "heuristic"] = "heuristic"
    provider_used: Optional[str] = None
    model_used: Optional[str] = None
    items: List[QueueItemResponse]
