"""
Resolve a machine's five-hour quota anchor (resets_at + utilization).

Tries a live agent read first, then falls back to the latest stored snapshot.
"""
from __future__ import annotations

from datetime import datetime
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
    return reset_at, normalize_utilization(snapshot.utilization)


async def _live_machine_quota(
    db: Session, machine_id: int, user_id: int, timeout: float
) -> tuple[Optional[datetime], Optional[float]]:
    machine = (
        db.query(Machine)
        .filter(Machine.id == machine_id, Machine.user_id == user_id)
        .first()
    )
    if machine is None or not agent_hub.is_online(machine_id):
        return None, None

    response = await agent_hub.request_agent(machine_id, {"type": "quota.read"}, timeout=timeout)
    if response is None:
        return None, None

    utilization = normalize_utilization(response.get("utilization"))
    resets_at = _parse_live_reset(response.get("resets_at"))
    if utilization is None and resets_at is None:
        return None, None

    db.add(
        QuotaSnapshot(
            machine_id=machine_id,
            bucket=response.get("bucket", "five_hour"),
            utilization=float(utilization or 0.0),
            resets_at=resets_at.replace(tzinfo=None) if resets_at else None,
        )
    )
    db.commit()
    return resets_at, utilization


async def resolve_machine_quota_anchor(
    db: Session,
    machine_id: int,
    user_id: int,
    *,
    prefer_live: bool = True,
    live_timeout: float = 12.0,
) -> Tuple[Optional[datetime], Optional[float], QuotaAnchorSource]:
    """
    Resolve the best available five-hour bucket anchor for a machine.

    Args:
        db: Database session.
        machine_id: Target machine.
        user_id: Owner user id (for authorization on live reads).
        prefer_live: When True, query the connected agent before using snapshots.
        live_timeout: Seconds to wait for ``quota.read``.

    Returns:
        Tuple of (resets_at, utilization, source).
    """
    if prefer_live:
        live_reset, live_util = await _live_machine_quota(
            db, machine_id, user_id, timeout=live_timeout
        )
        if live_reset is not None or live_util is not None:
            return live_reset, live_util, "live"

    reset_at, utilization = _latest_snapshot(db, machine_id)
    if reset_at is not None or utilization is not None:
        return reset_at, utilization, "snapshot"
    return None, None, "none"
