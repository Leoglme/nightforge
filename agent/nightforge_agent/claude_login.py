"""
Claude account capture via ``claude auth login``, without leaving the machine on the
wrong account.

The Claude CLI does not support isolated profiles the way a browser does, so capturing an
*additional* account means: back up the current ``~/.claude/.credentials.json`` OAuth block,
launch ``claude auth login`` for the new account, wait until a **different** access token
appears on disk, capture it, then immediately restore the backup — the machine's own Claude
session is never actually left signed into the new account.

The login subprocess is launched in the background (non-blocking `Popen`); a small reader
thread only drains its stdout (to grab the login URL and avoid pipe back-pressure) so the
main asyncio loop is never blocked. Polling is a plain async function that reads the
credentials file — safe to call from the worker's WebSocket loop directly.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from . import oauth_credentials

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+")
_START_GRACE_SEC = 3.0
_STALL_ERROR_AFTER_SEC = 8.0

_sessions: dict[str, "LoginSession"] = {}
_sessions_lock = threading.Lock()


@dataclass
class LoginSession:
    """Thread-safe state for an in-progress ``claude auth login`` capture."""

    id: str
    baseline_token: Optional[str]
    backup_snapshot: Optional[dict[str, Any]]
    started_at: float = field(default_factory=time.monotonic)
    process: Optional["subprocess.Popen[bytes]"] = None
    login_url: Optional[str] = None
    finished: bool = False
    error: Optional[str] = None
    captured_oauth: Optional[dict[str, Any]] = None
    captured_email: Optional[str] = None
    restored: bool = False
    thread: Optional[threading.Thread] = None
    _lock: threading.Lock = field(default_factory=threading.Lock)


def _reader_thread(session: LoginSession) -> None:
    """Drain the CLI's stdout in its own thread — no event loop needed for this."""
    process = session.process
    if process is None or process.stdout is None:
        return
    try:
        for raw in process.stdout:
            line = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
            match = _URL_RE.search(line)
            if match:
                with session._lock:
                    if not session.login_url:
                        session.login_url = match.group(0).rstrip(").,]}\"'")
    except Exception as exc:  # noqa: BLE001
        logger.debug("Claude login reader thread stopped: %s", exc)
    finally:
        try:
            process.wait(timeout=5.0)
        except Exception:  # noqa: BLE001
            pass


def _spawn(claude_bin: str) -> "subprocess.Popen[bytes]":
    """Start ``claude auth login`` detached, capturing merged stdout/stderr."""
    binary = shutil.which(claude_bin) or claude_bin
    env = os.environ.copy()

    popen_kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "env": env,
    }
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        popen_kwargs["start_new_session"] = True
    return subprocess.Popen([binary, "auth", "login"], **popen_kwargs)


async def start_login(claude_bin: str, *, keep_on_machine: bool = False) -> dict[str, Any]:
    """
    Launch ``claude auth login`` for a new account while keeping the current one safe.

    Args:
        claude_bin: Path or name of the Claude CLI.
        keep_on_machine: When True (machine first connect / re-import), leave the
            newly logged-in session on disk instead of restoring a previous account.

    Returns:
        Dict with ``login_id``, ``status``, ``login_url``/``note``/``error``.
    """
    with _sessions_lock:
        stale_ids = list(_sessions.keys())
    for stale_id in stale_ids:
        await cancel_login(stale_id)

    baseline_oauth = oauth_credentials.load_oauth_block_with_fallback()
    baseline_usable = oauth_credentials.credentials_usable(baseline_oauth)
    baseline_token = (
        baseline_oauth.get("accessToken")
        if baseline_usable and isinstance(baseline_oauth, dict)
        else None
    )
    # Only back up a *usable* machine session. An empty/stale credentials file must
    # never be restored after a successful login (would wipe the new session).
    backup_snapshot = (
        None
        if keep_on_machine or not baseline_usable
        else oauth_credentials.export_oauth_snapshot()
    )

    login_id = str(uuid.uuid4())
    session = LoginSession(
        id=login_id,
        baseline_token=baseline_token if isinstance(baseline_token, str) else None,
        backup_snapshot=backup_snapshot,
    )

    try:
        session.process = _spawn(claude_bin)
    except OSError as exc:
        return {
            "login_id": None,
            "status": "error",
            "mode": "cli",
            "error": f"Impossible de démarrer « claude auth login » : {exc}",
        }

    thread = threading.Thread(
        target=_reader_thread,
        args=(session,),
        name=f"claude-login-{login_id[:8]}",
        daemon=True,
    )
    session.thread = thread
    thread.start()

    with _sessions_lock:
        _sessions[login_id] = session

    # Brief grace window so an already-printed URL is available on the first response.
    await asyncio.sleep(_START_GRACE_SEC)

    with session._lock:
        login_url = session.login_url

    # Do not call webbrowser.open here: ``claude auth login`` already opens one tab.
    # We only surface ``login_url`` so the UI can offer a manual reopen link.

    if keep_on_machine or not baseline_usable:
        note = (
            "Connecte-toi avec ton compte Claude dans la fenêtre qui s'ouvre — "
            "cette session restera active sur la machine une fois la connexion terminée."
        )
    else:
        note = (
            "Connecte-toi avec le NOUVEAU compte Claude dans la fenêtre qui s'ouvre — "
            "la session de cette machine sera restaurée automatiquement une fois la capture terminée."
        )

    return {
        "login_id": login_id,
        "login_url": login_url,
        "status": "pending",
        "mode": "cli",
        "keep_on_machine": keep_on_machine or not baseline_usable,
        "note": note,
    }


