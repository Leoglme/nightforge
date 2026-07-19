"""
Detach a project from NightForge by deleting all related app data (disk untouched).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from models.project import Project
from models.project_machine_path import ProjectMachinePath
from models.project_message import ProjectMessage
from models.queue_item import QueueItem
from models.run_message import RunMessage
from models.run_project import RunProject


def delete_project_cascade(db: Session, project: Project) -> None:
    """
    Remove a project and every NightForge row that references it.

    Does not touch the local git clone or the remote GitHub repository.

    Args:
        db: Database session.
        project: Project row to delete (still attached to the session).
    """
    project_id = project.id

    # Run history first (no ORM cascade from Project).
    db.query(RunMessage).filter(RunMessage.project_id == project_id).delete(synchronize_session=False)
    db.query(RunProject).filter(RunProject.project_id == project_id).delete(synchronize_session=False)

    # Composer drafts, queue notebook, machine paths.
    db.query(ProjectMessage).filter(ProjectMessage.project_id == project_id).delete(
        synchronize_session=False
    )
    db.query(QueueItem).filter(QueueItem.project_id == project_id).delete(synchronize_session=False)
    db.query(ProjectMachinePath).filter(ProjectMachinePath.project_id == project_id).delete(
        synchronize_session=False
    )

    db.delete(project)
