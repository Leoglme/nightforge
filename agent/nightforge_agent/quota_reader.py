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
_cache_readings: Optional[list["QuotaReading"]] = None
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


def _normalize_utilization(value: float, *, from_percent: bool = False) -> float:
    """
    Normalize a raw utilization / percent to a 0.0 → 1.0 fraction.

    Anthropic's OAuth ``percent`` field is 0–100 (so ``1`` means 1 %, not 100 %).
    Legacy ``utilization`` fields are already 0–1 (or occasionally 0–100).
    """
    if from_percent:
        return min(max(float(value) / 100.0, 0.0), 1.0)
    if value > 1.0:
        return min(value / 100.0, 1.0)
    return min(max(float(value), 0.0), 1.0)


def _utilization_from_entry(entry: dict[str, Any]) -> Optional[float]:
    """Pick utilization from a limit / bucket dict, preferring ``percent`` (0–100)."""
    if "percent" in entry and isinstance(entry.get("percent"), (int, float)):
        return _normalize_utilization(float(entry["percent"]), from_percent=True)
    for key in ("utilization", "used_percentage"):
        raw = entry.get(key)
        if isinstance(raw, (int, float)):
            return _normalize_utilization(float(raw), from_percent=False)
    return None


_KIND_TO_BUCKET = {
    "session": "five_hour",
    "five_hour": "five_hour",
    "five-hour": "five_hour",
    "weekly": "seven_day",
    "weekly_all": "seven_day",
    "seven_day": "seven_day",
    "seven-day": "seven_day",
    "week": "seven_day",
    "weekly_opus": "seven_day_opus",
    "seven_day_opus": "seven_day_opus",
    "opus": "seven_day_opus",
    "oauth": "seven_day_oauth_apps",
    "oauth_apps": "seven_day_oauth_apps",
    "seven_day_oauth_apps": "seven_day_oauth_apps",
    "weekly_oauth_apps": "seven_day_oauth_apps",
}


def _bucket_from_limit_entry(entry: dict[str, Any]) -> Optional[str]:
    """
    Map a Claude ``limits[]`` entry to an internal bucket key.

    ``weekly_scoped`` (e.g. Fable / legacy Opus) is stored as ``seven_day_opus`` so
    existing columns and APIs keep working without a migration.
    """
    kind = str(entry.get("kind") or entry.get("type") or entry.get("name") or "").lower()
    if kind == "weekly_scoped":
        return "seven_day_opus"
    return _KIND_TO_BUCKET.get(kind)


def _parse_all_buckets(payload: dict[str, Any]) -> list[QuotaReading]:
    """
    Extract every known Claude Max bucket from an OAuth usage payload.

    Supports ``limits[]`` (kind/percent) and legacy flat keys.
    """
    found: dict[str, QuotaReading] = {}

    limits = payload.get("limits")
    if isinstance(limits, list):
        for entry in limits:
            if not isinstance(entry, dict):
                continue
            bucket = _bucket_from_limit_entry(entry)
            if not bucket:
                continue
            utilization = _utilization_from_entry(entry)
            if utilization is None:
                continue
            found[bucket] = QuotaReading(
                bucket=bucket,
                utilization=utilization,
                resets_at=_parse_resets_at(entry.get("resets_at")),
            )

    for flat_key, bucket in (
        ("five_hour", "five_hour"),
        ("seven_day", "seven_day"),
        ("seven_day_opus", "seven_day_opus"),
        ("seven_day_oauth_apps", "seven_day_oauth_apps"),
    ):
        if bucket in found:
            continue
        entry = payload.get(flat_key)
        if not isinstance(entry, dict):
            continue
        utilization = _utilization_from_entry(entry)
        if utilization is None:
            continue
        found[bucket] = QuotaReading(
            bucket=bucket,
            utilization=utilization,
            resets_at=_parse_resets_at(entry.get("resets_at")),
        )

    return list(found.values())


