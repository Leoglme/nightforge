"""
WebSocket routes — agent connections (outbound from each PC) and dashboard live feed.

Protocol (JSON messages):

Agent -> server:
  {"type": "hello", "agent_version": "...", "claude_version": "..."}
  {"type": "status", "status": "WORKING|IDLE|WAITING_QUOTA|ERROR"}
  {"type": "quota", "bucket": "five_hour", "utilization": 0.4, "resets_at": "ISO"}
  {"type": "event", "run_id": 1, "level": "info", "message": "...", "queue_item_id": 2}
  {"type": "run.status", "run_id": 1, "status": "RUNNING|COMPLETED|FAILED|STOPPED|WAITING_QUOTA"}
  {"type": "message.status", "message_id": 2, "status": "RUNNING|DONE|FAILED|SKIPPED", "error": null}
  {"type": "message.session", "message_id": 2, "claude_session_id": "uuid"}
  {"type": "sessions.response", "request_id": "...", "sessions": [...]}

Server -> agent:
  {"type": "run.payload", "run": {...}}   # full run description (projects, paths, prompts)
  {"type": "run.update", "run": {...}}    # refresh quota budget / pending messages
  {"type": "run.stop", "run_id": 1}
  {"type": "sessions.list", "local_path": "C:\\...", "request_id": "..."}
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt

from core.config import settings
from core.database import SessionLocal
from enums.machine_status import MachineStatus
from enums.queue_item_status import QueueItemStatus
from enums.run_status import RunStatus
from models.machine import Machine
from models.quota_snapshot import QuotaSnapshot
from models.run import Run
from models.run_event import RunEvent
from models.run_message import RunMessage
from services.agent_hub import agent_hub
from services.auth_service import verify_password
from services.queue_sync import sync_queue_items_for_run_message
from services.run_dispatcher import dispatch_run

router = APIRouter(prefix="/ws", tags=["websocket"])


def _authenticate_agent(token: str) -> Optional[int]:
    """
    Resolve a machine id from an agent token by verifying the stored hash.

    Args:
        token: The plaintext agent token.

    Returns:
        The machine id if the token is valid, else None.
    """
    db = SessionLocal()
    try:
        for machine in db.query(Machine).filter(Machine.agent_token_hash.isnot(None)).all():
            if verify_password(token, machine.agent_token_hash):
                return machine.id
        return None
    finally:
        db.close()


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """
    Parse an ISO timestamp coming from the agent.

    Args:
        value: ISO string or None.

    Returns:
        A datetime or None.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Store as naive UTC for consistency with the rest of the schema (datetime.utcnow()).
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


@router.websocket("/agent")
async def agent_socket(websocket: WebSocket, token: str = Query(...)) -> None:
    """
    Handle an agent WebSocket connection.

    Args:
        websocket: The agent WebSocket.
        token: The agent's machine token.
    """
    machine_id = _authenticate_agent(token)
    if machine_id is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    await agent_hub.register_agent(machine_id, websocket)
    _set_machine_online(machine_id, True, MachineStatus.IDLE.value)
    await _redispatch_pending_runs(machine_id)

    try:
        while True:
            message = await websocket.receive_json()
            await _handle_agent_message(machine_id, message)
    except WebSocketDisconnect:
        pass
    finally:
        await agent_hub.unregister_agent(machine_id)
        _set_machine_online(machine_id, False, MachineStatus.OFFLINE.value)


