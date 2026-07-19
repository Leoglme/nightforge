"""
Run message model — the execution snapshot of a composed night message.

At launch, each selected project's :class:`ProjectMessage` drafts (or, as a fallback, its
pending queue items) are frozen into ``RunMessage`` rows. The agent executes them in order,
one Claude invocation per message, and reports their status back.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base
from enums.queue_item_status import QueueItemStatus

if TYPE_CHECKING:
    from models.run import Run


class RunMessage(Base):
    """
    A single message executed within a run, for a given project.

    Attributes:
        id: Unique identifier.
        run_id: Owning run.
        project_id: The project this message targets.
        order_index: Execution order within the project (lower runs first).
        content: The text sent to the provider CLI.
        claude_session_id: Optional session to resume (Claude).
        claude_model: Model alias for the chosen provider.
        provider: ``claude`` or ``cursor``.
        effort: Effort / thinking level when supported.
        fast_mode: Fast variant when supported.
        status: Lifecycle status (reuses the queue item status vocabulary).
        error: Last error message when failed.
    """

    __tablename__ = "run_messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    claude_session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    claude_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    effort: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    fast_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_item_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=QueueItemStatus.PENDING.value, nullable=False
    )
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    run: Mapped["Run"] = relationship("Run", back_populates="messages")

    def __repr__(self) -> str:
        """String representation of the run message."""
        return f"<RunMessage id={self.id} run={self.run_id} status={self.status}>"
