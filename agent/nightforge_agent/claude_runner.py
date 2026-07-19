"""
Claude Code CLI runner — spawns headless Claude, streams output, detects completion
and quota exhaustion.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import AsyncIterator, Optional

from .session_scanner import find_latest_session_id
from .stream_actions import (
    encode_action,
    extract_claude_assistant_parts,
    session_id_from_event,
    try_parse_json_line,
)

logger = logging.getLogger(__name__)

# Phrases that clearly mean Claude Max / session quota is exhausted.
# Do NOT use bare words like "quota" — they match normal assistant text and
# git diffs of this very codebase (false WAITING_QUOTA).
_QUOTA_MARKERS = (
    "you've reached your limit",
    "you've hit your limit",
    "you have reached your limit",
    "you have hit your limit",
    "usage limit reached",
    "hit your usage limit",
    "reached your usage limit",
    "session limit reached",
    "rate limit reached",
    "limite d'utilisation atteinte",
    "limite d’utilisation atteinte",
    "tu as atteint ta limite",
    "vous avez atteint votre limite",
)


def looks_like_quota_exhaustion(text: str) -> bool:
    """
    Return True only when the line clearly reports Claude quota exhaustion.

    Args:
        text: A single CLI / stream line (or short error message).

    Returns:
        Whether this should flip ``quota_hit``.
    """
    lowered = text.lower()
    if any(marker in lowered for marker in _QUOTA_MARKERS):
        return True
    # "Resets at 3pm" style — only when paired with limit/usage language.
    if ("reset" in lowered or "réinitialisation" in lowered) and (
        "limit" in lowered or "limite" in lowered or "usage" in lowered
    ):
        return True
    return False


# Best-effort patterns to extract a reset time from Claude CLI output.
_RESET_ISO = re.compile(r"resets? at[^0-9]*([0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9:]+)", re.IGNORECASE)
_RESET_CLOCK = re.compile(
    r"resets?(?:\s+at)?[^0-9]*([0-9]{1,2})(?::|h)([0-9]{2})\s*([ap]m)?",
    re.IGNORECASE,
)
_RESET_SIMPLE_MERIDIEM = re.compile(
    r"resets?\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
    re.IGNORECASE,
)
_RESET_FR = re.compile(r"réinitialisation\s+à\s+([0-9]{1,2})h([0-9]{2})", re.IGNORECASE)

_AUTH_MARKERS = (
    "401",
    "invalid authentication",
    "authentication credentials",
    "not authenticated",
    "please log in",
    "oauth token",
)

DEFAULT_CONTINUE_PROMPT = "Vas-y, continue là où tu t'étais arrêté."


def claude_subprocess_env(access_token: Optional[str] = None) -> dict[str, str]:
    """
    Environment for Claude Code subprocesses spawned by the NightForge agent.

    Injects a fresh OAuth token when provided so Claude Code does not depend on a global
    ``apiKeyHelper`` (which would run on every Cursor / Claude Code tab).
    """
    env = os.environ.copy()
    if access_token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = access_token
    else:
        env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    return env


def parse_reset_hint(line: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """
    Try to extract a quota reset timestamp from a Claude CLI output line.

    Args:
        line: A single output line.
        now: Reference time (defaults to ``datetime.now``), used to resolve clock-only hints.

    Returns:
        The next reset datetime if one could be parsed, else None.
    """
    now = now or datetime.now()

    iso_match = _RESET_ISO.search(line)
    if iso_match:
        try:
            return datetime.fromisoformat(iso_match.group(1).replace("T", " ").strip())
        except ValueError:
            pass

    for pattern in (_RESET_CLOCK, _RESET_FR):
        clock_match = pattern.search(line)
        if not clock_match:
            continue
        hour = int(clock_match.group(1))
        minute = int(clock_match.group(2) or 0)
        meridiem = (clock_match.group(3) or "").lower() if clock_match.lastindex and clock_match.lastindex >= 3 else ""
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        candidate = now.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    simple_match = _RESET_SIMPLE_MERIDIEM.search(line)
    if simple_match:
        hour = int(simple_match.group(1))
        minute = int(simple_match.group(2) or 0)
        meridiem = (simple_match.group(3) or "").lower()
        if meridiem == "pm" and hour < 12:
            hour += 12
        elif meridiem == "am" and hour == 12:
            hour = 0
        candidate = now.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    return None


def looks_like_auth_failure(line: str) -> bool:
    """
    Detect Claude CLI output that indicates expired or missing OAuth credentials.

    Args:
        line: A single output line.

    Returns:
        True when the line suggests an authentication problem.
    """
    lowered = line.lower()
    return any(marker in lowered for marker in _AUTH_MARKERS)


@dataclass
class ClaudeResult:
    """
    Outcome of a single Claude Code invocation.

    Attributes:
        exit_code: Process exit code.
        quota_hit: True if output indicates the quota was exhausted.
        output: Captured combined output (truncated by the caller if needed).
        session_id: Claude session UUID if one could be determined.
    """

    exit_code: int
    quota_hit: bool
    output: str
    session_id: Optional[str] = None


async def run_prompt(
    claude_bin: str,
    cwd: str,
    prompt: str,
    resume_session: Optional[str] = None,
    continue_session: bool = False,
    model: Optional[str] = None,
    effort: Optional[str] = None,
    access_token: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    Run a prompt through Claude Code in headless mode, yielding output lines.

    The final yielded line is a sentinel of the form
    ``__NF_RESULT__:<exit>:<quota_hit>:<reset_iso>:<session_id>``
    so callers can build a :class:`ClaudeResult` while still streaming logs live.

    Args:
        claude_bin: Path or name of the Claude CLI.
        cwd: Working directory (the project clone).
        prompt: The prompt to send.
        resume_session: Optional Claude session id to resume.
        continue_session: Resume the most recent conversation in ``cwd`` (``-c``).
        model: Optional model alias (fable, opus, sonnet, haiku).
        effort: Optional effort level (low, medium, high, xhigh, max).
        access_token: OAuth access token for this subprocess (NightForge agent only).

    Yields:
        Output lines, then a final sentinel line.
    """
    started_at = time.time()
    # stream-json + verbose → tool_use blocks (Edit/Write/Read) for code review UI.
    args = [
        claude_bin,
        "-p",
        prompt,
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    if model:
        args += ["--model", model]
    if effort:
        args += ["--effort", effort]
    if resume_session:
        args += ["--resume", resume_session]
    elif continue_session:
        args += ["--continue"]

    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        env=claude_subprocess_env(access_token),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    quota_hit = False
    reset_hint: Optional[datetime] = None
    session_id = resume_session
    assert process.stdout is not None
    async for raw in process.stdout:
        line = raw.decode(errors="replace").rstrip("\n")

        event = try_parse_json_line(line)
        if event is None:
            # Non-JSON fallback (older CLI / noise) — keep raw log line.
            if line.strip():
                if looks_like_quota_exhaustion(line):
                    quota_hit = True
                    parsed = parse_reset_hint(line)
                    if parsed is not None:
                        reset_hint = parsed
                yield line
            continue

        sid = session_id_from_event(event)
        if sid:
            session_id = sid

        if event.get("type") == "result":
            # Prefer already-streamed assistant text; only surface hard errors here.
            err_msg = str(event.get("error") or event.get("result") or "")
            if event.get("is_error") or event.get("subtype") == "error":
                if err_msg.strip():
                    if looks_like_quota_exhaustion(err_msg):
                        quota_hit = True
                        parsed = parse_reset_hint(err_msg)
                        if parsed is not None:
                            reset_hint = parsed
                    yield err_msg
            elif err_msg and looks_like_quota_exhaustion(err_msg):
                # Successful result payload that still embeds a limit notice.
                quota_hit = True
                parsed = parse_reset_hint(err_msg)
                if parsed is not None:
                    reset_hint = parsed
            continue

        # Never scan full stream-json blobs for quota (tool_result / diffs contain "quota").
        texts, actions = extract_claude_assistant_parts(event)
        for text in texts:
            if text.strip():
                # Short system-style notices only — not long code reviews.
                if len(text) < 400 and looks_like_quota_exhaustion(text):
                    quota_hit = True
                    parsed = parse_reset_hint(text)
                    if parsed is not None:
                        reset_hint = parsed
                yield text
        for action in actions:
            yield encode_action(action)

    exit_code = await process.wait()
    if session_id is None:
        session_id = find_latest_session_id(cwd, started_at)
    reset_iso = reset_hint.isoformat() if reset_hint else ""
    session_part = session_id or ""
    yield f"__NF_RESULT__:{exit_code}:{int(quota_hit)}:{reset_iso}:{session_part}"
