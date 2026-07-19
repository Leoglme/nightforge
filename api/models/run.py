"""
Run model — a scheduled night working session on a machine.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base
from enums.run_status import RunStatus
from enums.run_kind import RunKind

if TYPE_CHECKING:
    from models.user import User
    from models.run_project import RunProject
    from models.run_event import RunEvent
    from models.run_message import RunMessage


class Run(Base):
    """
    A scheduled autonomous working session on a given machine.

    Attributes:
        id: Unique identifier.
        user_id: Owner.
        machine_id: Target machine.
        status: Lifecycle status.
        kind: ``night`` (Composer) or ``quick`` (file d'attente à la volée).
        quota_count: Number of 5-hour quotas the user allowed to burn.
        parallel: Whether selected projects run in parallel (else sequential).
        planned_timeline: Estimated per-quota start/reset timeline (JSON).
        started_at: When the run actually started.
        window_end: Hard stop time (end of allowed window), if any.
        finished_at: When it ended.
    """

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default=RunStatus.SCHEDULED.value, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default=RunKind.NIGHT.value, nullable=False)
    quota_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    parallel: Mapped[bool] = mapped_column(default=False, nullable=False)
    planned_timeline: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    window_end: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="runs")
    run_projects: Mapped[list["RunProject"]] = relationship(
        "RunProject", back_populates="run", cascade="all, delete-orphan"
    )
    events: Mapped[list["RunEvent"]] = relationship(
        "RunEvent", back_populates="run", cascade="all, delete-orphan"
    )
    messages: Mapped[list["RunMessage"]] = relationship(
        "RunMessage", back_populates="run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation of the run."""
        return f"<Run id={self.id} machine={self.machine_id} status={self.status}>"
