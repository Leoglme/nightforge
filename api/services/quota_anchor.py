"""
Resolve a machine's five-hour quota anchor (resets_at + utilization).

Tries a live agent read first, then falls back to the latest stored snapshot.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional, Tuple

from sqlalchemy.orm import Session

from enums.quota_bucket import QuotaBucket
from models.machine import Machine
from models.quota_snapshot import QuotaSnapshot
from services.agent_hub import agent_hub
from services.quota_planner import anchor_reset_at_from_snapshot, normalize_utilization

QuotaAnchorSource = Literal["live", "snapshot", "none"]


def _parse_live_reset(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return anchor_reset_at_from_snapshot(parsed)


def _sanitize_anchor(
    resets_at: Optional[datetime], utilization: Optional[float]
) -> tuple[Optional[datetime], Optional[float]]:
    """Drop reset times that are already in the past (stale transcript/snapshot noise)."""
    if resets_at is None:
        return None, utilization
    now = datetime.now(timezone.utc)
    if resets_at <= now:
        return None, utilization
    return resets_at, utilization


def _latest_snapshot(
    db: Session, machine_id: int
) -> tuple[Optional[datetime], Optional[float]]:
    snapshot = (
        db.query(QuotaSnapshot)
        .filter(
            QuotaSnapshot.machine_id == machine_id,
            QuotaSnapshot.bucket == QuotaBucket.FIVE_HOUR.value,
        )
        .order_by(QuotaSnapshot.created_at.desc())
        .first()
    )
    if snapshot is None:
        return None, None
    reset_at = (
        anchor_reset_at_from_snapshot(snapshot.resets_at) if snapshot.resets_at else None
    )
    utilization = normalize_utilization(snapshot.utilization)
    return _sanitize_anchor(reset_at, utilization)


async def _live_machine_quota(
    db: Session, machine_id: int, user_id: int, timeout: float
) -> tuple[Optional[datetime], Optional[float], Optional[str]]:
    machine = (
        db.query(Machine)
        .filter(Machine.id == machine_id, Machine.user_id == user_id)
        .first()
    )
    if machine is None or not agent_hub.is_online(machine_id):
        return None, None, None

    response = await agent_hub.request_agent(machine_id, {"type": "quota.read"}, timeout=timeout)
    if response is None:
        return None, None, None

    auth_error = response.get("auth_error")
    if isinstance(auth_error, str) and auth_error.strip():
        return None, None, auth_error.strip()

    utilization = normalize_utilization(response.get("utilization"))
    resets_at = _parse_live_reset(response.get("resets_at"))
    resets_at, utilization = _sanitize_anchor(resets_at, utilization)

    if utilization is None and resets_at is None:
        return None, None, None

    if resets_at is not None:
        db.add(
            QuotaSnapshot(
                machine_id=machine_id,
                bucket=response.get("bucket", "five_hour"),
                utilization=float(utilization or 0.0),
                resets_at=resets_at.replace(tzinfo=None),
            )
        )
        db.commit()

    return resets_at, utilization, None


async def resolve_machine_quota_anchor(
    db: Session,
    machine_id: int,
    user_id: int,
    *,
    prefer_live: bool = True,
    live_timeout: float = 12.0,
) -> Tuple[Optional[datetime], Optional[float], QuotaAnchorSource, Optional[str]]:
    """
    Resolve the best available five-hour bucket anchor for a machine.

    Returns:
        Tuple of (resets_at, utilization, source, auth_error).
    """
    auth_error: Optional[str] = None
    if prefer_live:
        live_reset, live_util, live_error = await _live_machine_quota(
            db, machine_id, user_id, timeout=live_timeout
        )
        if live_error:
            return None, None, "none", live_error
        elif live_reset is not None or live_util is not None:
            return live_reset, live_util, "live", None

    reset_at, utilization = _latest_snapshot(db, machine_id)
    if reset_at is not None or utilization is not None:
        return reset_at, utilization, "snapshot", auth_error

    if auth_error:
        return None, None, "none", auth_error
    return None, None, "none", None
