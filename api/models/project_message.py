"""
Project message model — a composed "night message" draft for a project.

The chat composer lets the user build, in advance, the exact ordered sequence of messages
that will be sent to Claude Code during the night. Each message is free text, optionally
assembled from one or more queue items (the prompt library). Drafts live independently of
runs so they can be prepared from any device and reused night after night; at launch they
are snapshotted into :class:`RunMessage` rows for execution.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base

if TYPE_CHECKING:
    from models.project import Project


class ProjectMessage(Base):
    """
    A composed night-message draft attached to a project.

    Attributes:
        id: Unique identifier.
        project_id: Owning project.
        order_index: Position in the night sequence (lower runs first).
        content: The final text sent to the provider CLI.
        claude_session_id: Optional session to resume (Claude).
        claude_model: Model alias for the chosen provider.
        provider: ``claude`` or ``cursor``.
        effort: Effort / thinking level when supported.
        fast_mode: Fast variant when supported.
        source_item_ids: Queue item ids this message was assembled from (JSON list), if any.
        created_from: Origin device (web/desktop/mobile).
    """

    __tablename__ = "project_messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    claude_session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    claude_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    effort: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    fast_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_item_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_from: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=func.now(), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="messages")

    def __repr__(self) -> str:
        """String representation of the project message."""
        return f"<ProjectMessage id={self.id} project={self.project_id} order={self.order_index}>"