def _parse_five_hour_bucket(payload: dict[str, Any]) -> Optional[QuotaReading]:
    """
    Extract the rolling 5-hour session bucket from an OAuth usage payload.

    Supports the newer ``limits[]`` shape (``kind: session``) and the legacy
    flat ``five_hour`` key.
    """
    for reading in _parse_all_buckets(payload):
        if reading.bucket == "five_hour":
            return reading
    return None


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


async def _fetch_oauth_usage_payload(access_token: str) -> Optional[dict[str, Any]]:
    """GET the raw OAuth usage JSON, or None on failure / rate-limit."""
    if oauth_credentials.is_rate_limited():
        return None

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

    if response.status_code == 429:
        oauth_credentials._mark_rate_limited()
        return None

    if response.status_code != 200:
        logger.debug("OAuth usage rejected (%s): %s", response.status_code, response.text[:200])
        return None

    payload = response.json()
    return payload if isinstance(payload, dict) else None


async def _fetch_oauth_usage(access_token: str) -> Optional[QuotaReading]:
    payload = await _fetch_oauth_usage_payload(access_token)
    if payload is None:
        return None
    return _parse_five_hour_bucket(payload)


async def _fetch_oauth_usage_all(access_token: str) -> list[QuotaReading]:
    payload = await _fetch_oauth_usage_payload(access_token)
    if payload is None:
        return []
    return _parse_all_buckets(payload)


async def read_usage_for_access_token(access_token: str) -> list["QuotaReading"]:
    """
    Read every Claude Max bucket for an explicit OAuth access token.

    Used for vaulted multi-accounts — unlike :func:`read_all_buckets`, this never touches
    the local machine's ``.credentials.json`` and does no refresh/repair.

    Args:
        access_token: A vaulted account's OAuth access token.

    Returns:
        List of buckets (possibly empty on failure or rate-limit).
    """
    if not access_token:
        return []
    readings = await _fetch_oauth_usage_all(access_token)
    return [_aware_utc(r) for r in readings]


async def export_local_oauth() -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """
    Export the local machine's active Claude OAuth block + best-effort email.

    Returns any on-disk (or Credential Manager) block that has an ``accessToken``,
    even if currently expired. A refresh is attempted when needed, but a refresh
    failure (rate-limit, network) must not hide a real local Claude Code session —
    callers may vault the token as-is. Only returns ``(None, None)`` when no
    access token exists at all (then the UI may fall back to ``claude auth login``).

    Returns:
        ``(oauth_block, email)`` — either may be None when no session exists on disk.
    """
    oauth = oauth_credentials.load_oauth_block_with_fallback()
    if not isinstance(oauth, dict) or not str(oauth.get("accessToken") or "").strip():
        return None, None

    needs_refresh = (
        not oauth_credentials.credentials_usable(oauth)
        or oauth_credentials.token_expires_soon(oauth)
    )
    if needs_refresh and str(oauth.get("refreshToken") or "").strip():
        refreshed = await oauth_credentials.refresh_oauth_token(oauth)
        if isinstance(refreshed, dict) and str(refreshed.get("accessToken") or "").strip():
            oauth = refreshed

    email = oauth_credentials.email_from_oauth(oauth)
    return oauth, email


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

    if oauth_credentials.is_rate_limited():
        if _cache_reading is not None and _cache_reading.auth_error is None:
            return _cache_reading
        return QuotaReading(
            bucket="five_hour",
            utilization=0.0,
            resets_at=None,
            auth_error=(
                "Lecture quota temporairement limitée par l'API Claude. "
                "Nouvelle tentative automatique dans quelques instants."
            ),
        )

    if oauth_credentials.token_expired(oauth):
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

    repairing = await _kickoff_repair_if_needed()
    return QuotaReading(
        bucket="five_hour",
        utilization=0.0,
        resets_at=None,
        auth_error=oauth_credentials.oauth_unavailable_reason(oauth, repairing=repairing),
    )


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
    global _cache_expires_at, _cache_reading, _cache_readings
    _cache_expires_at = 0.0
    _cache_reading = None
    _cache_readings = None


