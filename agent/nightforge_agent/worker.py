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
from typing import Dict, Optional, Set

from . import (
    claude_login,
    claude_runner,
    cursor_login,
    cursor_runner,
    cursor_usage_reader,
    git_manager,
    ideas_expander,
    oauth_credentials,
    oauth_setup,
    quota_reader,
    session_scanner,
)
from .claude_runner import DEFAULT_CONTINUE_PROMPT, looks_like_auth_failure
from .config import AgentConfig, try_load_config
from .ws_client import WsClient

logger = logging.getLogger(__name__)

# Only block before Claude when the 5h bucket is actually near empty.
# Partial usage must NOT delay launches — "fresh quota" waits come from the
# night planner via ``quota_wait_until``, not from live utilization alone.
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
    cursor_accounts: list = field(default_factory=list)
    claude_accounts: list = field(default_factory=list)
    processed_message_ids: Set[int] = field(default_factory=set)
    had_message_failure: bool = False


class Worker:
    """Drives Claude Code for scheduled runs and reports back to the control-plane."""

    def __init__(self, config: AgentConfig) -> None:
        """
        Initialize the worker.

        Args:
            config: Agent configuration.
        """
        self._config = config
        oauth_setup.remove_nightforge_api_key_helper()
        self._client = WsClient(self._fresh_config, self._on_message)
        self._run_state: Optional[_RunState] = None
        self._stop_requested = False
        self._failures = 0
        self._last_reset_hint: Optional[datetime] = None
        self._run_task: Optional[asyncio.Task] = None
        self._redispatch_pending = False
        self._pending_runs: list[dict] = []

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

    async def flush_quotas(self) -> None:
        """
        Push a final Claude + Cursor quota snapshot to the control-plane.

        Used on shutdown so mobile/web keep the last known usage after the PC leaves.
        """
        try:
            await self._tick()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Final quota flush failed: %s", exc)

    async def _heartbeat_loop(self) -> None:
        """Periodically report status and quota to the control-plane."""
        while True:
            try:
                await self._tick()
            except Exception as exc:  # noqa: BLE001
                logger.error("Unhandled error in heartbeat tick: %s", exc, exc_info=True)
            # Slower ticks when idle to reduce CPU/network; faster while working.
            delay = (
                self._config.tick_seconds_working
                if self._run_state is not None
                else self._config.tick_seconds
            )
            await asyncio.sleep(delay)

    async def _tick(self) -> None:
        """One heartbeat: push status and any available quota reading."""
        status = "WORKING" if self._run_state is not None else "IDLE"
        await self._client.send({"type": "status", "status": status})

        readings = await quota_reader.read_all_buckets(self._last_reset_hint)
        for reading in readings:
            if reading.auth_error:
                continue
            await self._client.send(
                {
                    "type": "quota",
                    "bucket": reading.bucket,
                    "utilization": reading.utilization,
                    "resets_at": reading.resets_at.isoformat() if reading.resets_at else None,
                }
            )

        # Best-effort Cursor plan usage (omit when unavailable).
        try:
            for bucket in await cursor_usage_reader.read_cursor_usage():
                await self._client.send(
                    {
                        "type": "quota",
                        "bucket": bucket.bucket,
                        "utilization": bucket.utilization,
                        "resets_at": bucket.resets_at.isoformat() if bucket.resets_at else None,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("Cursor usage tick skipped: %s", exc)

    async def _on_message(self, message: dict) -> None:
        """
        Handle a command from the control-plane.

        Args:
            message: The JSON command.
        """
        msg_type = message.get("type")
        if msg_type == "run.payload":
            try:
                await self._handle_run_payload(message["run"])
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed to handle run.payload: %s", exc, exc_info=True)
        elif msg_type == "run.stop":
            run_id = message.get("run_id")
            if run_id is None or (
                self._run_state is not None and int(run_id) == self._run_state.run_id
            ):
                self._stop_requested = True
        elif msg_type == "sessions.list":
            await self._handle_sessions_list(message)
        elif msg_type == "repo.inspect":
            await self._handle_repo_inspect(message)
        elif msg_type == "run.update":
            await self._handle_run_update(message.get("run", {}))
        elif msg_type == "quota.read":
            await self._handle_quota_read(message)
        elif msg_type == "cursor.usage":
            await self._handle_cursor_usage(message)
        elif msg_type == "cursor.session.export":
            await self._handle_cursor_session_export(message)
        elif msg_type == "cursor.login.start":
            await self._handle_cursor_login_start(message)
        elif msg_type == "cursor.login.poll":
            await self._handle_cursor_login_poll(message)
        elif msg_type == "cursor.login.complete":
            await self._handle_cursor_login_complete(message)
        elif msg_type == "cursor.login.cancel":
            await self._handle_cursor_login_cancel(message)
        elif msg_type == "claude.usage":
            await self._handle_claude_usage(message)
        elif msg_type == "claude.session.export":
            await self._handle_claude_session_export(message)
        elif msg_type == "claude.login.start":
            await self._handle_claude_login_start(message)
        elif msg_type == "claude.login.poll":
            await self._handle_claude_login_poll(message)
        elif msg_type == "claude.login.complete":
            await self._handle_claude_login_complete(message)
        elif msg_type == "claude.login.cancel":
            await self._handle_claude_login_cancel(message)
        elif msg_type == "ideas.expand":
            await self._handle_ideas_expand(message)

    async def _handle_quota_read(self, message: dict) -> None:
        """
        Reply with fresh OAuth quota readings (all Claude buckets) for the UI.

        Args:
            message: Command with optional ``request_id``.
        """
        quota_reader.invalidate_cache()
        readings = await quota_reader.read_all_buckets(self._last_reset_hint)
        five = next((r for r in readings if r.bucket == "five_hour"), None)
        await self._client.send(
            {
                "type": "quota.response",
                "request_id": message.get("request_id"),
                "bucket": five.bucket if five else None,
                "utilization": five.utilization if five else None,
                "resets_at": five.resets_at.isoformat() if five and five.resets_at else None,
                "auth_error": five.auth_error if five else None,
                "buckets": [
                    {
                        "bucket": r.bucket,
                        "utilization": r.utilization,
                        "resets_at": r.resets_at.isoformat() if r.resets_at else None,
                        "auth_error": r.auth_error,
                    }
                    for r in readings
                ],
            }
        )

    async def _handle_cursor_usage(self, message: dict) -> None:
        """
        Reply with Cursor plan usage when the local session can fetch it.

        Args:
            message: Command with optional ``request_id``.
        """
        buckets = await cursor_usage_reader.read_cursor_usage(force=True)
        _token, email = cursor_usage_reader.export_local_session()
        await self._client.send(
            {
                "type": "cursor.usage.response",
                "request_id": message.get("request_id"),
                "email": email,
                "buckets": [
                    {
                        "bucket": b.bucket,
                        "label": b.label,
                        "utilization": b.utilization,
                        "resets_at": b.resets_at.isoformat() if b.resets_at else None,
                    }
                    for b in buckets
                ],
            }
        )

    async def _handle_cursor_session_export(self, message: dict) -> None:
        """
        Export the local Cursor session token for vault import.

        Args:
            message: Command with optional ``request_id``.
        """
        token, email = cursor_usage_reader.export_local_session()
        await self._client.send(
            {
                "type": "cursor.session.export.response",
                "request_id": message.get("request_id"),
                "session_token": token,
                "email": email,
                "error": None if token else "Session Cursor locale introuvable",
            }
        )

    async def _handle_cursor_login_start(self, message: dict) -> None:
        """Start NoDriver Cursor login (isolated Chromium)."""
        result = await cursor_login.start_login(self._config.cursor_bin)
        await self._client.send(
            {
                "type": "cursor.login.start.response",
                "request_id": message.get("request_id"),
                **result,
            }
        )

    async def _handle_cursor_login_poll(self, message: dict) -> None:
        """Poll an in-progress NoDriver Cursor login."""
        login_id = str(message.get("login_id") or "")
        result = await cursor_login.poll_login(login_id)
        await self._client.send(
            {
                "type": "cursor.login.poll.response",
                "request_id": message.get("request_id"),
                **result,
            }
        )

    async def _handle_cursor_login_complete(self, message: dict) -> None:
        """User confirmed NoDriver login finished — capture cookie."""
        login_id = str(message.get("login_id") or "")
        result = await cursor_login.complete_login(login_id)
        await self._client.send(
            {
                "type": "cursor.login.complete.response",
                "request_id": message.get("request_id"),
                **result,
            }
        )

    async def _handle_cursor_login_cancel(self, message: dict) -> None:
        """Cancel NoDriver login and close the helper browser."""
        login_id = str(message.get("login_id") or "")
        result = await cursor_login.cancel_login(login_id)
        await self._client.send(
            {
                "type": "cursor.login.cancel.response",
                "request_id": message.get("request_id"),
                **result,
            }
        )

    async def _handle_claude_usage(self, message: dict) -> None:
        """
        Reply with every Claude Max bucket + best-effort email for the local session.

        Args:
            message: Command with optional ``request_id``.
        """
        quota_reader.invalidate_cache()
        readings = await quota_reader.read_all_buckets(self._last_reset_hint)
        _oauth, email = await quota_reader.export_local_oauth()
        five = next((r for r in readings if r.bucket == "five_hour"), None)
        await self._client.send(
            {
                "type": "claude.usage.response",
                "request_id": message.get("request_id"),
                "email": email,
                "auth_error": five.auth_error if five else None,
                "buckets": [
                    {
                        "bucket": r.bucket,
                        "utilization": r.utilization,
                        "resets_at": r.resets_at.isoformat() if r.resets_at else None,
                        "auth_error": r.auth_error,
                    }
                    for r in readings
                ],
            }
        )

    async def _handle_claude_session_export(self, message: dict) -> None:
        """
        Export the local Claude OAuth block + email for vault import.

        Refreshes an expired access token when possible; does not open the browser.
        """
        oauth, email = await quota_reader.export_local_oauth()
        error = None
        if not oauth:
            error = "Session Claude locale introuvable"
        await self._client.send(
            {
                "type": "claude.session.export.response",
                "request_id": message.get("request_id"),
                "oauth": oauth,
                "email": email,
                "error": error,
            }
        )

    async def _handle_claude_login_start(self, message: dict) -> None:
        """Start a ``claude auth login`` capture (extra account, or machine first connect)."""
        keep_on_machine = bool(message.get("keep_on_machine"))
        result = await claude_login.start_login(
            self._config.claude_bin,
            keep_on_machine=keep_on_machine,
        )
        await self._client.send(
            {
                "type": "claude.login.start.response",
                "request_id": message.get("request_id"),
                **result,
            }
        )

    async def _handle_claude_login_poll(self, message: dict) -> None:
        """Poll an in-progress Claude login capture."""
        login_id = str(message.get("login_id") or "")
        result = await claude_login.poll_login(login_id)
        await self._client.send(
            {
                "type": "claude.login.poll.response",
                "request_id": message.get("request_id"),
                **result,
            }
        )

    async def _handle_claude_login_complete(self, message: dict) -> None:
        """User confirmed Claude login finished — capture OAuth block."""
        login_id = str(message.get("login_id") or "")
        result = await claude_login.complete_login(login_id)
        await self._client.send(
            {
                "type": "claude.login.complete.response",
                "request_id": message.get("request_id"),
                **result,
            }
        )

    async def _handle_claude_login_cancel(self, message: dict) -> None:
        """Cancel Claude login capture and restore the machine's own session."""
        login_id = str(message.get("login_id") or "")
        result = await claude_login.cancel_login(login_id)
        await self._client.send(
            {
                "type": "claude.login.cancel.response",
                "request_id": message.get("request_id"),
                **result,
            }
        )

    async def _handle_ideas_expand(self, message: dict) -> None:
        """
        Expand free-form ideas into queue prompts via Cursor / Claude.

        Args:
            message: Command with ``prompt``, ``prefer_provider``, ``request_id``.
        """
        request_id = message.get("request_id")
        prompt = message.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            await self._client.send(
                {
                    "type": "ideas.expand.response",
                    "request_id": request_id,
                    "error": "missing prompt",
                    "items": [],
                }
            )
            return

        prefer = message.get("prefer_provider") or "cursor"
        result = await ideas_expander.expand_ideas(
            prompt=prompt.strip(),
            prefer_provider=str(prefer),
            cursor_bin=self._config.cursor_bin,
            claude_bin=self._config.claude_bin,
        )
        await self._client.send(
            {
                "type": "ideas.expand.response",
                "request_id": request_id,
                **result,
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

    async def _handle_repo_inspect(self, message: dict) -> None:
        """
        Inspect a local path (folder name + git remote) and reply.

        Args:
            message: Command with ``local_path`` and ``request_id``.
        """
        local_path = message.get("local_path")
        request_id = message.get("request_id")
        if not isinstance(local_path, str) or not local_path.strip():
            payload = {"exists": False, "is_git": False, "error": "missing local_path"}
        else:
            payload = await git_manager.inspect_repo(local_path.strip())
        await self._client.send(
            {
                "type": "repo.inspect.response",
                "request_id": request_id,
                **payload,
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

        if "cursor_accounts" in run:
            self._run_state.cursor_accounts = list(run.get("cursor_accounts") or [])
        if "claude_accounts" in run:
            self._run_state.claude_accounts = list(run.get("claude_accounts") or [])

    async def _handle_run_payload(self, run: dict) -> None:
        """
        Start or refresh a run from its payload.

        Args:
            run: The run payload.
        """
        run_id = int(run["id"])
        message_count = sum(len(p.get("messages") or []) for p in (run.get("projects") or []))
        logger.info(
            "Received run.payload id=%s projects=%s pending_messages=%s",
            run_id,
            len(run.get("projects") or []),
            message_count,
        )
        if self._run_state is not None and self._run_state.run_id == run_id:
            self._run_state.quota_limit = int(run.get("quota_count", self._run_state.quota_limit))
            self._run_state.projects = run.get("projects", self._run_state.projects)
            self._run_state.window_end = _parse_dt(run.get("window_end"))
            if "cursor_accounts" in run:
                self._run_state.cursor_accounts = list(run.get("cursor_accounts") or [])
            if "claude_accounts" in run:
                self._run_state.claude_accounts = list(run.get("claude_accounts") or [])
            self._hydrate_sessions(self._run_state)
            self._redispatch_pending = True
            return

        if self._run_state is not None:
            self._enqueue_pending_run(run)
            logger.info(
                "Run %s queued behind active run %s (%s pending)",
                run_id,
                self._run_state.run_id,
                len(self._pending_runs),
            )
            return

        self._run_task = asyncio.create_task(self._execute_run(run))

    def _enqueue_pending_run(self, run: dict) -> None:
        """Keep at most one pending payload per run id (latest wins)."""
        run_id = int(run["id"])
        self._pending_runs = [item for item in self._pending_runs if int(item.get("id", -1)) != run_id]
        self._pending_runs.append(run)

    @staticmethod
    def _run_needs_claude_quota(run: dict) -> bool:
        """True when at least one message will use Claude Code (not Cursor-only)."""
        for project in run.get("projects") or []:
            for message in project.get("messages") or []:
                provider = str(message.get("provider") or "claude").strip().lower()
                if provider != "cursor":
                    return True
        return False

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
            cursor_accounts=list(run.get("cursor_accounts") or []),
            claude_accounts=list(run.get("claude_accounts") or []),
        )
        self._hydrate_sessions(self._run_state)
        self._stop_requested = False
        self._failures = 0
        self._redispatch_pending = False

        wait_until = _parse_dt(run.get("quota_wait_until"))
        kind = str(run.get("kind") or "night").strip().lower()
        if not self._run_needs_claude_quota(run):
            logger.info("Run %s: Cursor-only — skip Claude quota wait", run_id)
            await self._emit(run_id, "info", f"Run {run_id}: Cursor-only — skip Claude quota wait")
        elif kind == "quick":
            # Queue / on-the-fly launches: start immediately. Real exhaustion is
            # handled mid-run via Claude CLI quota_hit → _wait_for_quota.
            logger.info("Run %s: quick launch — skip pre-start Claude quota wait", run_id)
        else:
            if not await self._ensure_quota_available(run_id, wait_until):
                await self._finalize_unprocessed_messages(
                    reason="Arrêté avant démarrage (quota / fenêtre)",
                    status="SKIPPED",
                    count_as_failure=False,
                )
                await self._set_run_status(run_id, "STOPPED")
                await self._emit(run_id, "info", f"Run {run_id} stopped before start (quota/window)")
                self._finish_run_and_start_next()
                return

        await self._set_run_status(run_id, "RUNNING")
        logger.info("Run %s started", run_id)
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

            await self._finalize_unprocessed_messages()
            final = self._final_status()
            await self._set_run_status(run_id, final)
            logger.info("Run %s finished (%s)", run_id, final)
            await self._emit(run_id, "info", f"Run {run_id} finished ({final})")
        except Exception as exc:  # noqa: BLE001
            logger.error("Run %s crashed: %s", run_id, exc, exc_info=True)
            await self._emit(run_id, "error", f"Run crashed: {exc}")
            await self._finalize_unprocessed_messages(
                reason=f"Run crashed: {exc}",
                status="FAILED",
                count_as_failure=True,
            )
            await self._set_run_status(run_id, "FAILED")
        finally:
            self._finish_run_and_start_next()

    def _finish_run_and_start_next(self) -> None:
        """Clear active run state and start the next queued payload if any."""
        self._run_state = None
        self._run_task = None
        if not self._pending_runs:
            return
        next_run = self._pending_runs.pop(0)
        logger.info("Starting queued run %s (%s remaining)", next_run.get("id"), len(self._pending_runs))
        self._run_task = asyncio.create_task(self._execute_run(next_run))

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
        if self._run_state is not None and self._run_state.had_message_failure:
            return "FAILED"
        return "COMPLETED"

    async def _finalize_unprocessed_messages(
        self,
        reason: Optional[str] = None,
        status: Optional[str] = None,
        count_as_failure: Optional[bool] = None,
    ) -> None:
        """
        Mark any payload messages still unprocessed before the run ends.

        Prevents the control-plane from showing PENDING forever after a run
        ends without executing them (e.g. missing local path).
        """
        if self._run_state is None:
            return
        if status is None:
            status = "SKIPPED" if self._stop_requested else "FAILED"
        if reason is None:
            reason = (
                "Arrêté avant exécution"
                if status == "SKIPPED"
                else "Non exécuté avant la fin du run"
            )
        if count_as_failure is None:
            count_as_failure = status == "FAILED"
        for project in self._run_state.projects:
            for message in project.get("messages") or []:
                message_id = message.get("id")
                if message_id is None:
                    continue
                mid = int(message_id)
                if mid in self._run_state.processed_message_ids:
                    continue
                self._run_state.processed_message_ids.add(mid)
                if count_as_failure:
                    self._run_state.had_message_failure = True
                await self._set_message_status(mid, status, reason)
                await self._emit(
                    self._run_state.run_id,
                    "error" if count_as_failure else "warning",
                    f"Message #{mid}: {reason}",
                )

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
        Wait until quota is available before the first Claude invocation (night runs).

        Live OAuth blocks only when the 5h bucket is saturated (>= 85%).
        Otherwise the planned timeline from the control-plane (fresh-quota nights)
        is honored when still in the future.

        Args:
            run_id: The active run id.
            planned_wait_until: Optional first-window start from the control-plane plan.

        Returns:
            False when a stop was requested or the hard window elapsed while waiting.
        """
        wait_until: Optional[datetime] = None
        reading = await quota_reader.read_five_hour(self._last_reset_hint)
        if reading is not None and reading.resets_at is not None:
            live_wait = _coerce_wait_until(reading.resets_at)
            if (
                live_wait is not None
                and live_wait > _utc_now()
                and reading.utilization >= SATURATION_THRESHOLD
            ):
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
            f"Attente du prochain quota vierge — démarrage vers {_format_local_time(wait_until)}",
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
            logger.info("Run %s project %s: no pending messages", run_id, name)
            return
        if not cwd:
            error = (
                f"{name}: aucun chemin local configuré pour cette machine — "
                "ouvre Réglages du projet et renseigne le dossier local."
            )
            logger.error("Run %s: %s", run_id, error)
            await self._emit(run_id, "error", error)
            if self._run_state is not None:
                self._run_state.had_message_failure = True
            for message in messages:
                message_id = message.get("id")
                if message_id is None:
                    continue
                mid = int(message_id)
                if self._run_state is not None:
                    self._run_state.processed_message_ids.add(mid)
                await self._set_message_status(mid, "FAILED", error)
            return

        # Flip first message to RUNNING before git setup so the UI leaves
        # "En attente dans la file…" during branch prep / CLI spawn.
        first_id = messages[0].get("id") if messages else None
        if first_id is not None:
            await self._set_message_status(int(first_id), "RUNNING")

        if not await git_manager.ensure_clean(cwd):
            await self._emit(run_id, "warning", f"{name}: working tree not clean, continuing")

        base_branch = project.get("base_branch") or "main"
        push_to_main = bool(project.get("push_to_main", True))
        allow_push = bool(project.get("allow_push", True))
        if push_to_main:
            branch = await git_manager.ensure_on_branch(cwd, base_branch)
            await self._emit(
                run_id,
                "info",
                f"{name}: working on {branch}"
                + (" (push enabled)" if allow_push else " (local commits only)"),
            )
        else:
            branch = await git_manager.create_night_branch(cwd, base_branch)
            await self._emit(run_id, "info", f"{name}: on branch {branch}")

        did_work = False
        for index, message in enumerate(messages):
            if self._stop_requested or self._budget_exhausted() or self._quota_budget_exhausted():
                break
            if self._window_passed():
                await self._emit(run_id, "info", f"{name}: window reached, stopping")
                break
            if index > 0:
                await self._emit(
                    run_id,
                    "info",
                    f"{name}: message {index + 1}/{len(messages)} — previous message finished",
                )
            ok = await self._run_message(run_id, cwd, message)
            await git_manager.commit_all(cwd, self._commit_message(message, ok))
            if not ok:
                await self._emit(run_id, "warning", f"{name}: stopping sequence after message {index + 1}")
                break
            did_work = True

        if did_work and allow_push:
            await git_manager.push(cwd, branch)
            await self._emit(run_id, "info", f"{name}: pushed {branch}")
        elif did_work:
            await self._emit(
                run_id,
                "info",
                f"{name}: commits left on {branch} (push auto désactivé — review manuelle)",
            )

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

        provider = (message.get("provider") or "claude").strip().lower()
        model = message.get("claude_model") or message.get("model") or None
        effort = message.get("effort") or None
        fast_mode = bool(message.get("fast_mode"))

        while True:
            if self._stop_requested or self._window_passed():
                await self._set_message_status(message_id, "SKIPPED")
                self._mark_message_processed(message_id, failed=True)
                return False

            await self._set_message_status(message_id, "RUNNING")

            if provider == "cursor":
                account = self._pick_cursor_account()
                exit_code, quota_hit, reset_hint, session_id, auth_failed = await self._run_cursor(
                    run_id,
                    cwd,
                    prompt,
                    model=model,
                    effort=effort,
                    fast_mode=fast_mode,
                    cursor_account=account,
                )
                if account is not None:
                    await self._refresh_cursor_account_usage(account)
            else:
                claude_account = self._pick_claude_account()
                if claude_account is None:
                    await quota_reader.ensure_oauth_fresh()
                exit_code, quota_hit, reset_hint, session_id, auth_failed = await self._run_claude(
                    run_id,
                    cwd,
                    prompt,
                    resume_session=resume_session,
                    model=model,
                    effort=effort,
                    claude_account=claude_account,
                )
                if claude_account is not None:
                    await self._refresh_claude_account_usage(claude_account)

                if auth_failed and claude_account is None:
                    await self._emit(
                        run_id,
                        "warning",
                        "Session Claude expirée — reconnexion automatique en cours…",
                    )
                    if await quota_reader.ensure_oauth_fresh():
                        exit_code, quota_hit, reset_hint, session_id, auth_failed = (
                            await self._run_claude(
                                run_id,
                                cwd,
                                prompt,
                                resume_session=resume_session,
                                model=model,
                                effort=effort,
                            )
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

            if quota_hit and provider != "cursor":
                if self._run_state is not None:
                    self._run_state.quotas_consumed += 1
                self._last_reset_hint = reset_hint
                await self._set_run_status(run_id, "WAITING_QUOTA")
                await self._client.send({"type": "status", "status": "WAITING_QUOTA"})
                await self._emit(run_id, "warning", "Quota hit — waiting for reset")
                resumed = await self._wait_for_quota(reset_hint)
                if not resumed:
                    await self._set_message_status(message_id, "SKIPPED")
                    self._mark_message_processed(message_id, failed=True)
                    return False
                if self._quota_budget_exhausted():
                    await self._emit(run_id, "info", "Quota budget exhausted after reset wait")
                    await self._set_message_status(message_id, "SKIPPED")
                    self._mark_message_processed(message_id, failed=True)
                    return False
                await self._set_run_status(run_id, "RUNNING")
                prompt = DEFAULT_CONTINUE_PROMPT
                continue

            if exit_code == 0:
                self._failures = 0
                await self._set_message_status(message_id, "DONE")
                self._mark_message_processed(message_id, failed=False)
                return True

            self._failures += 1
            await self._set_message_status(message_id, "FAILED", f"exit code {exit_code}")
            self._mark_message_processed(message_id, failed=True)
            await self._emit(run_id, "error", f"Message failed (exit {exit_code})")
            return False

    def _mark_message_processed(self, message_id: Optional[int], *, failed: bool) -> None:
        """Record that a message reached a terminal status during this run."""
        if message_id is None or self._run_state is None:
            return
        self._run_state.processed_message_ids.add(int(message_id))
        if failed:
            self._run_state.had_message_failure = True

    async def _run_claude(
        self,
        run_id: int,
        cwd: str,
        prompt: str,
        resume_session: Optional[str] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        claude_account: Optional[dict] = None,
    ) -> tuple[int, bool, Optional[datetime], Optional[str], bool]:
        """
        Stream one Claude invocation, emitting output as events.

        Args:
            run_id: The active run id.
            cwd: Working directory.
            prompt: Prompt text.
            resume_session: Optional session UUID to resume.
            model: Optional Claude model alias.
            effort: Optional effort level.
            claude_account: Vaulted account to use instead of the machine's own session.

        Returns:
            Tuple of exit code, quota hit, reset hint, session id and auth-failure flag.
        """
        exit_code = 0
        quota_hit = False
        reset_hint: Optional[datetime] = None
        session_id: Optional[str] = resume_session
        auth_failed = False

        if claude_account is not None:
            access_token = claude_account.get("access_token")
            label = str(
                claude_account.get("label") or claude_account.get("email") or f"#{claude_account.get('id')}"
            )
            await self._emit(run_id, "info", f"Claude — compte={label}")
        else:
            access_token = oauth_credentials.current_access_token()

        async for line in claude_runner.run_prompt(
            self._config.claude_bin,
            cwd,
            prompt,
            resume_session=resume_session,
            model=model,
            effort=effort,
            access_token=access_token,
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

    def _pick_cursor_account(self) -> Optional[dict]:
        """
        Choose the vaulted Cursor account with the lowest average utilization.

        Returns:
            Account dict from the run payload, or None to use the machine default.
        """
        if self._run_state is None:
            return None
        accounts = list(self._run_state.cursor_accounts or [])
        if not accounts:
            return None

        scored: list[tuple[float, dict]] = []
        for account in accounts:
            auto_u = account.get("auto_utilization")
            api_u = account.get("api_utilization")
            values = [float(v) for v in (auto_u, api_u) if isinstance(v, (int, float))]
            if not values:
                scored.append((0.99, account))
                continue
            avg = sum(values) / len(values)
            if avg >= 0.999:
                continue
            scored.append((avg, account))

        if not scored:
            # All exhausted — still try the lowest so the CLI can fail loudly.
            fallback = sorted(
                accounts,
                key=lambda a: (
                    (
                        (float(a["auto_utilization"]) if isinstance(a.get("auto_utilization"), (int, float)) else 1.0)
                        + (float(a["api_utilization"]) if isinstance(a.get("api_utilization"), (int, float)) else 1.0)
                    )
                    / 2.0
                ),
            )
            return fallback[0] if fallback else None

        scored.sort(key=lambda item: item[0])
        return scored[0][1]

    def _pick_claude_account(self) -> Optional[dict]:
        """
        Choose the vaulted Claude account with the lowest five-hour utilization.

        Returns:
            Account dict from the run payload, or None to use the machine's own session.
        """
        if self._run_state is None:
            return None
        accounts = [
            a for a in (self._run_state.claude_accounts or []) if a.get("access_token")
        ]
        if not accounts:
            return None

        scored: list[tuple[float, dict]] = []
        for account in accounts:
            five_u = account.get("five_hour_utilization")
            if not isinstance(five_u, (int, float)):
                scored.append((0.99, account))
                continue
            if float(five_u) >= 0.999:
                continue
            scored.append((float(five_u), account))

        if not scored:
            # All exhausted — still try the lowest so the CLI can fail loudly.
            fallback = sorted(
                accounts,
                key=lambda a: (
                    float(a["five_hour_utilization"])
                    if isinstance(a.get("five_hour_utilization"), (int, float))
                    else 1.0
                ),
            )
            return fallback[0] if fallback else None

        scored.sort(key=lambda item: item[0])
        return scored[0][1]

    async def _refresh_claude_account_usage(self, account: dict) -> None:
        """
        Best-effort re-read Claude Max usage for the account just used (in-memory cache).

        Args:
            account: Mutable account dict from ``claude_accounts``.
        """
        access_token = account.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            return
        try:
            readings = await quota_reader.read_usage_for_access_token(access_token)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Post-prompt Claude usage refresh failed: %s", exc)
            return
        for reading in readings:
            if reading.bucket == "five_hour":
                account["five_hour_utilization"] = reading.utilization
            elif reading.bucket == "seven_day":
                account["seven_day_utilization"] = reading.utilization
            elif reading.bucket == "seven_day_opus":
                account["seven_day_opus_utilization"] = reading.utilization

    async def _refresh_cursor_account_usage(self, account: dict) -> None:
        """
        Best-effort re-read plan usage for the account just used and update in-memory cache.

        Args:
            account: Mutable account dict from ``cursor_accounts``.
        """
        token = account.get("session_token")
        if not isinstance(token, str) or not token.strip():
            return
        try:
            buckets = await cursor_usage_reader.read_cursor_usage_for_token(token)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Post-prompt Cursor usage refresh failed: %s", exc)
            return
        for bucket in buckets:
            if bucket.bucket == "cursor_auto":
                account["auto_utilization"] = bucket.utilization
            elif bucket.bucket == "cursor_api":
                account["api_utilization"] = bucket.utilization

    async def _run_cursor(
        self,
        run_id: int,
        cwd: str,
        prompt: str,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        fast_mode: bool = False,
        cursor_account: Optional[dict] = None,
    ) -> tuple[int, bool, Optional[datetime], Optional[str], bool]:
        """
        Stream one Cursor Agent invocation.

        Returns:
            Same tuple shape as ``_run_claude`` (quota/session unused for Cursor).
        """
        exit_code = 0
        api_key = None
        session_token = None
        label = "machine locale"
        if cursor_account:
            api_key = cursor_account.get("api_key")
            session_token = cursor_account.get("session_token")
            label = str(
                cursor_account.get("label")
                or cursor_account.get("email")
                or f"#{cursor_account.get('id')}"
            )
        else:
            # No vault pick — still try silent IDE session auth.
            local_token, local_email = cursor_usage_reader.export_local_session()
            if local_token:
                session_token = local_token
                label = f"IDE locale ({local_email})" if local_email else "IDE locale"

        await self._emit(
            run_id,
            "info",
            f"Cursor Agent — compte={label} model={model or 'default'} "
            f"effort={effort or '-'} fast={fast_mode}",
        )
        try:
            async for line in cursor_runner.run_prompt(
                self._config.cursor_bin,
                cwd,
                prompt,
                model=model,
                effort=effort,
                fast_mode=fast_mode,
                api_key=api_key if isinstance(api_key, str) else None,
                session_token=session_token if isinstance(session_token, str) else None,
            ):
                if line.startswith("__NF_RESULT__:"):
                    parts = line.split(":", 4)
                    exit_code = int(parts[1]) if len(parts) > 1 and parts[1] else 0
                    continue
                await self._emit(run_id, "info", line)
        except (cursor_runner.CursorBinNotFoundError, cursor_runner.CursorInstallError) as exc:
            logger.error("Cursor CLI unavailable: %s", exc)
            await self._emit(run_id, "error", str(exc))
            return 127, False, None, None, False

        return exit_code, False, None, None, False

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
