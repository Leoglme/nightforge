"""
Machine routes — register/list machines and issue agent tokens.
"""
import secrets
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from models.machine import Machine
from models.project import Project
from models.project_machine_path import ProjectMachinePath
from models.user import User
from schemas.claude_session import ClaudeSessionListResponse, ClaudeSessionResponse
from schemas.machine import MachineCreate, MachineCreated, MachineResponse
from schemas.repo_inspect import RepoInspectResponse
from services.agent_hub import agent_hub
from services.auth_service import get_current_active_user, get_password_hash
from services.machine_cleanup import delete_machine_cascade

router = APIRouter(prefix="/machines", tags=["machines"])


@router.get("", response_model=List[MachineResponse])
async def list_machines(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
) -> Any:
    """
    List the current user's machines with live online status.

    Args:
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The user's machines.
    """
    machines = db.query(Machine).filter(Machine.user_id == current_user.id).all()
    for m in machines:
        m.online = agent_hub.is_online(m.id)
    return machines


@router.post("", response_model=MachineCreated, status_code=status.HTTP_201_CREATED)
async def create_machine(
    payload: MachineCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Register a new machine and return its one-time agent token.

    Args:
        payload: Machine creation data.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The created machine including the plaintext agent token (shown once).
    """
    token = secrets.token_urlsafe(32)
    machine = Machine(
        user_id=current_user.id,
        name=payload.name,
        agent_token_hash=get_password_hash(token),
    )
    db.add(machine)
    db.commit()
    db.refresh(machine)

    return MachineCreated(**MachineResponse.model_validate(machine).model_dump(), agent_token=token)


@router.post("/{machine_id}/reissue-token", response_model=MachineCreated)
async def reissue_machine_token(
    machine_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Rotate the agent token for an existing machine (desktop re-provisioning).

    Args:
        machine_id: The machine id.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The machine with a fresh plaintext agent token (shown once).

    Raises:
        HTTPException: If the machine is not found.
    """
    machine = (
        db.query(Machine)
        .filter(Machine.id == machine_id, Machine.user_id == current_user.id)
        .first()
    )
    if not machine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")

    token = secrets.token_urlsafe(32)
    machine.agent_token_hash = get_password_hash(token)
    db.commit()
    db.refresh(machine)

    # Drop any live socket authenticated with the previous token so the desktop
    # sidecar reconnects with the new agent.json instead of staying "half online".
    await agent_hub.disconnect_agent(machine_id)

    return MachineCreated(**MachineResponse.model_validate(machine).model_dump(), agent_token=token)


@router.delete("/{machine_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_machine(
    machine_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """
    Delete a machine.

    Args:
        machine_id: The machine id.
        current_user: The authenticated user.
        db: Database session.

    Raises:
        HTTPException: If the machine is not found.
    """
    machine = (
        db.query(Machine)
        .filter(Machine.id == machine_id, Machine.user_id == current_user.id)
        .first()
    )
    if not machine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")

    await agent_hub.disconnect_agent(machine_id)
    delete_machine_cascade(db, machine)
    db.commit()


def _normalize_local_path(path: str) -> str:
    """
    Normalize a clone path for cross-OS comparison (slashes, trailing sep, case).

    Args:
        path: A local filesystem path from the agent PC.

    Returns:
        A comparable, normalized key.
    """
    return path.strip().replace("\\", "/").rstrip("/").lower()


@router.get("/{machine_id}/claude-sessions", response_model=ClaudeSessionListResponse)
async def list_claude_sessions(
    machine_id: int,
    local_path: Optional[str] = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    List resumable Claude Code sessions on a machine.

    Args:
        machine_id: Target machine (must be online).
        local_path: When set, scope to one project's clone; when omitted, list every
            session on the machine (Discussions hub) and resolve each to a project.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        Recent sessions sorted by last activity, each mapped to a project when known.

    Raises:
        HTTPException: If the machine is unknown or offline.
    """
    machine = (
        db.query(Machine)
        .filter(Machine.id == machine_id, Machine.user_id == current_user.id)
        .first()
    )
    if not machine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")

    if not agent_hub.is_online(machine_id):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Machine offline — sessions are only available on the agent PC",
        )

    response = await agent_hub.request_agent(
        machine_id,
        {"type": "sessions.list", "local_path": local_path},
    )
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Agent did not respond in time",
        )

    project_by_path: dict[str, tuple[int, str]] = {
        _normalize_local_path(path): (project_id, name)
        for path, project_id, name in (
            db.query(ProjectMachinePath.local_path, Project.id, Project.name)
            .join(Project, Project.id == ProjectMachinePath.project_id)
            .filter(
                ProjectMachinePath.machine_id == machine_id,
                Project.user_id == current_user.id,
            )
            .all()
        )
    }

    sessions = []
    for item in response.get("sessions", []):
        cwd = item.get("cwd")
        project = project_by_path.get(_normalize_local_path(cwd)) if cwd else None
        sessions.append(
            ClaudeSessionResponse(
                session_id=item["session_id"],
                title=item.get("title"),
                cwd=cwd,
                updated_at=item["updated_at"],
                project_id=project[0] if project else None,
                project_name=project[1] if project else None,
            )
        )
    return ClaudeSessionListResponse(sessions=sessions)


@router.get("/{machine_id}/inspect-repo", response_model=RepoInspectResponse)
async def inspect_repo(
    machine_id: int,
    local_path: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Inspect a local git clone on a machine (folder name, GitHub remote, base branch).

    Args:
        machine_id: Target machine (must be online).
        local_path: Absolute path of the clone on that PC.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        Detected repo metadata.

    Raises:
        HTTPException: If the machine is unknown or offline.
    """
    machine = (
        db.query(Machine)
        .filter(Machine.id == machine_id, Machine.user_id == current_user.id)
        .first()
    )
    if not machine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")

    if not agent_hub.is_online(machine_id):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Machine offline — inspection requires the agent PC",
        )

    response = await agent_hub.request_agent(
        machine_id,
        {"type": "repo.inspect", "local_path": local_path},
    )
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Agent did not respond in time",
        )

    return RepoInspectResponse(
        exists=bool(response.get("exists")),
        is_git=bool(response.get("is_git")),
        name=response.get("name"),
        github_repo=response.get("github_repo"),
        base_branch=response.get("base_branch"),
        error=response.get("error"),
    )
