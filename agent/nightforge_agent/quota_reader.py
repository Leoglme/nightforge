"""
Quota reader — reads the Claude Max usage buckets so the control-plane can plan.

Strategies (in order):

1. OAuth usage API (``GET api.anthropic.com/api/oauth/usage``) via ``~/.claude/.credentials.json``.
2. Recent Claude Code session transcripts (rate-limit lines from an open desktop/CLI session).
3. A ``resets_at`` hint captured live by :mod:`claude_runner` during a run.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

from .claude_runner import parse_reset_hint

logger = logging.getLogger(__name__)

OAUTH_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_REFRESH_URL = "https://console.anthropic.com/v1/oauth/token"
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
OAUTH_BETA_HEADER = "oauth-2025-04-20"
CLAUDE_USER_AGENT = "claude-code/2.1.172"

_CACHE_TTL_SECONDS = 60
_cache_expires_at = 0.0
_cache_reading: Optional["QuotaReading"] = None


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


def _load_oauth_block() -> Optional[dict[str, Any]]:
    path = _credentials_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.debug("Could not read Claude credentials: %s", exc)
        return None
    oauth = data.get("claudeAiOauth")
    return oauth if isinstance(oauth, dict) else None


def _token_expired(oauth: dict[str, Any], buffer_seconds: int = 60) -> bool:
    expires_at = oauth.get("expiresAt")
    if not isinstance(expires_at, (int, float)):
        return True
    return int(expires_at) <= int(time.time() * 1000) + buffer_seconds * 1000


def _write_oauth_block(oauth: dict[str, Any]) -> None:
    path = _credentials_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    payload["claudeAiOauth"] = oauth
    tmp = path.with_suffix(".credentials.json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


async def _refresh_oauth_token(oauth: dict[str, Any]) -> Optional[dict[str, Any]]:
    refresh_token = oauth.get("refreshToken")
    if not isinstance(refresh_token, str) or not refresh_token:
        return None

    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": OAUTH_CLIENT_ID,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(OAUTH_REFRESH_URL, json=body)
    except httpx.HTTPError as exc:
        logger.debug("OAuth refresh failed: %s", exc)
        return None

    if response.status_code != 200:
        logger.debug("OAuth refresh rejected (%s): %s", response.status_code, response.text[:200])
        return None

    data = response.json()
    updated = {
        **oauth,
        "accessToken": data["access_token"],
        "refreshToken": data.get("refresh_token", refresh_token),
        "expiresAt": int(time.time() * 1000) + int(data.get("expires_in", 3600)) * 1000,
    }
    try:
        _write_oauth_block(updated)
    except OSError as exc:
        logger.warning("Could not persist refreshed OAuth token: %s", exc)
    return updated


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
    bucket = payload.get("five_hour")
    if not isinstance(bucket, dict):
        return None

    utilization = bucket.get("utilization")
    if not isinstance(utilization, (int, float)):
        return None

    return QuotaReading(
        bucket="five_hour",
        utilization=_normalize_utilization(float(utilization)),
        resets_at=_parse_event_timestamp(bucket.get("resets_at")),
    )


async def _read_oauth_usage() -> Optional[QuotaReading]:
    oauth = _load_oauth_block()
    if oauth is None:
        return None

    access_token = oauth.get("accessToken")
    if not isinstance(access_token, str) or not access_token:
        return None

    if _token_expired(oauth):
        refreshed = await _refresh_oauth_token(oauth)
        if refreshed is None:
            return None
        oauth = refreshed
        access_token = oauth["accessToken"]

    reading = await _fetch_oauth_usage(access_token)
    if reading is not None:
        return reading

    if not _token_expired(oauth):
        refreshed = await _refresh_oauth_token(oauth)
        if refreshed is None:
            return None
        return await _fetch_oauth_usage(refreshed["accessToken"])

    return None


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

    return QuotaReading(bucket="five_hour", utilization=1.0, resets_at=best_reset)


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
    if reading is None:
        reading = _scan_session_transcripts()
    if reading is None and last_reset_hint is not None:
        reading = QuotaReading(bucket="five_hour", utilization=1.0, resets_at=last_reset_hint)

    if reading is not None:
        # Normalize the reset to timezone-aware UTC. The OAuth path is already aware; the
        # transcript / CLI-hint paths produce naive *local* datetimes, so interpret those as
        # local before converting — otherwise the control-plane and UI show a shifted hour.
        if reading.resets_at is not None and reading.resets_at.tzinfo is None:
            reading = QuotaReading(
                bucket=reading.bucket,
                utilization=reading.utilization,
                resets_at=reading.resets_at.astimezone(timezone.utc),
            )
        _cache_reading = reading
        _cache_expires_at = now + _CACHE_TTL_SECONDS

    return reading
