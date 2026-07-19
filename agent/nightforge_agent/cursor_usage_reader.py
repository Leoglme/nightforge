"""
Cursor usage reader — best-effort quotas from the local Cursor session + dashboard API.

Uses the same unofficial ``cursor.com`` dashboard endpoints as community tools
(``WorkosCursorSessionToken`` from ``state.vscdb``). If auth or the API fails,
returns an empty list so the UI can hide Cursor entirely.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

CURSOR_BASE = "https://cursor.com"
_CACHE_TTL = 90.0
_cache_expires_at = 0.0
_cache_buckets: Optional[list["CursorUsageBucket"]] = None


@dataclass
class CursorUsageBucket:
    """One Cursor plan usage bar."""

    bucket: str
    label: str
    utilization: float
    resets_at: Optional[datetime] = None


def _state_db_candidates() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        base = home / "Library" / "Application Support"
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return [
        base / "Cursor" / "User" / "globalStorage" / "state.vscdb",
        base / "Cursor Nightly" / "User" / "globalStorage" / "state.vscdb",
    ]


def _jwt_claims(token: str) -> dict[str, Any]:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def _read_item_value(path: Path, key: str) -> Optional[str]:
    """Read a single string value from a Cursor state.vscdb."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = con.execute(
                "SELECT value FROM ItemTable WHERE key = ?",
                (key,),
            ).fetchone()
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Cursor state key unreadable (%s / %s): %s", path, key, exc)
        return None
    if not row or row[0] is None:
        return None
    value = row[0]
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    text = str(value).strip()
    # Values are sometimes stored as JSON strings.
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    try:
        import json

        parsed = json.loads(text)
        if isinstance(parsed, str):
            text = parsed.strip()
    except Exception:  # noqa: BLE001
        pass
    return text or None


def _read_access_token() -> Optional[str]:
    env = os.environ.get("CURSOR_SESSION_TOKEN", "").strip()
    if env:
        return env.replace("%3A%3A", "::")

    for path in _state_db_candidates():
        if not path.exists():
            continue
        value = _read_item_value(path, "cursorAuth/accessToken")
        if value:
            return value.strip().strip('"')
    return None


def _read_cached_email() -> Optional[str]:
    """Read ``cursorAuth/cachedEmail`` from the local Cursor state DB."""
    for path in _state_db_candidates():
        if not path.exists():
            continue
        email = _read_item_value(path, "cursorAuth/cachedEmail")
        if email and "@" in email:
            return email
    return None


def export_local_session() -> tuple[Optional[str], Optional[str]]:
    """
    Export the local Cursor IDE/CLI session token and best-effort email.

    Returns:
        ``(session_token, email)`` — either may be None.
    """
    token = _read_access_token()
    email = _read_cached_email()
    if not email and token:
        claims = _jwt_claims(token.split("::")[-1])
        for key in ("email", "preferred_username", "name"):
            value = claims.get(key)
            if isinstance(value, str) and "@" in value:
                email = value.strip()
                break
    return token, email


async def read_cursor_usage_for_token(
    token: str,
) -> list[CursorUsageBucket]:
    """
    Read plan usage buckets for an explicit session token (no local DB).

    Args:
        token: Workos session cookie value or JWT access token.

    Returns:
        Zero or more buckets.
    """
    cookie = _cookie_from_token(token)
    if not cookie:
        return []
    cookie_header = "WorkosCursorSessionToken=" + cookie.replace("::", "%3A%3A")
    headers = {
        "Cookie": cookie_header,
        "Accept": "application/json",
        "User-Agent": "nightforge-agent/0.1",
        "Origin": CURSOR_BASE,
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            summary = await client.get(f"{CURSOR_BASE}/api/usage-summary", headers=headers)
            payload: Optional[dict[str, Any]] = None
            if summary.status_code == 200:
                data = summary.json()
                if isinstance(data, dict):
                    payload = data
            if payload is None:
                period = await client.post(
                    f"{CURSOR_BASE}/api/dashboard/get-current-period-usage",
                    headers=headers,
                    json={},
                )
                if period.status_code == 200:
                    data = period.json()
                    if isinstance(data, dict):
                        payload = data
            if payload:
                return _buckets_from_summary(payload)
    except Exception as exc:  # noqa: BLE001
        logger.info("Cursor usage for token unavailable: %s", exc)
    return []


def _cookie_from_token(token: str) -> Optional[str]:
    token = token.strip().replace("%3A%3A", "::")
    if "::" in token:
        return token
    claims = _jwt_claims(token)
    if claims.get("type") == "api_key_token":
        return None
    sub = claims.get("sub")
    if not sub:
        return None
    cid = str(sub).split("|")[-1]
    return f"{cid}::{token}"


def _parse_reset(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)) or (isinstance(raw, str) and raw.isdigit()):
            ms = float(raw)
            # Heuristic: ms vs seconds
            if ms > 1e12:
                ms = ms / 1000.0
            elif ms > 1e10:
                ms = ms / 1000.0
            return datetime.fromtimestamp(ms, tz=timezone.utc)
        if isinstance(raw, str):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError, OSError):
        return None
    return None


