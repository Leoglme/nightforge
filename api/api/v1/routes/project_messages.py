"""
Project message routes — the chat composer's persistent night-message drafts.

These are the ordered messages the user assembles in advance (from the prompt queue and/or
free text) and that will be sent to Claude Code, one at a time, during a night run.
"""
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from models.project import Project
from models.project_message import ProjectMessage
from models.user import User
from schemas.project_message import (
    ProjectMessageCreate,
    ProjectMessageReorder,
    ProjectMessageResponse,
    ProjectMessageUpdate,
)
from services.auth_service import get_current_active_user

router = APIRouter(prefix="/projects/{project_id}/messages", tags=["messages"])


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
        db.query(Project).filter(Project.id == project_id, Project.user_id == user.id).first()
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _get_message(db: Session, project_id: int, message_id: int) -> ProjectMessage:
    """
    Fetch a message belonging to a project.

    Args:
        db: Database session.
        project_id: The project id.
        message_id: The message id.

    Returns:
        The message.

    Raises:
        HTTPException: If not found.
    """
    message = (
        db.query(ProjectMessage)
        .filter(ProjectMessage.id == message_id, ProjectMessage.project_id == project_id)
        .first()
    )
    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return message


@router.get("", response_model=List[ProjectMessageResponse])
async def list_messages(
    project_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    List a project's night-message drafts in order.

    Args:
        project_id: The project id.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The ordered message drafts.
    """
    _assert_owns_project(db, project_id, current_user)
    return (
        db.query(ProjectMessage)
        .filter(ProjectMessage.project_id == project_id)
        .order_by(ProjectMessage.order_index.asc(), ProjectMessage.id.asc())
        .all()
    )


@router.post("", response_model=ProjectMessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(
    project_id: int,
    payload: ProjectMessageCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Append a night-message draft to a project's sequence.

    Args:
        project_id: The project id.
        payload: The message content and optional source queue items.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The created message draft.
    """
    _assert_owns_project(db, project_id, current_user)
    next_index = (
        db.query(ProjectMessage)
        .filter(ProjectMessage.project_id == project_id)
        .count()
    )
    message = ProjectMessage(
        project_id=project_id,
        order_index=next_index,
        content=payload.content,
        claude_session_id=payload.claude_session_id,
        claude_model=payload.claude_model,
        provider=payload.provider,
        effort=payload.effort,
        fast_mode=payload.fast_mode,
        source_item_ids=payload.source_item_ids,
        created_from=payload.created_from,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.patch("/{message_id}", response_model=ProjectMessageResponse)
async def update_message(
    project_id: int,
    message_id: int,
    payload: ProjectMessageUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Edit a night-message draft.

    Args:
        project_id: The project id.
        message_id: The message id.
        payload: Fields to update.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The updated message draft.
    """
    _assert_owns_project(db, project_id, current_user)
    message = _get_message(db, project_id, message_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(message, field, value)
    db.commit()
    db.refresh(message)
    return message


@router.post("/reorder", response_model=List[ProjectMessageResponse])
async def reorder_messages(
    project_id: int,
    payload: ProjectMessageReorder,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Reorder a project's night-message drafts.

    Args:
        project_id: The project id.
        payload: The message ids in the desired order.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The reordered message drafts.
    """
    _assert_owns_project(db, project_id, current_user)
    messages = {
        m.id: m
        for m in db.query(ProjectMessage).filter(ProjectMessage.project_id == project_id).all()
    }
    for index, message_id in enumerate(payload.ordered_ids):
        message = messages.get(message_id)
        if message:
            message.order_index = index
    db.commit()
    return (
        db.query(ProjectMessage)
        .filter(ProjectMessage.project_id == project_id)
        .order_by(ProjectMessage.order_index.asc(), ProjectMessage.id.asc())
        .all()
    )


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    project_id: int,
    message_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """
    Delete a night-message draft.

    Args:
        project_id: The project id.
        message_id: The message id.
        current_user: The authenticated user.
        db: Database session.
    """
    _assert_owns_project(db, project_id, current_user)
    message = _get_message(db, project_id, message_id)
    db.delete(message)
    db.commit()