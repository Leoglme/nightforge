"""
Queue item model — a single prompt in a project's queue.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base
from enums.queue_item_status import QueueItemStatus

if TYPE_CHECKING:
    from models.project import Project


class QueueItem(Base):
    """
    A prompt queued for a project, executed one by one.

    Attributes:
        id: Unique identifier.
        project_id: Owning project.
        prompt: The prompt text sent to Claude Code.
        priority: Lower runs first.
        status: Lifecycle status.
        created_from: Origin device (web/desktop/mobile).
        error: Last error message when failed.
    """

    __tablename__ = "queue_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
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
