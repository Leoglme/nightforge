"""
Run dispatcher — builds the full run payload from the DB and pushes it to the target agent.

Pushing the payload over the existing agent WebSocket avoids inventing a separate
agent-authenticated REST channel: the agent receives everything it needs (projects, local
paths on this machine, ordered pending prompts) in one message.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from enums.queue_item_status import QueueItemStatus
from models.claude_account import ClaudeAccount
from models.cursor_account import CursorAccount
from models.project import Project
from models.project_machine_path import ProjectMachinePath
from models.run import Run
from models.run_message import RunMessage
from models.run_project import RunProject
from services.agent_hub import agent_hub
from services.claude_usage_service import pick_best_claude_account
from services.cursor_usage_service import pick_best_account
from services.encryption_service import encryption_service

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
                "push_to_main": bool(getattr(project, "push_to_main", True)),
                "local_path": path.local_path if path else None,
                "messages": [
                    {
                        "id": message.id,
                        "content": message.content,
                        "claude_session_id": message.claude_session_id,
                        "claude_model": message.claude_model,
                        "provider": message.provider or "claude",
                        "effort": message.effort,
                        "fast_mode": bool(message.fast_mode),
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
            "quota_wait_until": _quota_wait_until(run),
            "projects": projects_payload,
            "cursor_accounts": _cursor_accounts_payload(db, run.user_id),
            "claude_accounts": _claude_accounts_payload(db, run.user_id),
        },
    }


def _cursor_accounts_payload(db: Session, user_id: int) -> list[dict]:
    """
    Decrypt active Cursor vault accounts for the agent (per-prompt auth switch).

    Args:
        db: Database session.
        user_id: Run owner.

    Returns:
        List of account dicts with optional api_key / session_token.
    """
    accounts = (
        db.query(CursorAccount)
        .filter(CursorAccount.user_id == user_id, CursorAccount.is_active.is_(True))
        .order_by(CursorAccount.created_at.asc())
        .all()
    )
    out: list[dict] = []
    for account in accounts:
        session_token = None
        api_key = None
        if account.session_token_encrypted:
            try:
                session_token = encryption_service.decrypt(account.session_token_encrypted)
            except ValueError:
                session_token = None
        if account.api_key_encrypted:
            try:
                api_key = encryption_service.decrypt(account.api_key_encrypted)
            except ValueError:
                api_key = None
        if not session_token and not api_key:
            continue
        out.append(
            {
                "id": account.id,
                "label": account.label,
                "email": account.email,
                "session_token": session_token,
                "api_key": api_key,
                "auto_utilization": account.auto_utilization,
                "api_utilization": account.api_utilization,
            }
        )

    # Annotate which account the planner would pick first.
    best = pick_best_account(
        [(a["id"], a.get("auto_utilization"), a.get("api_utilization")) for a in out]
    )
    for entry in out:
        entry["preferred"] = entry["id"] == best
    return out


def _claude_accounts_payload(db: Session, user_id: int) -> list[dict]:
    """
    Decrypt active Claude vault accounts for the agent (per-prompt auth switch).

    Args:
        db: Database session.
        user_id: Run owner.

    Returns:
        List of account dicts with the decrypted OAuth access token.
    """
    accounts = (
        db.query(ClaudeAccount)
        .filter(ClaudeAccount.user_id == user_id, ClaudeAccount.is_active.is_(True))
        .order_by(ClaudeAccount.created_at.asc())
        .all()
    )
    out: list[dict] = []
    for account in accounts:
        access_token = None
        refresh_token = None
        expires_at = None
        if account.oauth_encrypted:
            try:
                raw = encryption_service.decrypt(account.oauth_encrypted)
                oauth = json.loads(raw)
            except (ValueError, json.JSONDecodeError):
                oauth = None
            if isinstance(oauth, dict):
                access_token = oauth.get("accessToken")
                refresh_token = oauth.get("refreshToken")
                expires_at = oauth.get("expiresAt")
        if not access_token:
            continue
        out.append(
            {
                "id": account.id,
                "label": account.label,
                "email": account.email,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": expires_at,
                "five_hour_utilization": account.five_hour_utilization,
                "seven_day_utilization": account.seven_day_utilization,
                "seven_day_opus_utilization": account.seven_day_opus_utilization,
            }
        )

    # Annotate which account the planner would pick first.
    best = pick_best_claude_account(
        [
            (a["id"], a.get("five_hour_utilization"), a.get("seven_day_utilization"))
            for a in out
        ]
    )
    for entry in out:
        entry["preferred"] = entry["id"] == best
    return out


def _quota_wait_until(run: Run) -> Optional[str]:
    """
    First quota window start from the planned timeline, when the run was created.

    The agent waits until this instant before the first Claude prompt when it is still
  in the future (e.g. bucket saturated, reset at 18:00).

    Args:
        run: The run whose planned timeline was computed at creation time.

    Returns:
        ISO timestamp string, or None.
    """
    timeline = run.planned_timeline
    if not isinstance(timeline, dict):
        return None
    windows = timeline.get("windows") or []
    if not windows:
        return None
    starts_at = windows[0].get("starts_at")
    return str(starts_at) if starts_at else None


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