def _pct_to_util(value: Any) -> Optional[float]:
    if not isinstance(value, (int, float)):
        return None
    return min(max(float(value) / 100.0, 0.0), 1.0)


def _buckets_from_summary(payload: dict[str, Any]) -> list[CursorUsageBucket]:
    plan = (
        payload.get("planUsage")
        or (payload.get("individualUsage") or {}).get("plan")
        or {}
    )
    if not isinstance(plan, dict):
        return []

    resets_at = _parse_reset(
        payload.get("billingCycleEnd") or plan.get("billingCycleEnd")
    )
    out: list[CursorUsageBucket] = []

    auto = _pct_to_util(plan.get("autoPercentUsed"))
    if auto is not None:
        out.append(
            CursorUsageBucket(
                bucket="cursor_auto",
                label="Composer / Auto",
                utilization=auto,
                resets_at=resets_at,
            )
        )

    api = _pct_to_util(plan.get("apiPercentUsed"))
    if api is not None:
        out.append(
            CursorUsageBucket(
                bucket="cursor_api",
                label="API",
                utilization=api,
                resets_at=resets_at,
            )
        )
    return out


async def read_cursor_usage(*, force: bool = False) -> list[CursorUsageBucket]:
    """
    Read Cursor plan usage buckets from the local session + dashboard API.

    Args:
        force: Bypass the short in-memory cache.

    Returns:
        Zero or more buckets. Empty means « hide Cursor in the UI ».
    """
    global _cache_expires_at, _cache_buckets

    now = time.monotonic()
    if not force and _cache_buckets is not None and now < _cache_expires_at:
        return list(_cache_buckets)

    token = _read_access_token()
    if not token:
        _cache_buckets = []
        _cache_expires_at = now + 30
        return []

    cookie = _cookie_from_token(token)
    if not cookie:
        _cache_buckets = []
        _cache_expires_at = now + 30
        return []

    cookie_header = "WorkosCursorSessionToken=" + cookie.replace("::", "%3A%3A")
    headers = {
        "Cookie": cookie_header,
        "Accept": "application/json",
        "User-Agent": "nightforge-agent/0.1",
        "Origin": CURSOR_BASE,
        "Content-Type": "application/json",
    }

    buckets: list[CursorUsageBucket] = []
    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            # Prefer usage-summary (richer plan %); fall back to get-current-period-usage.
            summary = await client.get(f"{CURSOR_BASE}/api/usage-summary", headers=headers)
            payload: Optional[dict[str, Any]] = None
            if summary.status_code == 200:
                data = summary.json()
                if isinstance(data, dict):
                    payload = data
            if payload is None:
                period = await client.post(
                    f"{CURSOR_BASE}/api/dashboard/get-current-period-usage",
                    headers=headers,
                    json={},
                )
                if period.status_code == 200:
                    data = period.json()
                    if isinstance(data, dict):
                        payload = data
            if payload:
                buckets = _buckets_from_summary(payload)
    except Exception as exc:  # noqa: BLE001
        logger.info("Cursor usage unavailable: %s", exc)
        buckets = []

    _cache_buckets = buckets
    _cache_expires_at = now + (_CACHE_TTL if buckets else 30)
    return list(buckets)
