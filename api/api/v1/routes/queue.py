"""
Queue routes — manage the prompt queue of a project.
"""
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from enums.queue_item_status import QueueItemStatus
from models.project import Project
from models.queue_item import QueueItem
from models.user import User
from schemas.queue_item import QueueItemCreate, QueueItemResponse, QueueItemUpdate
from services.auth_service import get_current_active_user

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
        priority=payload.priority,
        created_from=payload.created_from,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


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
