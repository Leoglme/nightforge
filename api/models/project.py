"""
Project model — a GitHub repository with its own prompt queue.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base

if TYPE_CHECKING:
    from models.user import User
    from models.queue_item import QueueItem
    from models.project_machine_path import ProjectMachinePath
    from models.project_message import ProjectMessage


class Project(Base):
    """
    A project the agent can work on — one GitHub repo + a prompt queue.

    Attributes:
        id: Unique identifier.
        user_id: Owner.
        name: Display name.
        github_repo: Repo reference (owner/name or full URL).
        base_branch: Branch the night branch is created from.
        created_at: Creation timestamp.
    """

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    github_repo: Mapped[str] = mapped_column(String(400), nullable=False)
    base_branch: Mapped[str] = mapped_column(String(120), default="main", nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=func.now(), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="projects")
    queue_items: Mapped[list["QueueItem"]] = relationship(
        "QueueItem", back_populates="project", cascade="all, delete-orphan"
    )
    machine_paths: Mapped[list["ProjectMachinePath"]] = relationship(
        "ProjectMachinePath", back_populates="project", cascade="all, delete-orphan"
    )
    messages: Mapped[list["ProjectMessage"]] = relationship(
        "ProjectMessage", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation of the project."""
        return f"<Project id={self.id} name={self.name} repo={self.github_repo}>"
