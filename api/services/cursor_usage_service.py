"""
Fetch Cursor plan usage from dashboard APIs using a session token.

Mirrors the agent ``cursor_usage_reader`` so the control-plane can refresh
vaulted accounts without an online agent.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

CURSOR_BASE = "https://cursor.com"


@dataclass
class CursorUsageReading:
    """Parsed plan usage for one Cursor account."""

    auto_utilization: Optional[float] = None
    api_utilization: Optional[float] = None
    resets_at: Optional[datetime] = None
    email: Optional[str] = None
    error: Optional[str] = None

    @property
    def average_utilization(self) -> Optional[float]:
        """Mean of available Auto + API percentages (0–1)."""
        values = [v for v in (self.auto_utilization, self.api_utilization) if v is not None]
        if not values:
            return None
        return sum(values) / len(values)


def _jwt_claims(token: str) -> dict[str, Any]:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:  # noqa: BLE001
        return {}


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
            if ms > 1e10:
                ms = ms / 1000.0
            return datetime.fromtimestamp(ms, tz=timezone.utc).replace(tzinfo=None)
        if isinstance(raw, str):
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                parsed = parsed.replace(tzinfo=None)
            return parsed
    except (TypeError, ValueError, OSError):
        return None
    return None


def _pct_to_util(value: Any) -> Optional[float]:
    if not isinstance(value, (int, float)):
        return None
    return min(max(float(value) / 100.0, 0.0), 1.0)


def email_from_token(token: str) -> Optional[str]:
    """Best-effort email from JWT claims."""
    claims = _jwt_claims(token.strip().replace("%3A%3A", "::").split("::")[-1])
    for key in ("email", "preferred_username", "name"):
        value = claims.get(key)
        if isinstance(value, str) and "@" in value:
            return value.strip()
    return None


def _parse_summary(payload: dict[str, Any]) -> CursorUsageReading:
    plan = (
        payload.get("planUsage")
        or (payload.get("individualUsage") or {}).get("plan")
        or {}
    )
    if not isinstance(plan, dict):
        plan = {}

    resets_at = _parse_reset(payload.get("billingCycleEnd") or plan.get("billingCycleEnd"))
    return CursorUsageReading(
        auto_utilization=_pct_to_util(plan.get("autoPercentUsed")),
        api_utilization=_pct_to_util(plan.get("apiPercentUsed")),
        resets_at=resets_at,
    )


async def fetch_cursor_usage(session_token: str) -> CursorUsageReading:
    """
    Call Cursor usage-summary with a session token.

    Args:
        session_token: Workos cookie value or JWT access token.

    Returns:
        Parsed reading (``error`` set when the call fails).
    """
    token = (session_token or "").strip()
    if not token:
        return CursorUsageReading(error="Token de session manquant")

    cookie = _cookie_from_token(token)
    if not cookie:
        return CursorUsageReading(error="Token invalide (API key seule ne lit pas le plan)")

    email = email_from_token(token)
    cookie_header = "WorkosCursorSessionToken=" + cookie.replace("::", "%3A%3A")
    headers = {
        "Cookie": cookie_header,
        "Accept": "application/json",
        "User-Agent": "nightforge-api/0.1",
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
            elif summary.status_code in (401, 403):
                return CursorUsageReading(
                    email=email,
                    error="Session expirée ou révoquée — reconnecte ce compte",
                )
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
                elif period.status_code in (401, 403):
                    return CursorUsageReading(
                        email=email,
                        error="Session expirée ou révoquée — reconnecte ce compte",
                    )
            if not payload:
                return CursorUsageReading(
                    email=email,
                    error=f"Réponse Cursor inattendue (HTTP {summary.status_code})",
                )
            reading = _parse_summary(payload)
            reading.email = email
            if reading.auto_utilization is None and reading.api_utilization is None:
                reading.error = "Aucun quota plan dans la réponse Cursor"
            return reading
    except Exception as exc:  # noqa: BLE001
        logger.info("Cursor usage fetch failed: %s", exc)
        return CursorUsageReading(email=email, error=str(exc))


def pick_best_account(
    accounts: list[tuple[int, Optional[float], Optional[float]]],
) -> Optional[int]:
    """
    Pick the account id with the lowest average utilization below 100%.

    Args:
        accounts: List of ``(id, auto_util, api_util)``.

    Returns:
        Best account id, or None if all are exhausted / unknown.
    """
    scored: list[tuple[float, int]] = []
    for account_id, auto_u, api_u in accounts:
        values = [v for v in (auto_u, api_u) if v is not None]
        if not values:
            # Prefer unknown over exhausted — put at end with high score
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
