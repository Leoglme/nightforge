"""
Worker — orchestrates runs: drains project queues through Claude Code, commits & pushes,
and reports status / events / quota to the control-plane.

Follows the DevLeadHunter worker pattern: an async loop that ticks forever, never crashing
on a single error, plus reactive handlers for server commands.

The control-plane pushes a full ``run.payload`` (projects, local paths, ordered prompts) so
the agent has everything it needs without a separate REST channel.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

from . import claude_runner, git_manager, quota_reader, session_scanner
from .claude_runner import DEFAULT_CONTINUE_PROMPT, looks_like_auth_failure
from .config import AgentConfig, try_load_config
from .ws_client import WsClient

logger = logging.getLogger(__name__)

SATURATION_THRESHOLD = 0.85


@dataclass
class _MessageState:
    """Runtime state for a single run message."""

    id: int
    content: str
    claude_session_id: Optional[str] = None


@dataclass
class _RunState:
    """In-memory state for the active run."""

    run_id: int
    parallel: bool
    window_end: Optional[datetime]
    quota_limit: int
    quotas_consumed: int = 0
    projects: list = field(default_factory=list)
    session_by_message: Dict[int, Optional[str]] = field(default_factory=dict)


class Worker:
    """Drives Claude Code for scheduled runs and reports back to the control-plane."""

    def __init__(self, config: AgentConfig) -> None:
        """
        Initialize the worker.

        Args:
            config: Agent configuration.
        """
        self._config = config
        self._client = WsClient(self._fresh_config, self._on_message)
        self._run_state: Optional[_RunState] = None
        self._stop_requested = False
        self._failures = 0
        self._last_reset_hint: Optional[datetime] = None
        self._run_task: Optional[asyncio.Task] = None
        self._redispatch_pending = False

    def _fresh_config(self) -> Optional[AgentConfig]:
        """
        Reload agent.json before each WebSocket connect.

        Returns:
            Fresh configuration, or None if not provisioned yet.
        """
        config = try_load_config()
        if config is not None:
            self._config = config
        return config

    async def start(self) -> None:
        """Start the WebSocket loop and the heartbeat loop concurrently."""
        await asyncio.gather(self._client.run_forever(), self._heartbeat_loop())

    async def _heartbeat_loop(self) -> None:
        """Periodically report status and quota to the control-plane."""
        while True:
            try:
                await self._tick()
            except Exception as exc:  # noqa: BLE001
                logger.error("Unhandled error in heartbeat tick: %s", exc, exc_info=True)
            await asyncio.sleep(self._config.tick_seconds)

    async def _tick(self) -> None:
        """One heartbeat: push status and any available quota reading."""
        status = "WORKING" if self._run_state is not None else "IDLE"
        await self._client.send({"type": "status", "status": status})

        reading = await quota_reader.read_five_hour(self._last_reset_hint)
        if reading is not None:
            await self._client.send(
                {
                    "type": "quota",
                    "bucket": reading.bucket,
                    "utilization": reading.utilization,
                    "resets_at": reading.resets_at.isoformat() if reading.resets_at else None,
                }
            )

    async def _on_message(self, message: dict) -> None:
        """
        Handle a command from the control-plane.

        Args:
            message: The JSON command.
        """
        msg_type = message.get("type")
        if msg_type == "run.payload":
            await self._handle_run_payload(message["run"])
        elif msg_type == "run.stop":
            run_id = message.get("run_id")
            if run_id is None or (
                self._run_state is not None and int(run_id) == self._run_state.run_id
            ):
                self._stop_requested = True
        elif msg_type == "sessions.list":
            await self._handle_sessions_list(message)
        elif msg_type == "run.update":
            await self._handle_run_update(message.get("run", {}))
        elif msg_type == "quota.read":
            await self._handle_quota_read(message)

    async def _handle_quota_read(self, message: dict) -> None:
        """
        Reply with a fresh OAuth quota reading for the quota planner UI.

        Args:
            message: Command with optional ``request_id``.
        """
        quota_reader.invalidate_cache()
        reading = await quota_reader.read_five_hour(self._last_reset_hint)
        await self._client.send(
            {
                "type": "quota.response",
                "request_id": message.get("request_id"),
                "bucket": reading.bucket if reading else None,
                "utilization": reading.utilization if reading else None,
                "resets_at": reading.resets_at.isoformat() if reading and reading.resets_at else None,
            }
        )

    async def _handle_sessions_list(self, message: dict) -> None:
        """
        List Claude sessions for a local path and reply to the control-plane.

        Args:
            message: Command with ``local_path`` and ``request_id``.
        """
        local_path = message.get("local_path")
        request_id = message.get("request_id")
        sessions = []
        if isinstance(local_path, str) and local_path.strip():
            for item in session_scanner.list_sessions(local_path.strip()):
                sessions.append(
                    {
                        "session_id": item.session_id,
                        "title": item.title,
                        "cwd": item.cwd,
                        "updated_at": item.updated_at.isoformat(),
                    }
                )
        await self._client.send(
            {
                "type": "sessions.response",
                "request_id": request_id,
                "sessions": sessions,
            }
        )

    async def _handle_run_update(self, run: dict) -> None:
        """
        Update quota budget or redispatch while a run is active.

        Args:
            run: Partial run payload with at least ``id`` and optionally ``quota_count``.
        """
        if self._run_state is None:
            await self._handle_run_payload(run)
            return

        run_id = int(run.get("id", self._run_state.run_id))
        if run_id != self._run_state.run_id:
            return

        if "quota_count" in run:
            self._run_state.quota_limit = int(run["quota_count"])
            await self._emit(run_id, "info", f"Quota budget updated → {self._run_state.quota_limit}")

        if run.get("projects"):
            self._run_state.projects = run["projects"]
            self._hydrate_sessions(self._run_state)
            self._redispatch_pending = True

    async def _handle_run_payload(self, run: dict) -> None:
        """
        Start or refresh a run from its payload.

        Args:
            run: The run payload.
        """
        run_id = int(run["id"])
        if self._run_state is not None and self._run_state.run_id == run_id:
            self._run_state.quota_limit = int(run.get("quota_count", self._run_state.quota_limit))
            self._run_state.projects = run.get("projects", self._run_state.projects)
            self._run_state.window_end = _parse_dt(run.get("window_end"))
            self._hydrate_sessions(self._run_state)
            self._redispatch_pending = True
            return

        if self._run_state is not None:
            logger.info("A run is already active (%s); ignoring run %s", self._run_state.run_id, run_id)
            return

        self._run_task = asyncio.create_task(self._execute_run(run))

    # ------------------------------------------------------------------ run

    async def _execute_run(self, run: dict) -> None:
        """
        Execute a run described by its payload: drain each selected project's queue.

        Args:
            run: The run payload with ``id``, ``parallel``, ``window_end`` and ``projects``.
        """
        run_id = int(run["id"])
        self._run_state = _RunState(
            run_id=run_id,
            parallel=bool(run.get("parallel")),
            window_end=_parse_dt(run.get("window_end")),
            quota_limit=int(run.get("quota_count", 1)),
            quotas_consumed=int(run.get("quotas_consumed", 0)),
            projects=run.get("projects", []),
        )
        self._hydrate_sessions(self._run_state)
        self._stop_requested = False
        self._failures = 0
        self._redispatch_pending = False

        wait_until = _parse_dt(run.get("quota_wait_until"))
        if not await self._ensure_quota_available(run_id, wait_until):
            await self._set_run_status(run_id, "STOPPED")
            await self._emit(run_id, "info", f"Run {run_id} stopped before start (quota/window)")
            self._run_state = None
            self._run_task = None
            return

        await self._set_run_status(run_id, "RUNNING")
        await self._emit(run_id, "info", f"Run {run_id} started")

        try:
            while not self._stop_requested and not self._budget_exhausted():
                if self._window_passed():
                    break
                if self._quota_budget_exhausted():
                    await self._emit(run_id, "info", "Quota budget reached — stopping")
                    break

                projects = self._run_state.projects
                if self._run_state.parallel:
                    await asyncio.gather(*(self._work_project(run_id, project) for project in projects))
                    break
                for project in projects:
                    if self._stop_requested or self._budget_exhausted() or self._quota_budget_exhausted():
                        break
                    if self._window_passed():
                        break
                    await self._work_project(run_id, project)

                if not self._redispatch_pending:
                    break
                self._redispatch_pending = False
                await self._emit(run_id, "info", "Run updated — continuing with pending messages")

            final = self._final_status()
            await self._set_run_status(run_id, final)
            await self._emit(run_id, "info", f"Run {run_id} finished ({final})")
        except Exception as exc:  # noqa: BLE001
            logger.error("Run %s crashed: %s", run_id, exc, exc_info=True)
            await self._emit(run_id, "error", f"Run crashed: {exc}")
            await self._set_run_status(run_id, "FAILED")
        finally:
            self._run_state = None
            self._run_task = None

    @staticmethod
    def _hydrate_sessions(state: _RunState) -> None:
        """Load per-message Claude session ids from the payload into runtime state."""
        for project in state.projects:
            for message in project.get("messages", []):
                message_id = message.get("id")
                if message_id is None:
                    continue
                session_id = message.get("claude_session_id")
                if session_id:
                    state.session_by_message[int(message_id)] = str(session_id)

    def _final_status(self) -> str:
        """
        Compute the terminal status of the active run.

        Returns:
            One of ``STOPPED``, ``FAILED`` or ``COMPLETED``.
        """
        if self._stop_requested:
            return "STOPPED"
        if self._budget_exhausted():
            return "FAILED"
        return "COMPLETED"

    def _budget_exhausted(self) -> bool:
        """
        Whether the consecutive-failure budget has been exhausted.

        Returns:
            True if too many items failed in a row.
        """
        return self._failures >= self._config.error_budget

    def _quota_budget_exhausted(self) -> bool:
        """
        Whether the run has consumed its allowed quota windows.

        Returns:
            True when no further quota-backed work should start.
        """
        if self._run_state is None:
            return False
        return self._run_state.quotas_consumed >= self._run_state.quota_limit

    def _window_passed(self) -> bool:
        """
        Whether the run's hard-stop window has elapsed.

        Returns:
            True if a window end is set and now is past it.
        """
        if self._run_state is None or self._run_state.window_end is None:
            return False
        return _utc_now_naive() >= self._run_state.window_end

    async def _ensure_quota_available(
        self, run_id: int, planned_wait_until: Optional[datetime]
    ) -> bool:
        """
        Wait until quota is available before the first Claude invocation.

        Uses the planned timeline when provided, otherwise the live OAuth reading.

        Args:
            run_id: The active run id.
            planned_wait_until: Optional first-window start from the control-plane plan.

        Returns:
            False when a stop was requested or the hard window elapsed while waiting.
        """
        wait_until: Optional[datetime] = None
        reading = await quota_reader.read_five_hour(self._last_reset_hint)
        if (
            reading is not None
            and reading.utilization >= SATURATION_THRESHOLD
            and reading.resets_at is not None
        ):
            live_wait = _coerce_wait_until(reading.resets_at)
            if live_wait is not None and live_wait > _utc_now():
                wait_until = live_wait

        if wait_until is None and planned_wait_until is not None:
            planned_wait = _coerce_wait_until(planned_wait_until)
            if planned_wait is not None and planned_wait > _utc_now():
                wait_until = planned_wait

        if wait_until is None or wait_until <= _utc_now():
            await quota_reader.ensure_oauth_fresh()
            return True

        await self._set_run_status(run_id, "WAITING_QUOTA")
        await self._client.send({"type": "status", "status": "WAITING_QUOTA"})
        await self._emit(
            run_id,
            "info",
            f"Quota saturé — attente jusqu'à {_format_local_time(wait_until)}",
        )
        resumed = await self._wait_for_quota(wait_until)
        if resumed:
            await quota_reader.ensure_oauth_fresh()
        return resumed

    # -------------------------------------------------------------- project

    async def _work_project(self, run_id: int, project: dict) -> None:
        """
        Run every composed night message of a project sequentially.

        Args:
            run_id: The active run id.
            project: Project payload with ``local_path``, ``base_branch`` and ``messages``.
        """
        cwd = project.get("local_path")
        name = project.get("name", "project")
        messages = project.get("messages", [])
        if not messages:
            return
        if not cwd:
            await self._emit(run_id, "error", f"{name}: no local path set for this machine")
            return

        if not await git_manager.ensure_clean(cwd):
            await self._emit(run_id, "warning", f"{name}: working tree not clean, continuing")

        branch = await git_manager.create_night_branch(cwd, project.get("base_branch") or "main")
        await self._emit(run_id, "info", f"{name}: on branch {branch}")

        did_work = False
        for message in messages:
            if self._stop_requested or self._budget_exhausted() or self._quota_budget_exhausted():
                break
            if self._window_passed():
                await self._emit(run_id, "info", f"{name}: window reached, stopping")
                break
            ok = await self._run_message(run_id, cwd, message)
            await git_manager.commit_all(cwd, self._commit_message(message, ok))
            did_work = True

        if did_work:
            await git_manager.push(cwd, branch)
            await self._emit(run_id, "info", f"{name}: pushed {branch}")

    @staticmethod
    def _commit_message(message: dict, ok: bool) -> str:
        """
        Build a conventional commit message for a night message.

        Args:
            message: The message payload.
            ok: Whether the message completed successfully.

        Returns:
            A commit message string.
        """
        summary = " ".join(str(message.get("content", "")).split())[:60]
        prefix = "feat" if ok else "wip"
        return f"{prefix}: {summary}" if summary else f"{prefix}: night run progress"

    async def _run_message(self, run_id: int, cwd: str, message: dict) -> bool:
        """
        Run a single night message, retrying across quota resets until it completes or stops.

        Args:
            run_id: The active run id.
            cwd: Project working directory.
            message: Message payload with ``id`` and ``content``.

        Returns:
            True if the message completed successfully.
        """
        message_id = message.get("id")
        resume_session = None
        if message_id is not None and self._run_state is not None:
            resume_session = self._run_state.session_by_message.get(int(message_id))
        if not resume_session:
            resume_session = message.get("claude_session_id")

        prompt = str(message.get("content") or "").strip()
        if resume_session and not prompt:
            prompt = DEFAULT_CONTINUE_PROMPT

        while True:
            if self._stop_requested or self._window_passed():
                await self._set_message_status(message_id, "SKIPPED")
                return False

            await self._set_message_status(message_id, "RUNNING")
            await quota_reader.ensure_oauth_fresh()
            exit_code, quota_hit, reset_hint, session_id, auth_failed = await self._run_claude(
                run_id,
                cwd,
                prompt,
                resume_session=resume_session,
                model=message.get("claude_model") or None,
            )

            if auth_failed:
                await self._emit(run_id, "warning", "Auth Claude expirée — rafraîchissement du token…")
                if await quota_reader.ensure_oauth_fresh():
                    exit_code, quota_hit, reset_hint, session_id, auth_failed = await self._run_claude(
                        run_id,
                        cwd,
                        prompt,
                        resume_session=resume_session,
                        model=message.get("claude_model") or None,
                    )

            if session_id and message_id is not None and self._run_state is not None:
                self._run_state.session_by_message[int(message_id)] = session_id
                await self._client.send(
                    {
                        "type": "message.session",
                        "message_id": int(message_id),
                        "claude_session_id": session_id,
                    }
                )
                resume_session = session_id

            if quota_hit:
                if self._run_state is not None:
                    self._run_state.quotas_consumed += 1
                self._last_reset_hint = reset_hint
                await self._set_run_status(run_id, "WAITING_QUOTA")
                await self._client.send({"type": "status", "status": "WAITING_QUOTA"})
                await self._emit(run_id, "warning", "Quota hit — waiting for reset")
                resumed = await self._wait_for_quota(reset_hint)
                if not resumed:
                    await self._set_message_status(message_id, "SKIPPED")
                    return False
                if self._quota_budget_exhausted():
                    await self._emit(run_id, "info", "Quota budget exhausted after reset wait")
                    await self._set_message_status(message_id, "SKIPPED")
                    return False
                await self._set_run_status(run_id, "RUNNING")
                prompt = DEFAULT_CONTINUE_PROMPT
                continue

            if exit_code == 0:
                self._failures = 0
                await self._set_message_status(message_id, "DONE")
                return True

            self._failures += 1
            await self._set_message_status(message_id, "FAILED", f"exit code {exit_code}")
            await self._emit(run_id, "error", f"Message failed (exit {exit_code})")
            return False

    async def _run_claude(
        self,
        run_id: int,
        cwd: str,
        prompt: str,
        resume_session: Optional[str] = None,
        model: Optional[str] = None,
    ) -> tuple[int, bool, Optional[datetime], Optional[str], bool]:
        """
        Stream one Claude invocation, emitting output as events.

        Args:
            run_id: The active run id.
            cwd: Working directory.
            prompt: Prompt text.
            resume_session: Optional session UUID to resume.
            model: Optional Claude model alias.

        Returns:
            Tuple of exit code, quota hit, reset hint, session id and auth-failure flag.
        """
        exit_code = 0
        quota_hit = False
        reset_hint: Optional[datetime] = None
        session_id: Optional[str] = resume_session
        auth_failed = False

        async for line in claude_runner.run_prompt(
            self._config.claude_bin,
            cwd,
            prompt,
            resume_session=resume_session,
            model=model,
        ):
            if line.startswith("__NF_RESULT__:"):
                parts = line.split(":", 4)
                exit_code = int(parts[1]) if len(parts) > 1 and parts[1] else 0
                quota_hit = len(parts) > 2 and parts[2] == "1"
                if len(parts) > 3 and parts[3]:
                    try:
                        reset_hint = datetime.fromisoformat(parts[3])
                    except ValueError:
                        reset_hint = None
                if len(parts) > 4 and parts[4]:
                    session_id = parts[4]
                continue
            if looks_like_auth_failure(line):
                auth_failed = True
            await self._emit(run_id, "info", line)

        return exit_code, quota_hit, reset_hint, session_id, auth_failed

    async def _wait_for_quota(self, reset_hint: Optional[datetime]) -> bool:
        """
        Sleep until the quota is expected to reset, in short cancellable slices.

        Args:
            reset_hint: A parsed reset time, if known.

        Returns:
            True if we should resume, False if a stop was requested or the window elapsed.
        """
        target = _coerce_wait_until(reset_hint)
        if target is not None:
            total = max(0.0, (target - _utc_now()).total_seconds()) + 60.0
        else:
            total = float(self._config.quota_retry_seconds)

        waited = 0.0
        while waited < total:
            if self._stop_requested or self._window_passed():
                return False
            await asyncio.sleep(min(15.0, total - waited))
            waited += 15.0
        return not (self._stop_requested or self._window_passed())

    # --------------------------------------------------------------- report

    async def _set_run_status(self, run_id: int, status: str) -> None:
        """
        Report a run status transition to the control-plane.

        Args:
            run_id: The run id.
            status: The new run status.
        """
        await self._client.send({"type": "run.status", "run_id": run_id, "status": status})

    async def _set_message_status(
        self, message_id: Optional[int], status: str, error: Optional[str] = None
    ) -> None:
        """
        Report a night-message status transition to the control-plane.

        Args:
            message_id: The run message id.
            status: The new message status.
            error: Optional error message.
        """
        if message_id is None:
            return
        await self._client.send(
            {
                "type": "message.status",
                "message_id": int(message_id),
                "status": status,
                "error": error,
            }
        )

    async def _emit(
        self, run_id: int, level: str, message: str, queue_item_id: Optional[int] = None
    ) -> None:
        """
        Send a run event to the control-plane.

        Args:
            run_id: The run id.
            level: Log level.
            message: The message.
            queue_item_id: Related queue item, if any.
        """
        await self._client.send(
            {
                "type": "event",
                "run_id": run_id,
                "level": level,
                "message": message,
                "queue_item_id": queue_item_id,
            }
        )


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    """
    Parse an ISO timestamp coming from the control-plane payload.

    Args:
        value: ISO string or None.

    Returns:
        A naive UTC datetime or None.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None)
    except ValueError:
        return None


def _utc_now() -> datetime:
    """Current time as timezone-aware UTC."""
    return datetime.now(timezone.utc)


def _utc_now_naive() -> datetime:
    """Current time as naive UTC (matches control-plane ``window_end`` storage)."""
    return _utc_now().replace(tzinfo=None)


def _coerce_wait_until(value: Optional[datetime]) -> Optional[datetime]:
    """
    Normalize a reset/wait timestamp to aware UTC for comparisons.

    Args:
        value: Datetime from OAuth, CLI hints or the planned timeline.

    Returns:
        Aware UTC datetime, or None.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_local_time(value: datetime) -> str:
    """Format a UTC instant for human-readable agent logs."""
    aware = _coerce_wait_until(value)
    if aware is None:
        return "?"
    return aware.astimezone().strftime("%H:%M")
