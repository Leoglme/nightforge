"""
Fetch Claude Max usage from Anthropic's OAuth usage API using a vaulted access token.

Unlike Cursor (browser-cookie gated), Anthropic's OAuth usage endpoint accepts a bare
bearer token, so the control-plane can refresh vaulted Claude accounts directly —
no online agent required.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

OAUTH_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
OAUTH_BETA_HEADER = "oauth-2025-04-20"
CLAUDE_USER_AGENT = "claude-code/2.1.172"

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
}


def _bucket_from_limit_entry(entry: dict[str, Any]) -> Optional[str]:
    """
    Map a Claude ``limits[]`` entry to an internal bucket key.

    ``weekly_scoped`` (Fable / legacy Opus) reuses ``seven_day_opus``.
    """
    kind = str(entry.get("kind") or entry.get("type") or entry.get("name") or "").lower()
    if kind == "weekly_scoped":
        return "seven_day_opus"
    return _KIND_TO_BUCKET.get(kind)


@dataclass
class ClaudeUsageReading:
    """Parsed Claude Max usage for one vaulted account."""

    five_hour_utilization: Optional[float] = None
    seven_day_utilization: Optional[float] = None
    seven_day_opus_utilization: Optional[float] = None
    resets_at: Optional[datetime] = None
    error: Optional[str] = None
    buckets: list[dict] = field(default_factory=list)


def _normalize_utilization(value: float, *, from_percent: bool = False) -> float:
    if from_percent:
        return min(max(float(value) / 100.0, 0.0), 1.0)
    if value > 1.0:
        return min(value / 100.0, 1.0)
    return min(max(float(value), 0.0), 1.0)


def _utilization_from_entry(entry: dict[str, Any]) -> Optional[float]:
    if "percent" in entry and isinstance(entry.get("percent"), (int, float)):
        return _normalize_utilization(float(entry["percent"]), from_percent=True)
    for key in ("utilization", "used_percentage"):
        raw = entry.get(key)
        if isinstance(raw, (int, float)):
            return _normalize_utilization(float(raw), from_percent=False)
    return None


def _parse_resets_at(raw: Any) -> Optional[datetime]:
    if raw is None:
        return None
    try:
        if isinstance(raw, (int, float)):
            return datetime.fromtimestamp(float(raw), tz=timezone.utc).replace(tzinfo=None)
        if isinstance(raw, str):
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.replace(tzinfo=None)
            return parsed
    except (TypeError, ValueError, OSError):
        return None
    return None


def _jwt_claims(token: str) -> dict[str, Any]:
    try:
        segment = token.split(".")[1]
        segment += "=" * (-len(segment) % 4)
        return json.loads(base64.urlsafe_b64decode(segment))
    except Exception:  # noqa: BLE001
        return {}


def email_from_oauth(oauth: Optional[dict[str, Any]]) -> Optional[str]:
    """
    Best-effort email extraction from a Claude OAuth block.

    Args:
        oauth: The captured OAuth block (``accessToken``, and optionally account fields).

    Returns:
        An email address if one could be inferred, else None.
    """
    if not isinstance(oauth, dict):
        return None
    for key in ("email", "accountEmail", "userEmail", "emailAddress"):
        value = oauth.get(key)
        if isinstance(value, str) and "@" in value:
            return value.strip()
    account = oauth.get("account")
    if isinstance(account, dict):
        for key in ("email", "emailAddress"):
            value = account.get(key)
            if isinstance(value, str) and "@" in value:
                return value.strip()
    token = oauth.get("accessToken")
    if isinstance(token, str) and token.count(".") >= 2:
        claims = _jwt_claims(token)
        for key in ("email", "preferred_username"):
            value = claims.get(key)
            if isinstance(value, str) and "@" in value:
                return value.strip()
    return None


async def fetch_claude_usage(access_token: str) -> ClaudeUsageReading:
    """
    Call Anthropic's OAuth usage endpoint with a vaulted access token.

    Args:
        access_token: The account's Claude OAuth access token.

    Returns:
        Parsed reading (``error`` set when the call fails).
    """
    token = (access_token or "").strip()
    if not token:
        return ClaudeUsageReading(error="Jeton d'accès manquant")

    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-beta": OAUTH_BETA_HEADER,
        "User-Agent": CLAUDE_USER_AGENT,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(OAUTH_USAGE_URL, headers=headers)
    except httpx.HTTPError as exc:
        logger.info("Claude OAuth usage request failed: %s", exc)
        return ClaudeUsageReading(error=str(exc))

    if response.status_code in (401, 403):
        return ClaudeUsageReading(error="Jeton expiré ou révoqué — reconnecte ce compte")
    if response.status_code == 429:
        return ClaudeUsageReading(
            error="Lecture quota temporairement limitée par l'API Claude — réessaie plus tard"
        )
    if response.status_code != 200:
        return ClaudeUsageReading(error=f"Réponse Claude inattendue (HTTP {response.status_code})")

    try:
        payload = response.json()
    except ValueError:
        return ClaudeUsageReading(error="Réponse Claude invalide")
    if not isinstance(payload, dict):
        return ClaudeUsageReading(error="Réponse Claude invalide")

    reading = ClaudeUsageReading()

    limits = payload.get("limits")
    entries: list[dict[str, Any]] = limits if isinstance(limits, list) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        bucket = _bucket_from_limit_entry(entry)
        if not bucket:
            continue
        utilization = _utilization_from_entry(entry)
        if utilization is None:
            continue
        reading.buckets.append(
            {"bucket": bucket, "utilization": utilization, "resets_at": entry.get("resets_at")}
        )
        if bucket == "five_hour" and reading.five_hour_utilization is None:
            reading.five_hour_utilization = utilization
            reading.resets_at = _parse_resets_at(entry.get("resets_at"))
        elif bucket == "seven_day" and reading.seven_day_utilization is None:
            reading.seven_day_utilization = utilization
        elif bucket == "seven_day_opus":
            # Scoped weekly (Fable) overwrites a null/flat opus slot.
            reading.seven_day_opus_utilization = utilization

    for flat_key, bucket in (
        ("five_hour", "five_hour"),
        ("seven_day", "seven_day"),
        ("seven_day_opus", "seven_day_opus"),
    ):
        entry = payload.get(flat_key)
        if not isinstance(entry, dict):
            continue
        utilization = _utilization_from_entry(entry)
        if utilization is None:
            continue
        if bucket == "five_hour" and reading.five_hour_utilization is None:
            reading.five_hour_utilization = utilization
            reading.resets_at = reading.resets_at or _parse_resets_at(entry.get("resets_at"))
        elif bucket == "seven_day" and reading.seven_day_utilization is None:
            reading.seven_day_utilization = utilization
        elif bucket == "seven_day_opus" and reading.seven_day_opus_utilization is None:
            reading.seven_day_opus_utilization = utilization

    if (
        reading.five_hour_utilization is None
        and reading.seven_day_utilization is None
        and reading.seven_day_opus_utilization is None
    ):
        reading.error = "Aucun quota Claude dans la réponse"
    return reading


def pick_best_claude_account(
    accounts: list[tuple[int, Optional[float], Optional[float]]],
) -> Optional[int]:
    """
    Pick the account id with the lowest average utilization below 100%.

    Args:
        accounts: List of ``(id, five_hour_utilization, seven_day_utilization)``.

    Returns:
        Best account id, or None if all are exhausted / unknown.
    """
    scored: list[tuple[float, int]] = []
    for account_id, five_hour_u, seven_day_u in accounts:
        values = [v for v in (five_hour_u, seven_day_u) if v is not None]
        if not values:
            # Prefer unknown over exhausted — put at end with high score.
            scored.append((0.99, account_id))
            continue
        avg = sum(values) / len(values)
        if avg >= 0.999:
            continue
        scored.append((avg, account_id))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0])
    return scored[0][1]
