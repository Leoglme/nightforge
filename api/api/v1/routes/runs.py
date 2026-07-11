"""
Run routes — schedule / stop night runs and read their events.
"""
from datetime import datetime
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from enums.queue_item_status import QueueItemStatus
from enums.run_status import RunStatus
from enums.quota_bucket import QuotaBucket
from models.machine import Machine
from models.project import Project
from models.project_machine_path import ProjectMachinePath
from models.quota_snapshot import QuotaSnapshot
from models.project_message import ProjectMessage
from models.queue_item import QueueItem
from models.run import Run
from models.run_event import RunEvent
from models.run_message import RunMessage
from models.run_project import RunProject
from models.user import User
from schemas.quota import QuotaPlanRequest
from schemas.run import RunAddQuotas, RunCreate, RunEventResponse, RunResponse
from schemas.run_message import RunMessageCreate, RunMessageResponse, RunMessageRetry, RunProjectSummary
from services.agent_hub import agent_hub
from services.auth_service import get_current_active_user
from services.quota_planner import anchor_reset_at_from_snapshot, build_plan
from services.run_dispatcher import dispatch_run, push_run_update

router = APIRouter(prefix="/runs", tags=["runs"])


def _machine_quota_anchor(db: Session, machine_id: int) -> tuple[datetime | None, float | None]:
    """
    Latest real five-hour bucket reading for a machine, if reported by its agent.

    Args:
        db: Database session.
        machine_id: Target machine.

    Returns:
        Tuple of (timezone-aware UTC reset time, utilization), either may be None.
    """
    snapshot = (
        db.query(QuotaSnapshot)
        .filter(
            QuotaSnapshot.machine_id == machine_id,
            QuotaSnapshot.bucket == QuotaBucket.FIVE_HOUR.value,
        )
        .order_by(QuotaSnapshot.created_at.desc())
        .first()
    )
    if snapshot is None:
        return None, None
    reset_at = (
        anchor_reset_at_from_snapshot(snapshot.resets_at) if snapshot.resets_at else None
    )
    return reset_at, snapshot.utilization


def _snapshot_project_messages_with_sessions(db: Session, run_id: int, project_id: int) -> None:
    """
    Freeze composed drafts into run messages, preserving Claude session ids when set.

    Args:
        db: Database session.
        run_id: The run to attach messages to.
        project_id: The project being snapshotted.
    """
    drafts = (
        db.query(ProjectMessage)
        .filter(ProjectMessage.project_id == project_id)
        .order_by(ProjectMessage.order_index.asc(), ProjectMessage.id.asc())
        .all()
    )
    if drafts:
        for draft in drafts:
            db.add(
                RunMessage(
                    run_id=run_id,
                    project_id=project_id,
                    order_index=draft.order_index,
                    content=draft.content,
                    claude_session_id=draft.claude_session_id,
                    claude_model=draft.claude_model,
                )
            )
        return

    items = (
        db.query(QueueItem)
        .filter(
            QueueItem.project_id == project_id,
            QueueItem.status == QueueItemStatus.PENDING.value,
        )
        .order_by(QueueItem.priority.asc(), QueueItem.created_at.asc())
        .all()
    )
    for index, item in enumerate(items):
        db.add(
            RunMessage(
                run_id=run_id,
                project_id=project_id,
                order_index=index,
                content=item.prompt,
            )
        )


def _rebuild_planned_timeline(db: Session, run: Run) -> None:
    """Recalculate and persist the quota plan after the budget changes."""
    anchor_reset_at, anchor_utilization = _machine_quota_anchor(db, run.machine_id)
    plan = build_plan(
        QuotaPlanRequest(
            quota_count=run.quota_count,
            start_at=run.started_at or run.scheduled_at,
            wake_at=run.window_end,
            machine_id=run.machine_id,
        ),
        anchor_reset_at=anchor_reset_at,
        anchor_utilization=anchor_utilization,
    )
    run.planned_timeline = plan.model_dump(mode="json")


DEFAULT_CONTINUE_PROMPT = "Vas-y, continue là où tu t'étais arrêté."


ACTIVE_RUN_STATUSES = {
    RunStatus.SCHEDULED.value,
    RunStatus.RUNNING.value,
    RunStatus.WAITING_QUOTA.value,
}


