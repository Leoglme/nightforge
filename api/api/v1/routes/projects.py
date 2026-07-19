"""
Project routes — CRUD for projects (GitHub repo + queue).
"""
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from enums.queue_item_status import QueueItemStatus
from models.machine import Machine
from models.project import Project
from models.project_machine_path import ProjectMachinePath
from models.queue_item import QueueItem
from models.user import User
from schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate, _slugify_name
from schemas.project_path import ProjectPathResponse, ProjectPathSet
from services.auth_service import get_current_active_user
from services.project_cleanup import delete_project_cascade

router = APIRouter(prefix="/projects", tags=["projects"])


def _to_response(db: Session, project: Project) -> ProjectResponse:
    """
    Build a project response including its pending-prompt count.

    Args:
        db: Database session.
        project: The project.

    Returns:
        The project response.
    """
    pending = (
        db.query(QueueItem)
        .filter(
            QueueItem.project_id == project.id,
            QueueItem.status == QueueItemStatus.PENDING.value,
        )
        .count()
    )
    response = ProjectResponse.model_validate(project)
    response.pending_count = pending
    return response


@router.get("", response_model=List[ProjectResponse])
async def list_projects(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
) -> Any:
    """
    List the current user's projects.

    Args:
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The user's projects.
    """
    projects = db.query(Project).filter(Project.user_id == current_user.id).all()
    return [_to_response(db, p) for p in projects]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Create a project.

    Args:
        payload: Project creation data.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The created project.
    """
    repo = payload.github_repo or f"local/{_slugify_name(payload.name)}"
    project = Project(
        user_id=current_user.id,
        name=payload.name,
        github_repo=repo,
        base_branch=payload.base_branch,
        push_to_main=payload.push_to_main,
        allow_push=payload.allow_push,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return _to_response(db, project)


def _get_owned_project(db: Session, project_id: int, user: User) -> Project:
    """
    Fetch a project owned by the user or raise 404.

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


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    payload: ProjectUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Update a project.

    Args:
        project_id: The project id.
        payload: Fields to update.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The updated project.
    """
    project = _get_owned_project(db, project_id, current_user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return _to_response(db, project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """
    Detach a project from NightForge (delete all related app data).

    Args:
        project_id: The project id.
        current_user: The authenticated user.
        db: Database session.
    """
    project = _get_owned_project(db, project_id, current_user)
    delete_project_cascade(db, project)
    db.commit()


@router.get("/{project_id}/paths", response_model=List[ProjectPathResponse])
async def list_paths(
    project_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    List the local clone paths of a project across machines.

    Args:
        project_id: The project id.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The project's machine paths.
    """
    _get_owned_project(db, project_id, current_user)
    return db.query(ProjectMachinePath).filter(ProjectMachinePath.project_id == project_id).all()


@router.put("/{project_id}/paths", response_model=ProjectPathResponse)
async def set_path(
    project_id: int,
    payload: ProjectPathSet,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Set (or update) a project's local clone path on a machine.

    Args:
        project_id: The project id.
        payload: The machine id and local path.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The upserted machine path.

    Raises:
        HTTPException: If the project or machine is not owned by the user.
    """
    _get_owned_project(db, project_id, current_user)
    machine = (
        db.query(Machine)
        .filter(Machine.id == payload.machine_id, Machine.user_id == current_user.id)
        .first()
    )
    if not machine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")

    path = (
        db.query(ProjectMachinePath)
        .filter(
            ProjectMachinePath.project_id == project_id,
            ProjectMachinePath.machine_id == payload.machine_id,
        )
        .first()
    )
    if path:
        path.local_path = payload.local_path
    else:
        path = ProjectMachinePath(
            project_id=project_id,
            machine_id=payload.machine_id,
            local_path=payload.local_path,
        )
        db.add(path)
    db.commit()
    db.refresh(path)
    return path