async def _handle_agent_message(machine_id: int, message: dict) -> None:
    """
    Persist and fan out a message received from an agent.

    Args:
        machine_id: The reporting machine.
        message: The JSON message.
    """
    msg_type = message.get("type")
    db = SessionLocal()
    try:
        if msg_type == "hello":
            machine = db.get(Machine, machine_id)
            if machine:
                machine.agent_version = message.get("agent_version")
                machine.claude_version = message.get("claude_version")
                machine.last_seen_at = datetime.utcnow()
                db.commit()
        elif msg_type == "status":
            machine = db.get(Machine, machine_id)
            if machine:
                machine.status = message.get("status", MachineStatus.IDLE.value)
                machine.last_seen_at = datetime.utcnow()
                db.commit()
        elif msg_type == "quota":
            db.add(
                QuotaSnapshot(
                    machine_id=machine_id,
                    bucket=message.get("bucket", "five_hour"),
                    utilization=float(message.get("utilization", 0.0)),
                    resets_at=_parse_dt(message.get("resets_at")),
                )
            )
            db.commit()
        elif msg_type == "event":
            db.add(
                RunEvent(
                    run_id=int(message["run_id"]),
                    level=message.get("level", "info"),
                    message=message.get("message", ""),
                    queue_item_id=message.get("queue_item_id"),
                )
            )
            db.commit()
        elif msg_type == "run.status":
            run = db.get(Run, int(message["run_id"]))
            if run:
                new_status = message.get("status", RunStatus.RUNNING.value)
                run.status = new_status
                if new_status == RunStatus.RUNNING.value and run.started_at is None:
                    run.started_at = datetime.utcnow()
                if new_status in (
                    RunStatus.COMPLETED.value,
                    RunStatus.FAILED.value,
                    RunStatus.STOPPED.value,
                ):
                    run.finished_at = datetime.utcnow()
                db.commit()
        elif msg_type == "message.status":
            run_message = db.get(RunMessage, int(message["message_id"]))
            if run_message:
                new_status = message.get("status", QueueItemStatus.PENDING.value)
                run_message.status = new_status
                run_message.error = message.get("error")
                sync_queue_items_for_run_message(
                    db, run_message, new_status, message.get("error")
                )
                db.commit()
        elif msg_type == "message.session":
            run_message = db.get(RunMessage, int(message["message_id"]))
            if run_message:
                session_id = message.get("claude_session_id")
                if session_id:
                    run_message.claude_session_id = str(session_id)
                    db.commit()
        elif msg_type == "sessions.response":
            agent_hub.resolve_request(message.get("request_id"), message)
        elif msg_type == "quota.response":
            agent_hub.resolve_request(message.get("request_id"), message)
    finally:
        db.close()

    if msg_type not in ("sessions.response", "quota.response"):
        # Relay to dashboards for live UI (session list responses stay server-side).
        await agent_hub.broadcast_dashboard({"machine_id": machine_id, **message})


async def _redispatch_pending_runs(machine_id: int) -> None:
    """
    On agent (re)connect, resend the payloads of runs that are due for this machine.

    Args:
        machine_id: The machine whose agent just connected.
    """
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        runs = (
            db.query(Run)
            .filter(
                Run.machine_id == machine_id,
                Run.status.in_(
                    [
                        RunStatus.SCHEDULED.value,
                        RunStatus.RUNNING.value,
                        RunStatus.WAITING_QUOTA.value,
                    ]
                ),
            )
            .order_by(Run.created_at.asc())
            .all()
        )
        for run in runs:
            if run.scheduled_at is None or run.scheduled_at <= now:
                await dispatch_run(db, run)
    finally:
        db.close()


def _set_machine_online(machine_id: int, online: bool, status_value: str) -> None:
    """
    Update a machine's online flag and status.

    Args:
        machine_id: The machine id.
        online: Whether the agent is connected.
        status_value: New status value.
    """
    db = SessionLocal()
    try:
        machine = db.get(Machine, machine_id)
        if machine:
            machine.online = online
            machine.status = status_value
            machine.last_seen_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


@router.websocket("/dashboard")
async def dashboard_socket(websocket: WebSocket, token: str = Query(...)) -> None:
    """
    Handle a dashboard WebSocket connection (live updates).

    Args:
        websocket: The dashboard WebSocket.
        token: A user JWT access token.
    """
    try:
        jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        await websocket.close(code=4401)
        return

    await websocket.accept()
    await agent_hub.register_dashboard(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await agent_hub.unregister_dashboard(websocket)
