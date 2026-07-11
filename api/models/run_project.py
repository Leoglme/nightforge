"""
Association between a run and the projects it works on.
"""
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from models.run import Run


class RunProject(Base):
    """
    Links a run to a selected project (many-to-many with ordering).

    Attributes:
        id: Unique identifier.
        run_id: The run.
        project_id: The selected project.
        order_index: Sequential order when not running in parallel.
    """

    __tablename__ = "run_projects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    run: Mapped["Run"] = relationship("Run", back_populates="run_projects")