async def ensure_oauth_fresh() -> bool:
    """
    Ensure Claude OAuth credentials are valid before a CLI run.

    Returns:
        True when a valid access token is available (may wait for auto-repair).
    """
    oauth = await oauth_credentials.ensure_valid_oauth(auto_repair=True)
    return oauth_credentials.credentials_usable(oauth)


def _aware_utc(reading: QuotaReading) -> QuotaReading:
    if reading.resets_at is not None and reading.resets_at.tzinfo is None:
        return QuotaReading(
            bucket=reading.bucket,
            utilization=reading.utilization,
            resets_at=reading.resets_at.astimezone(timezone.utc),
            auth_error=reading.auth_error,
        )
    return reading


async def read_all_buckets(last_reset_hint: Optional[datetime] = None) -> list[QuotaReading]:
    """
    Read every Claude Max bucket available from OAuth (5 h + weekly…).

    Falls back to the five-hour transcript / CLI hint path when OAuth is empty.
    """
    global _cache_expires_at, _cache_reading, _cache_readings

    now = time.monotonic()
    if _cache_readings is not None and now < _cache_expires_at:
        return list(_cache_readings)

    oauth = await oauth_credentials.ensure_valid_oauth(auto_repair=False)
    readings: list[QuotaReading] = []
    auth_error: Optional[str] = None

    if not oauth_credentials.credentials_usable(oauth):
        repairing = await _kickoff_repair_if_needed()
        auth_error = oauth_credentials.oauth_unavailable_reason(oauth, repairing=repairing)
        five = QuotaReading(
            bucket="five_hour",
            utilization=0.0,
            resets_at=None,
            auth_error=auth_error,
        )
        _cache_reading = five
        _cache_readings = [five]
        _cache_expires_at = now + 15
        return [five]

    assert oauth is not None
    readings = await _fetch_oauth_usage_all(oauth["accessToken"])
    if not readings and oauth_credentials.token_expired(oauth):
        refreshed = await _refresh_oauth_token(oauth)
        if refreshed is not None:
            readings = await _fetch_oauth_usage_all(refreshed["accessToken"])

    readings = [_aware_utc(r) for r in readings]

    five = next((r for r in readings if r.bucket == "five_hour"), None)
    if five is None or (five.resets_at is None and five.utilization <= 0):
        transcript = _scan_session_transcripts()
        if transcript is not None:
            five = _aware_utc(transcript)
            readings = [r for r in readings if r.bucket != "five_hour"] + [five]
    if five is None and last_reset_hint is not None:
        hint = QuotaReading(bucket="five_hour", utilization=1.0, resets_at=last_reset_hint)
        if _reading_is_actionable(hint):
            five = _aware_utc(hint)
            readings = [r for r in readings if r.bucket != "five_hour"] + [five]

    actionable = [
        r
        for r in readings
        if r.auth_error or _reading_is_actionable(r) or r.utilization >= 0
    ]
    # Keep zero-utilization buckets (user at 1% used → 99% remaining still useful).
    if not actionable and five is not None:
        actionable = [five]

    five_out = next((r for r in actionable if r.bucket == "five_hour"), None)
    _cache_reading = five_out
    _cache_readings = actionable
    _cache_expires_at = now + _CACHE_TTL_SECONDS
    return list(actionable)


async def read_five_hour(last_reset_hint: Optional[datetime] = None) -> Optional[QuotaReading]:
    """
    Read (or infer) the current five-hour quota bucket.

    Args:
        last_reset_hint: A ``resets_at`` parsed from recent Claude CLI output, if any.

    Returns:
        A :class:`QuotaReading` when a real signal is available, else None.
    """
    readings = await read_all_buckets(last_reset_hint)
    for reading in readings:
        if reading.bucket == "five_hour":
            return reading
    return readings[0] if readings else None