@router.get("", response_model=List[RunResponse])
async def list_runs(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
) -> Any:
    """
    List the current user's runs (most recent first).

    Args:
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The user's runs.
    """
    return (
        db.query(Run)
        .filter(Run.user_id == current_user.id)
        .order_by(Run.created_at.desc())
        .all()
    )


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: RunCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Schedule a night run on a machine for one or more projects.

    Args:
        payload: Run creation data.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The scheduled run, with its planned quota timeline.

    Raises:
        HTTPException: If the machine or a project is not owned by the user.
    """
    machine = (
        db.query(Machine)
        .filter(Machine.id == payload.machine_id, Machine.user_id == current_user.id)
        .first()
    )
    if not machine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")

    projects = (
        db.query(Project)
        .filter(Project.id.in_(payload.project_ids), Project.user_id == current_user.id)
        .all()
    )
    if len(projects) != len(set(payload.project_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown project(s)")

    anchor_reset_at, anchor_utilization = _machine_quota_anchor(db, payload.machine_id)
    plan = build_plan(
        QuotaPlanRequest(
            quota_count=payload.quota_count,
            start_at=payload.scheduled_at,
            wake_at=payload.window_end,
            machine_id=payload.machine_id,
        ),
        anchor_reset_at=anchor_reset_at,
        anchor_utilization=anchor_utilization,
    )

    run = Run(
        user_id=current_user.id,
        machine_id=payload.machine_id,
        status=RunStatus.SCHEDULED.value,
        quota_count=payload.quota_count,
        parallel=payload.parallel,
        planned_timeline=plan.model_dump(mode="json"),
        scheduled_at=payload.scheduled_at,
        window_end=payload.window_end,
    )
    db.add(run)
    db.flush()

    for index, project_id in enumerate(payload.project_ids):
        db.add(RunProject(run_id=run.id, project_id=project_id, order_index=index))
        _snapshot_project_messages_with_sessions(db, run.id, project_id)

    db.commit()
    db.refresh(run)

    # Dispatch now if it should start immediately and the agent is online. Otherwise it
    # stays SCHEDULED and is dispatched when the agent (re)connects.
    scheduled = payload.scheduled_at
    if scheduled is None:
        should_start_now = True
    else:
        now = datetime.now(scheduled.tzinfo) if scheduled.tzinfo else datetime.utcnow()
        should_start_now = scheduled <= now
    if should_start_now:
        await dispatch_run(db, run)
    return run


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Get a single run.

    Args:
        run_id: The run id.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The run.

    Raises:
        HTTPException: If the run is not found.
    """
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == current_user.id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.post("/{run_id}/stop", response_model=RunResponse)
async def stop_run(
    run_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Stop a run (kill switch).

    Args:
        run_id: The run id.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The updated run.

    Raises:
        HTTPException: If the run is not found.
    """
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == current_user.id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    run.status = RunStatus.STOPPED.value
    run.finished_at = datetime.utcnow()
    db.commit()
    db.refresh(run)
    await agent_hub.send_to_agent(run.machine_id, {"type": "run.stop", "run_id": run.id})
    return run


@router.get("/{run_id}/messages", response_model=List[RunMessageResponse])
async def list_run_messages(
    run_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    List the executed/pending messages of a run (its frozen night sequence).

    Args:
        run_id: The run id.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The run's messages, ordered by project then execution order.

    Raises:
        HTTPException: If the run is not found.
    """
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == current_user.id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return (
        db.query(RunMessage)
        .filter(RunMessage.run_id == run_id)
        .order_by(RunMessage.project_id.asc(), RunMessage.order_index.asc())
        .all()
    )


@router.get("/{run_id}/projects", response_model=List[RunProjectSummary])
async def list_run_projects(
    run_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    List projects attached to a run.

    Args:
        run_id: The run id.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        Projects in execution order.

    Raises:
        HTTPException: If the run is not found.
    """
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == current_user.id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    rows = (
        db.query(RunProject, Project)
        .join(Project, Project.id == RunProject.project_id)
        .filter(RunProject.run_id == run_id)
        .order_by(RunProject.order_index.asc())
        .all()
    )
    return [
        RunProjectSummary(
            project_id=project.id,
            name=project.name,
            order_index=run_project.order_index,
            local_path=(
                db.query(ProjectMachinePath.local_path)
                .filter(
                    ProjectMachinePath.project_id == project.id,
                    ProjectMachinePath.machine_id == run.machine_id,
                )
                .scalar()
            ),
        )
        for run_project, project in rows
    ]


@router.post("/{run_id}/messages", response_model=RunMessageResponse, status_code=status.HTTP_201_CREATED)
async def add_run_message(
    run_id: int,
    payload: RunMessageCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Append a message to a run's sequence while it is active (or restart a finished run).

    Args:
        run_id: The run id.
        payload: Message content and target project.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The created run message.

    Raises:
        HTTPException: If the run or project is invalid.
    """
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == current_user.id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    linked = (
        db.query(RunProject)
        .filter(RunProject.run_id == run_id, RunProject.project_id == payload.project_id)
        .first()
    )
    if not linked:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project not in this run")

    last_index = (
        db.query(RunMessage.order_index)
        .filter(RunMessage.run_id == run_id, RunMessage.project_id == payload.project_id)
        .order_by(RunMessage.order_index.desc())
        .limit(1)
        .scalar()
    )
    next_index = 0 if last_index is None else int(last_index) + 1

    message = RunMessage(
        run_id=run_id,
        project_id=payload.project_id,
        order_index=next_index,
        content=payload.content.strip(),
        claude_session_id=payload.claude_session_id,
        claude_model=payload.claude_model,
        status=QueueItemStatus.PENDING.value,
    )
    db.add(message)

    if run.status in (RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.STOPPED.value):
        run.status = RunStatus.RUNNING.value
        run.finished_at = None

    db.commit()
    db.refresh(message)

    if run.status in ACTIVE_RUN_STATUSES:
        await push_run_update(db, run)
    else:
        await dispatch_run(db, run)

    return message


@router.get("/{run_id}/events", response_model=List[RunEventResponse])
async def list_run_events(
    run_id: int,
    after_id: int = 0,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    List the log/events of a run, optionally only those newer than ``after_id``.

    Args:
        run_id: The run id.
        after_id: Only return events with an id strictly greater than this (for live polling).
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The run's events (oldest first).

    Raises:
        HTTPException: If the run is not found.
    """
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == current_user.id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return (
        db.query(RunEvent)
        .filter(RunEvent.run_id == run_id, RunEvent.id > after_id)
        .order_by(RunEvent.id.asc())
        .all()
    )


@router.post("/{run_id}/messages/{message_id}/retry", response_model=RunMessageResponse)
async def retry_run_message(
    run_id: int,
    message_id: int,
    payload: RunMessageRetry,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Re-queue a run message for execution (optionally with a continue prompt).

    Args:
        run_id: The run id.
        message_id: The message to retry.
        payload: Optional new content / session id.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The updated message.
    """
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == current_user.id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    message = (
        db.query(RunMessage)
        .filter(RunMessage.id == message_id, RunMessage.run_id == run_id)
        .first()
    )
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    if payload.content is not None:
        message.content = payload.content.strip() or message.content
    elif message.claude_session_id:
        message.content = DEFAULT_CONTINUE_PROMPT
    if payload.claude_session_id is not None:
        message.claude_session_id = payload.claude_session_id
    if payload.claude_model is not None:
        message.claude_model = payload.claude_model or None
    message.status = QueueItemStatus.PENDING.value
    message.error = None

    if run.status in (RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.STOPPED.value):
        run.status = RunStatus.RUNNING.value
        run.finished_at = None

    db.commit()
    db.refresh(message)

    if run.status in ACTIVE_RUN_STATUSES:
        await push_run_update(db, run)
    else:
        await dispatch_run(db, run)

    return message


@router.post("/{run_id}/quotas", response_model=RunResponse)
async def add_run_quotas(
    run_id: int,
    payload: RunAddQuotas,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Extend the quota budget of an active run without stopping it.

    Args:
        run_id: The run id.
        payload: How many quotas to add.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The updated run with a refreshed timeline.
    """
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == current_user.id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    if run.status not in ACTIVE_RUN_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only active runs can receive extra quotas",
        )

    run.quota_count = min(10, run.quota_count + payload.add)
    _rebuild_planned_timeline(db, run)
    db.commit()
    db.refresh(run)

    await push_run_update(db, run)
    return run
