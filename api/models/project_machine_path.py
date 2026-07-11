"""
Local clone path of a project on a given machine.
"""
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from models.project import Project
    from models.machine import Machine


class ProjectMachinePath(Base):
    """
    Where a project's repo is cloned on a specific machine.

    Attributes:
        id: Unique identifier.
        project_id: The project.
        machine_id: The machine.
        local_path: Absolute path of the clone on that machine (agent fills it if empty).
    """

    __tablename__ = "project_machine_paths"
    __table_args__ = (UniqueConstraint("project_id", "machine_id", name="uq_project_machine"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), nullable=False, index=True)
    local_path: Mapped[str] = mapped_column(String(600), nullable=False)

    project: Mapped["Project"] = relationship("Project", back_populates="machine_paths")
    machine: Mapped["Machine"] = relationship("Machine", back_populates="project_paths")
