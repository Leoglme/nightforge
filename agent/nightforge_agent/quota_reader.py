"""
Quota reader — reads the Claude Max usage buckets so the control-plane can plan.

Strategies (in order):

1. OAuth usage API (``GET api.anthropic.com/api/oauth/usage``) via ``~/.claude/.credentials.json``.
2. Recent Claude Code session transcripts (rate-limit lines from an open desktop/CLI session).
3. A ``resets_at`` hint captured live by :mod:`claude_runner` during a run.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from . import oauth_credentials
from .claude_runner import parse_reset_hint

logger = logging.getLogger(__name__)

OAUTH_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA_HEADER = "oauth-2025-04-20"
CLAUDE_USER_AGENT = oauth_credentials.CLAUDE_USER_AGENT

_CACHE_TTL_SECONDS = 60
_cache_expires_at = 0.0
_cache_reading: Optional["QuotaReading"] = None
_repair_task: Optional[asyncio.Task] = None


@dataclass
class QuotaReading:
    """
    A single quota bucket reading.

    Attributes:
        bucket: Bucket key (e.g. ``five_hour``).
        utilization: Fraction used 0.0 -> 1.0.
        resets_at: When the bucket next rolls off, if known.
    """

    bucket: str
    utilization: float
    resets_at: Optional[datetime]
    auth_error: Optional[str] = field(default=None)


def _claude_config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))


def _credentials_path() -> Path:
    return _claude_config_dir() / ".credentials.json"


def _normalize_utilization(value: float) -> float:
    if value > 1.0:
        return min(value / 100.0, 1.0)
    return min(max(value, 0.0), 1.0)


def _parse_event_timestamp(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_resets_at(raw: Any) -> Optional[datetime]:
    """
    Parse a bucket reset time from OAuth (ISO string or Unix epoch seconds).

    Args:
        raw: Value from the usage API.

    Returns:
        Timezone-aware UTC datetime, or None.
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), tz=timezone.utc)
    if isinstance(raw, str):
        parsed = _parse_event_timestamp(raw)
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _parse_five_hour_bucket(payload: dict[str, Any]) -> Optional[QuotaReading]:
    """
    Extract the rolling 5-hour session bucket from an OAuth usage payload.

    Supports the newer ``limits[]`` shape (``kind: session``) and the legacy
    flat ``five_hour`` key.
    """
    limits = payload.get("limits")
    if isinstance(limits, list):
        for entry in limits:
            if not isinstance(entry, dict) or entry.get("kind") != "session":
                continue
            utilization = entry.get("percent")
            if utilization is None:
                utilization = entry.get("utilization")
            if utilization is None:
                utilization = entry.get("used_percentage")
            if not isinstance(utilization, (int, float)):
                continue
            return QuotaReading(
                bucket="five_hour",
                utilization=_normalize_utilization(float(utilization)),
                resets_at=_parse_resets_at(entry.get("resets_at")),
            )

    bucket = payload.get("five_hour")
    if not isinstance(bucket, dict):
        return None

    utilization = bucket.get("utilization")
    if utilization is None:
        utilization = bucket.get("used_percentage")
    if utilization is None:
        utilization = bucket.get("percent")
    if not isinstance(utilization, (int, float)):
        return None

    return QuotaReading(
        bucket="five_hour",
        utilization=_normalize_utilization(float(utilization)),
        resets_at=_parse_resets_at(bucket.get("resets_at")),
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _reading_is_actionable(reading: QuotaReading) -> bool:
    """Ignore transcript hints whose reset time is already in the past."""
    if reading.resets_at is None:
        return reading.utilization > 0
    reset_at = reading.resets_at
    if reset_at.tzinfo is None:
        reset_at = reset_at.replace(tzinfo=timezone.utc)
    return reset_at > _utc_now()


def _load_oauth_block() -> Optional[dict[str, Any]]:
    return oauth_credentials.load_oauth_block_with_fallback()


def _token_expired(oauth: dict[str, Any], buffer_seconds: int = 60) -> bool:
    return oauth_credentials.token_expired(oauth, buffer_seconds)


def _write_oauth_block(oauth: dict[str, Any]) -> None:
    oauth_credentials.write_oauth_block(oauth)


async def _refresh_oauth_token(oauth: dict[str, Any]) -> Optional[dict[str, Any]]:
    return await oauth_credentials.refresh_oauth_token(oauth)


async def _fetch_oauth_usage(access_token: str) -> Optional[QuotaReading]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "anthropic-beta": OAUTH_BETA_HEADER,
        "User-Agent": CLAUDE_USER_AGENT,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(OAUTH_USAGE_URL, headers=headers)
    except httpx.HTTPError as exc:
        logger.debug("OAuth usage request failed: %s", exc)
        return None

    if response.status_code != 200:
        logger.debug("OAuth usage rejected (%s): %s", response.status_code, response.text[:200])
        return None

    payload = response.json()
    if not isinstance(payload, dict):
        return None
    return _parse_five_hour_bucket(payload)


async def _kickoff_repair_if_needed() -> bool:
    """Start background OAuth repair when credentials are unusable."""
    global _repair_task

    oauth = _load_oauth_block()
    if oauth_credentials.credentials_usable(oauth):
        return False

    if _repair_task is not None and not _repair_task.done():
        return True

    async def _run_repair() -> None:
        await oauth_credentials.repair_oauth_session()
        invalidate_cache()

    _repair_task = asyncio.create_task(_run_repair())
    return True


async def _read_oauth_usage() -> Optional[QuotaReading]:
    oauth = await oauth_credentials.ensure_valid_oauth(auto_repair=False)
    if not oauth_credentials.credentials_usable(oauth):
        repairing = await _kickoff_repair_if_needed()
        auth_error = oauth_credentials.oauth_unavailable_reason(oauth, repairing=repairing)
        return QuotaReading(
            bucket="five_hour",
            utilization=0.0,
            resets_at=None,
            auth_error=auth_error,
        )

    assert oauth is not None
    access_token = oauth["accessToken"]
    reading = await _fetch_oauth_usage(access_token)
    if reading is not None:
        return reading

    refreshed = await _refresh_oauth_token(oauth)
    if refreshed is None:
        repairing = await _kickoff_repair_if_needed()
        return QuotaReading(
            bucket="five_hour",
            utilization=0.0,
            resets_at=None,
            auth_error=oauth_credentials.oauth_unavailable_reason(oauth, repairing=repairing),
        )
    return await _fetch_oauth_usage(refreshed["accessToken"])


def _session_limit_markers(line: str) -> bool:
    lowered = line.lower()
    return (
        "session limit" in lowered
        or "rate_limit" in lowered
        or "usage limit" in lowered
        or "réinitialisation" in lowered
        or "resets " in lowered
    )


def _extract_text_blob(entry: dict[str, Any]) -> str:
    chunks: list[str] = []
    message = entry.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
    for key in ("content", "text", "result"):
        value = entry.get(key)
        if isinstance(value, str):
            chunks.append(value)
    return "\n".join(chunks)


def _scan_session_transcripts(max_age_hours: int = 24) -> Optional[QuotaReading]:
    projects_dir = _claude_config_dir() / "projects"
    if not projects_dir.is_dir():
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    best_reset: Optional[datetime] = None
    best_seen_at: Optional[datetime] = None

    for jsonl_path in projects_dir.rglob("*.jsonl"):
        try:
            if datetime.fromtimestamp(jsonl_path.stat().st_mtime, tz=timezone.utc) < cutoff:
                continue
            tail = jsonl_path.read_text(encoding="utf-8", errors="replace").splitlines()[-80:]
        except OSError:
            continue

        for raw_line in reversed(tail):
            if not _session_limit_markers(raw_line):
                continue
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            blob = _extract_text_blob(entry)
            if not blob:
                continue

            seen_at = _parse_event_timestamp(entry.get("timestamp"))
            if seen_at is None:
                seen_at = datetime.fromtimestamp(jsonl_path.stat().st_mtime, tz=timezone.utc)

            reset_at = parse_reset_hint(blob, now=seen_at.astimezone().replace(tzinfo=None))
            if reset_at is None:
                continue

            if best_seen_at is None or seen_at > best_seen_at:
                best_seen_at = seen_at
                best_reset = reset_at

    if best_reset is None:
        return None

    reading = QuotaReading(bucket="five_hour", utilization=1.0, resets_at=best_reset)
    if not _reading_is_actionable(reading):
        return None
    return reading


def invalidate_cache() -> None:
    """Drop the cached OAuth reading so the next poll fetches live data."""
    global _cache_expires_at, _cache_reading
    _cache_expires_at = 0.0
    _cache_reading = None


async def ensure_oauth_fresh() -> bool:
    """
    Ensure Claude OAuth credentials are valid before a CLI run.

    Returns:
        True when a valid access token is available (may wait for auto-repair).
    """
    oauth = await oauth_credentials.ensure_valid_oauth(auto_repair=True)
    return oauth_credentials.credentials_usable(oauth)


async def read_five_hour(last_reset_hint: Optional[datetime] = None) -> Optional[QuotaReading]:
    """
    Read (or infer) the current five-hour quota bucket.

    Args:
        last_reset_hint: A ``resets_at`` parsed from recent Claude CLI output, if any.

    Returns:
        A :class:`QuotaReading` when a real signal is available, else None.
    """
    global _cache_expires_at, _cache_reading

    now = time.monotonic()
    if _cache_reading is not None and now < _cache_expires_at:
        return _cache_reading

    reading = await _read_oauth_usage()
    if reading is not None and reading.auth_error and reading.resets_at is None:
        _cache_reading = reading
        _cache_expires_at = now + 15
        return reading

    if reading is None or (reading.resets_at is None and reading.utilization <= 0):
        transcript = _scan_session_transcripts()
        if transcript is not None:
            reading = transcript
    if reading is None and last_reset_hint is not None:
        hint_reading = QuotaReading(bucket="five_hour", utilization=1.0, resets_at=last_reset_hint)
        if _reading_is_actionable(hint_reading):
            reading = hint_reading

    if reading is not None:
        # Normalize the reset to timezone-aware UTC. The OAuth path is already aware; the
        # transcript / CLI-hint paths produce naive *local* datetimes, so interpret those as
        # local before converting — otherwise the control-plane and UI show a shifted hour.
        if reading.resets_at is not None and reading.resets_at.tzinfo is None:
            reading = QuotaReading(
                bucket=reading.bucket,
                utilization=reading.utilization,
                resets_at=reading.resets_at.astimezone(timezone.utc),
                auth_error=reading.auth_error,
            )
        if not _reading_is_actionable(reading) and reading.auth_error is None:
            reading = None

    if reading is not None:
        _cache_reading = reading
        _cache_expires_at = now + _CACHE_TTL_SECONDS

    return reading