def _snapshot(session: LoginSession) -> dict[str, Any]:
    with session._lock:
        return {
            "login_url": session.login_url,
            "finished": session.finished,
            "error": session.error,
            "captured_oauth": session.captured_oauth,
            "captured_email": session.captured_email,
            "elapsed_seconds": int(time.monotonic() - session.started_at),
        }


def _capture_and_restore(session: LoginSession, oauth: dict[str, Any]) -> None:
    """Store the newly captured OAuth block, then restore the machine's own session."""
    with session._lock:
        if session.captured_oauth is not None:
            return
        session.captured_oauth = dict(oauth)
        session.captured_email = oauth_credentials.email_from_oauth(oauth)
        session.finished = True

    if session.backup_snapshot is not None:
        oauth_credentials.restore_oauth_snapshot(session.backup_snapshot)
        with session._lock:
            session.restored = True
        logger.info(
            "Claude account captured (email=%s) — machine session restored",
            session.captured_email or "unknown",
        )
    else:
        logger.warning(
            "Claude account captured but no prior session snapshot existed — nothing to restore"
        )


async def poll_login(login_id: str) -> dict[str, Any]:
    """
    Check whether a new Claude account finished logging in.

    Args:
        login_id: Id returned by :func:`start_login`.

    Returns:
        ``{"status": "ready", "oauth": {...}, "email": "..."}`` once captured, a
        ``pending`` dict while waiting, or an ``error`` dict.
    """
    with _sessions_lock:
        session = _sessions.get(login_id)
    if session is None:
        return {"status": "error", "error": "Session de login Claude inconnue ou expirée"}

    snap = _snapshot(session)
    if snap["captured_oauth"] is not None:
        return {
            "status": "ready",
            "oauth": snap["captured_oauth"],
            "email": snap["captured_email"],
        }

    current = oauth_credentials.load_oauth_block_with_fallback()
    current_token = current.get("accessToken") if current else None
    if (
        isinstance(current_token, str)
        and current_token
        and current_token != session.baseline_token
        and oauth_credentials.credentials_usable(current)
    ):
        assert current is not None
        _capture_and_restore(session, current)
        snap = _snapshot(session)
        return {
            "status": "ready",
            "oauth": snap["captured_oauth"],
            "email": snap["captured_email"],
        }

    process = session.process
    if process is not None and process.poll() is not None and not snap["finished"]:
        if snap["elapsed_seconds"] > _STALL_ERROR_AFTER_SEC:
            with session._lock:
                session.finished = True
                session.error = (
                    "Le processus « claude auth login » s'est terminé sans nouvelle "
                    "connexion détectée."
                )
            return {"status": "error", "error": session.error}

    if snap["error"] and snap["finished"]:
        return {"status": "error", "error": snap["error"]}

    return {
        "status": "pending",
        "login_url": snap["login_url"],
        "mode": "cli",
        "elapsed_seconds": snap["elapsed_seconds"],
    }


async def complete_login(login_id: str) -> dict[str, Any]:
    """
    Manual confirm — usually unnecessary (auto-capture via :func:`poll_login`).

    Gives the capture a short extra window, then reports clearly.
    """
    result = await poll_login(login_id)
    if result.get("status") in ("ready", "error"):
        return result

    deadline = time.monotonic() + 8.0
    while time.monotonic() < deadline:
        await asyncio.sleep(0.5)
        result = await poll_login(login_id)
        if result.get("status") in ("ready", "error"):
            return result

    return {
        "status": "error",
        "error": (
            "Connexion non détectée. Termine la connexion dans la fenêtre Claude, "
            "puis réessaie."
        ),
    }


async def cancel_login(login_id: str) -> dict[str, Any]:
    """Cancel capture, kill the CLI process and restore the previous machine session."""
    with _sessions_lock:
        session = _sessions.pop(login_id, None)
    if session is None:
        return {"status": "ok"}

    process = session.process
    if process is not None and process.poll() is None:
        try:
            process.terminate()
            await asyncio.to_thread(process.wait, 5.0)
        except Exception:  # noqa: BLE001
            try:
                process.kill()
            except Exception:  # noqa: BLE001
                pass

    with session._lock:
        already_restored = session.restored
        backup = session.backup_snapshot

    if not already_restored and backup is not None:
        oauth_credentials.restore_oauth_snapshot(backup)

    return {"status": "ok"}
