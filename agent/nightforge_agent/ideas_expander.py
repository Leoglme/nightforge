"""
Ideas expander — run Cursor / Claude locally to turn keywords into queue prompts.
"""
from __future__ import annotations

import json
import logging
import re
import tempfile
from typing import Any, Optional

from . import claude_runner, cursor_runner

logger = logging.getLogger(__name__)

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_JSON_OBJECT = re.compile(r"\{[\s\S]*\}")


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """
    Best-effort extract of a JSON object from model output.

    Args:
        text: Full stdout from the CLI.

    Returns:
        Parsed dict, or None.
    """
    if not text:
        return None

    fence = _JSON_FENCE.search(text)
    candidates = []
    if fence:
        candidates.append(fence.group(1))
    match = _JSON_OBJECT.search(text)
    if match:
        candidates.append(match.group(0))

    for raw in candidates:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return data
    return None


async def _run_cursor(cursor_bin: str, prompt: str) -> tuple[str, int]:
    """
    Run Composer 2.5 via Cursor Agent CLI.

    Args:
        cursor_bin: Cursor agent binary.
        prompt: Planning prompt.

    Returns:
        (stdout, exit_code)
    """
    cwd = tempfile.gettempdir()
    lines: list[str] = []
    exit_code = 1
    async for line in cursor_runner.run_prompt(
        cursor_bin,
        cwd,
        prompt,
        model="composer-2.5",
        effort=None,
        fast_mode=False,
    ):
        if line.startswith("__NF_RESULT__:"):
            parts = line.split(":")
            try:
                exit_code = int(parts[1])
            except (IndexError, ValueError):
                exit_code = 1
            break
        lines.append(line)
    return "\n".join(lines), exit_code


async def _run_claude(claude_bin: str, prompt: str) -> tuple[str, int]:
    """
    Run Haiku via Claude Code CLI (cheap fallback).

    Args:
        claude_bin: Claude binary.
        prompt: Planning prompt.

    Returns:
        (stdout, exit_code)
    """
    cwd = tempfile.gettempdir()
    lines: list[str] = []
    exit_code = 1
    access_token = None
    try:
        from . import oauth_credentials

        oauth = await oauth_credentials.ensure_valid_oauth(auto_repair=False)
        if oauth_credentials.credentials_usable(oauth) and oauth:
            access_token = oauth.get("accessToken")
    except Exception as exc:  # noqa: BLE001
        logger.debug("OAuth for expand ideas: %s", exc)

    async for line in claude_runner.run_prompt(
        claude_bin,
        cwd,
        prompt,
        model="haiku",
        effort="low",
        access_token=access_token,
    ):
        if line.startswith("__NF_RESULT__:"):
            parts = line.split(":")
            try:
                exit_code = int(parts[1])
            except (IndexError, ValueError):
                exit_code = 1
            break
        lines.append(line)
    return "\n".join(lines), exit_code


async def expand_ideas(
    *,
    prompt: str,
    prefer_provider: str,
    cursor_bin: str,
    claude_bin: str,
) -> dict[str, Any]:
    """
    Expand ideas using the preferred local CLI, with fallback.

    Args:
        prompt: Full planning prompt (includes system rules).
        prefer_provider: ``cursor`` or ``claude``.
        cursor_bin: Cursor Agent CLI.
        claude_bin: Claude Code CLI.

    Returns:
        Response dict for ``ideas.expand.response``.
    """
    order = ["cursor", "claude"] if prefer_provider != "claude" else ["claude", "cursor"]
    last_error: Optional[str] = None

    for provider in order:
        try:
            if provider == "cursor":
                stdout, exit_code = await _run_cursor(cursor_bin, prompt)
                model_used = "composer-2.5"
            else:
                stdout, exit_code = await _run_claude(claude_bin, prompt)
                model_used = "haiku"

            parsed = _extract_json(stdout)
            if parsed is None:
                last_error = f"{provider}: no JSON in output (exit={exit_code})"
                logger.warning("ideas.expand %s", last_error)
                continue

            return {
                "summary": parsed.get("summary"),
                "items": parsed.get("items") or [],
                "provider_used": provider,
                "model_used": model_used,
            }
        except FileNotFoundError as exc:
            last_error = f"{provider}: binary not found ({exc})"
            logger.warning("ideas.expand %s", last_error)
        except Exception as exc:  # noqa: BLE001
            last_error = f"{provider}: {exc}"
            logger.warning("ideas.expand failed via %s: %s", provider, exc, exc_info=True)

    return {
        "error": last_error or "expansion failed",
        "summary": None,
        "items": [],
        "provider_used": None,
        "model_used": None,
    }
