"""
Run event / log line reported by the agent.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base

if TYPE_CHECKING:
    from models.run import Run


class RunEvent(Base):
    """
    A single log/event line streamed by the agent for a run.

    Attributes:
        id: Unique identifier.
        run_id: The run.
        level: Log level (info/warning/error).
        message: Log message.
        queue_item_id: Related queue item, if any.
        created_at: Timestamp.
    """

    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    queue_item_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    run: Mapped["Run"] = relationship("Run", back_populates="events")
