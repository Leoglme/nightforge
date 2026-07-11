"""
Run dispatcher — builds the full run payload from the DB and pushes it to the target agent.

Pushing the payload over the existing agent WebSocket avoids inventing a separate
agent-authenticated REST channel: the agent receives everything it needs (projects, local
paths on this machine, ordered pending prompts) in one message.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from enums.queue_item_status import QueueItemStatus
from models.project import Project
from models.project_machine_path import ProjectMachinePath
from models.run import Run
from models.run_message import RunMessage
from models.run_project import RunProject
from services.agent_hub import agent_hub

logger = logging.getLogger(__name__)


def build_run_payload(db: Session, run: Run) -> dict:
    """
    Build the JSON payload describing a run for its target machine's agent.

    Args:
        db: Database session.
        run: The run to describe.

    Returns:
        A JSON-serializable payload with projects, local paths and pending prompts.
    """
    run_projects = (
        db.query(RunProject)
        .filter(RunProject.run_id == run.id)
        .order_by(RunProject.order_index.asc())
        .all()
    )

    projects_payload = []
    for run_project in run_projects:
        project: Optional[Project] = db.get(Project, run_project.project_id)
        if project is None:
            continue

        path: Optional[ProjectMachinePath] = (
            db.query(ProjectMachinePath)
            .filter(
                ProjectMachinePath.project_id == project.id,
                ProjectMachinePath.machine_id == run.machine_id,
            )
            .first()
        )

        messages = (
            db.query(RunMessage)
            .filter(
                RunMessage.run_id == run.id,
                RunMessage.project_id == project.id,
                RunMessage.status.in_(
                    [QueueItemStatus.PENDING.value, QueueItemStatus.RUNNING.value, QueueItemStatus.FAILED.value]
                ),
            )
            .order_by(RunMessage.order_index.asc())
            .all()
        )

        projects_payload.append(
            {
                "id": project.id,
                "name": project.name,
                "github_repo": project.github_repo,
                "base_branch": project.base_branch,
                "local_path": path.local_path if path else None,
                "messages": [
                    {
                        "id": message.id,
                        "content": message.content,
                        "claude_session_id": message.claude_session_id,
                        "claude_model": message.claude_model,
                    }
                    for message in messages
                ],
            }
        )

    return {
        "type": "run.payload",
        "run": {
            "id": run.id,
            "parallel": run.parallel,
            "quota_count": run.quota_count,
            "window_end": run.window_end.isoformat() if run.window_end else None,
            "projects": projects_payload,
        },
    }


async def dispatch_run(db: Session, run: Run) -> bool:
    """
    Send a run's payload to its target agent if it is online.

    Args:
        db: Database session.
        run: The run to dispatch.

    Returns:
        True if the agent was online and the payload was sent.
    """
    payload = build_run_payload(db, run)
    sent = await agent_hub.send_to_agent(run.machine_id, payload)
    if sent:
        logger.info("Dispatched run %s to machine %s", run.id, run.machine_id)
    else:
        logger.info("Run %s queued: machine %s offline", run.id, run.machine_id)
    return sent


async def push_run_update(db: Session, run: Run) -> bool:
    """
    Push an incremental run update (quota budget, retried messages) to the agent.

    Args:
        db: Database session.
        run: The run to refresh on the agent.

    Returns:
        True if delivered to a connected agent.
    """
    payload = build_run_payload(db, run)
    update = {
        "type": "run.update",
        "run": payload["run"],
    }
    sent = await agent_hub.send_to_agent(run.machine_id, update)
    if sent:
        logger.info("Pushed run update %s to machine %s", run.id, run.machine_id)
    return sent
