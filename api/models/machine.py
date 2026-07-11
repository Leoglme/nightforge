"""
Machine model — a PC running the NightForge agent.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base
from enums.machine_status import MachineStatus

if TYPE_CHECKING:
    from models.user import User
    from models.project_machine_path import ProjectMachinePath


class Machine(Base):
    """
    A machine (PC) running the agent, connected to the control-plane.

    Attributes:
        id: Unique identifier.
        user_id: Owner.
        name: Human name ("Fixe", "Portable").
        agent_token_hash: Hashed token used by the agent to authenticate.
        status: Current runtime status.
        online: Whether an agent connection is currently active.
        last_seen_at: Last heartbeat timestamp.
        claude_version: Detected Claude Code CLI version.
        agent_version: Running agent version.
    """

    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    agent_token_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default=MachineStatus.OFFLINE.value, nullable=False)
    online: Mapped[bool] = mapped_column(default=False, nullable=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    claude_version: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    agent_version: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="machines")
    project_paths: Mapped[list["ProjectMachinePath"]] = relationship(
        "ProjectMachinePath", back_populates="machine", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        """String representation of the machine."""
        return f"<Machine id={self.id} name={self.name} status={self.status}>"
