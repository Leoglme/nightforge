"""
Queue item model — a single prompt in a project's library / waiting list.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base
from enums.queue_item_status import QueueItemStatus

if TYPE_CHECKING:
    from models.project import Project


class QueueItem(Base):
    """
    A prompt queued for a project (library + optional overnight execution).

    Attributes:
        id: Unique identifier.
        project_id: Owning project.
        prompt: The prompt text.
        title: Optional short label for the note list.
        provider: ``claude`` or ``cursor`` (optional until chosen).
        model: Model alias for the chosen provider.
        effort: Effort / thinking level when supported.
        fast_mode: Whether to use the fast variant (Cursor / some models).
        priority: Lower runs first.
        status: Lifecycle status.
        created_from: Origin device (web/desktop/mobile).
        error: Last error message when failed.
    """

    __tablename__ = "queue_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    effort: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    fast_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=QueueItemStatus.PENDING.value, nullable=False)
    created_from: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=func.now(), nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="queue_items")

    def __repr__(self) -> str:
        """String representation of the queue item."""
        return f"<QueueItem id={self.id} project={self.project_id} status={self.status}>"
