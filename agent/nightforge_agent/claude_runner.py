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

logger = logging.getLogger(__name__)

# Substrings that hint the 5-hour quota was hit (best-effort; refine on real output).
_QUOTA_MARKERS = (
    "usage limit",
    "rate limit",
    "quota",
    "session limit",
    "you've reached your limit",
    "you've hit your",
    "resets at",
    "resets ",
    "réinitialisation",
    "limite d'utilisation",
    "try again later",
)

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


def claude_subprocess_env() -> dict[str, str]:
    """
    Environment for Claude Code subprocesses.

    Strips static OAuth env vars so Claude uses NightForge's rotating apiKeyHelper instead.
    """
    env = os.environ.copy()
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

    Yields:
        Output lines, then a final sentinel line.
    """
    started_at = time.time()
    args = [claude_bin, "-p", prompt, "--dangerously-skip-permissions"]
    if model:
        args += ["--model", model]
    if resume_session:
        args += ["--resume", resume_session]
    elif continue_session:
        args += ["--continue"]

    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        env=claude_subprocess_env(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    quota_hit = False
    reset_hint: Optional[datetime] = None
    session_id = resume_session
    assert process.stdout is not None
    async for raw in process.stdout:
        line = raw.decode(errors="replace").rstrip("\n")
        lowered = line.lower()
        if any(marker in lowered for marker in _QUOTA_MARKERS):
            quota_hit = True
            parsed = parse_reset_hint(line)
            if parsed is not None:
                reset_hint = parsed
        yield line

    exit_code = await process.wait()
    if session_id is None:
        session_id = find_latest_session_id(cwd, started_at)
    reset_iso = reset_hint.isoformat() if reset_hint else ""
    session_part = session_id or ""
    yield f"__NF_RESULT__:{exit_code}:{int(quota_hit)}:{reset_iso}:{session_part}"
