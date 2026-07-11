"""
Delete a machine and all rows that reference it (explicit FK order).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from models.machine import Machine
from models.project_machine_path import ProjectMachinePath
from models.quota_snapshot import QuotaSnapshot
from models.run import Run
from models.run_event import RunEvent
from models.run_message import RunMessage
from models.run_project import RunProject


def delete_machine_cascade(db: Session, machine: Machine) -> None:
    """
    Remove a machine and every dependent row.

    Args:
        db: Database session.
        machine: Machine row to delete (still attached to the session).
    """
    machine_id = machine.id
    run_ids = [row.id for row in db.query(Run.id).filter(Run.machine_id == machine_id).all()]

    if run_ids:
        db.query(RunMessage).filter(RunMessage.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(RunEvent).filter(RunEvent.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(RunProject).filter(RunProject.run_id.in_(run_ids)).delete(synchronize_session=False)
        db.query(Run).filter(Run.id.in_(run_ids)).delete(synchronize_session=False)

    db.query(QuotaSnapshot).filter(QuotaSnapshot.machine_id == machine_id).delete(
        synchronize_session=False
    )
    db.query(ProjectMachinePath).filter(ProjectMachinePath.machine_id == machine_id).delete(
        synchronize_session=False
    )
    db.delete(machine)
