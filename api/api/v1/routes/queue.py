"""
Queue routes — manage the prompt queue of a project.
"""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from enums.queue_item_status import QueueItemStatus
from models.machine import Machine
from models.project import Project
from models.queue_item import QueueItem
from models.user import User
from schemas.ideas import IdeasExpandRequest, IdeasExpandResponse
from schemas.queue_item import QueueItemCreate, QueueItemResponse, QueueItemUpdate
from services.agent_hub import agent_hub
from services.auth_service import get_current_active_user
from services.ideas_expander import (
    build_agent_prompt,
    drafts_from_agent_payload,
    heuristic_expand,
)

router = APIRouter(prefix="/projects/{project_id}/queue", tags=["queue"])


def _assert_owns_project(db: Session, project_id: int, user: User) -> Project:
    """
    Ensure the project exists and belongs to the user.

    Args:
        db: Database session.
        project_id: The project id.
        user: The owner.

    Returns:
        The project.

    Raises:
        HTTPException: If not found.
    """
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == user.id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.get("", response_model=List[QueueItemResponse])
async def list_queue(
    project_id: int,
    include_done: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    List a project's queue ordered by priority then creation.

    Args:
        project_id: The project id.
        include_done: When false (default), completed prompts are omitted.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The ordered queue items.
    """
    _assert_owns_project(db, project_id, current_user)
    query = db.query(QueueItem).filter(QueueItem.project_id == project_id)
    if not include_done:
        query = query.filter(QueueItem.status != QueueItemStatus.DONE.value)
    return query.order_by(QueueItem.priority.asc(), QueueItem.created_at.asc()).all()


@router.post("", response_model=QueueItemResponse, status_code=status.HTTP_201_CREATED)
async def add_queue_item(
    project_id: int,
    payload: QueueItemCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Add a prompt to a project's queue.

    Args:
        project_id: The project id.
        payload: The prompt to add.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The created queue item.
    """
    _assert_owns_project(db, project_id, current_user)
    item = QueueItem(
        project_id=project_id,
        prompt=payload.prompt,
        title=payload.title,
        provider=payload.provider,
        model=payload.model,
        effort=payload.effort,
        fast_mode=payload.fast_mode,
        priority=payload.priority,
        created_from=payload.created_from,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/expand", response_model=IdeasExpandResponse, status_code=status.HTTP_201_CREATED)
async def expand_ideas_to_queue(
    project_id: int,
    payload: IdeasExpandRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Expand free-form ideas into queue prompts and persist them.

    Prefers an online agent (Cursor Composer 2.5, then Claude Haiku). Falls back to
    a local heuristic inspired by the plan-de-session skill when no agent answers.

    Args:
        project_id: The project id.
        payload: Ideas text + optional machine.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        Created queue items and expansion metadata.
    """
    project = _assert_owns_project(db, project_id, current_user)

    summary: Optional[str] = None
    drafts = []
    source = "heuristic"
    provider_used: Optional[str] = None
    model_used: Optional[str] = None

    machine = _resolve_expand_machine(db, current_user.id, payload.machine_id)
    if machine is not None and agent_hub.is_online(machine.id):
        prefer = payload.prefer_provider or "cursor"
        response = await agent_hub.request_agent(
            machine.id,
            {
                "type": "ideas.expand",
                "ideas": payload.ideas,
                "project_name": project.name,
                "prompt": build_agent_prompt(
                    ideas=payload.ideas, project_name=project.name
                ),
                "prefer_provider": prefer,
            },
            timeout=180.0,
        )
        if response and not response.get("error"):
            summary, drafts = drafts_from_agent_payload(response)
            if drafts:
                source = "agent"
                provider_used = response.get("provider_used")
                model_used = response.get("model_used")

    if not drafts:
        summary, drafts = heuristic_expand(
            ideas=payload.ideas, project_name=project.name
        )
        source = "heuristic"
        provider_used = None
        model_used = None

    created: List[QueueItem] = []
    for draft in drafts:
        item = QueueItem(
            project_id=project_id,
            prompt=draft.prompt,
            title=draft.title,
            provider=draft.provider,
            model=draft.model,
            effort=draft.effort,
            fast_mode=draft.fast_mode,
            priority=100,
            created_from="ideas",
        )
        db.add(item)
        created.append(item)
    db.commit()
    for item in created:
        db.refresh(item)

    return IdeasExpandResponse(
        summary=summary,
        source=source,  # type: ignore[arg-type]
        provider_used=str(provider_used) if provider_used else None,
        model_used=str(model_used) if model_used else None,
        items=created,
    )


def _resolve_expand_machine(
    db: Session, user_id: int, machine_id: Optional[int]
) -> Optional[Machine]:
    """
    Pick a machine for agent-backed expansion.

    Args:
        db: Database session.
        user_id: Owner id.
        machine_id: Explicit machine, or None to pick any online one.

    Returns:
        A machine owned by the user, or None.
    """
    if machine_id is not None:
        machine = (
            db.query(Machine)
            .filter(Machine.id == machine_id, Machine.user_id == user_id)
            .first()
        )
        return machine

    return (
        db.query(Machine)
        .filter(Machine.user_id == user_id, Machine.online.is_(True))
        .order_by(Machine.last_seen_at.desc())
        .first()
    )


@router.patch("/{item_id}", response_model=QueueItemResponse)
async def update_queue_item(
    project_id: int,
    item_id: int,
    payload: QueueItemUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Edit a queued prompt.

    Args:
        project_id: The project id.
        item_id: The queue item id.
        payload: Fields to update.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The updated queue item.
    """
    _assert_owns_project(db, project_id, current_user)
    item = (
        db.query(QueueItem)
        .filter(QueueItem.id == item_id, QueueItem.project_id == project_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue item not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_queue_item(
    project_id: int,
    item_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """
    Remove a prompt from the queue.

    Args:
        project_id: The project id.
        item_id: The queue item id.
        current_user: The authenticated user.
        db: Database session.
    """
    _assert_owns_project(db, project_id, current_user)
    item = (
        db.query(QueueItem)
        .filter(QueueItem.id == item_id, QueueItem.project_id == project_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Queue item not found")
    db.delete(item)
    db.commit()
