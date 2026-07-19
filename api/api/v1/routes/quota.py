"""
Quota routes — planner, latest snapshots, and dashboard Utilisation.
"""
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database import get_db
from enums.quota_bucket import QuotaBucket
from models.machine import Machine
from models.quota_snapshot import QuotaSnapshot
from models.user import User
from schemas.quota import (
    QuotaPlanRequest,
    QuotaPlanResponse,
    QuotaSnapshotResponse,
    UsageBucket,
    UsageSummaryResponse,
)
from services.agent_hub import agent_hub
from services.auth_service import get_current_active_user
from services.quota_anchor import resolve_machine_quota_anchor
from services.quota_planner import build_plan, normalize_utilization

router = APIRouter(prefix="/quota", tags=["quota"])

_CLAUDE_LABELS = {
    QuotaBucket.FIVE_HOUR.value: "Fenêtre 5 h",
    QuotaBucket.SEVEN_DAY.value: "Hebdomadaire",
    QuotaBucket.SEVEN_DAY_OPUS.value: "Hebdomadaire Fable",
    QuotaBucket.SEVEN_DAY_OAUTH_APPS.value: "Hebdomadaire Claude Code",
}

_CURSOR_LABELS = {
    "cursor_auto": "Composer / Auto",
    "cursor_api": "API",
}


@router.post("/plan", response_model=QuotaPlanResponse)
async def plan_quota(
    payload: QuotaPlanRequest,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Compute the quota timeline for N sequential 5-hour windows.

    Args:
        payload: Planner request.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The planned timeline, anchored on real reset data when a machine is given.
    """
    anchor_reset_at = None
    anchor_utilization = None
    anchor_source = None
    quota_auth_error = None
    if payload.machine_id is not None:
        anchor_reset_at, anchor_utilization, anchor_source, quota_auth_error = (
            await resolve_machine_quota_anchor(db, payload.machine_id, current_user.id)
        )

    return build_plan(
        payload,
        anchor_reset_at=anchor_reset_at,
        anchor_utilization=anchor_utilization,
        anchor_source=anchor_source,
        quota_auth_error=quota_auth_error,
    )


@router.get("/machines/{machine_id}/snapshots", response_model=List[QuotaSnapshotResponse])
async def latest_snapshots(
    machine_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Get the latest quota snapshot per bucket for a machine.

    Args:
        machine_id: The machine id.
        current_user: The authenticated user.
        db: Database session.

    Returns:
        The most recent snapshot for each known bucket.
    """
    results: List[QuotaSnapshot] = []
    for bucket in QuotaBucket:
        latest = (
            db.query(QuotaSnapshot)
            .join(Machine, Machine.id == QuotaSnapshot.machine_id)
            .filter(
                QuotaSnapshot.machine_id == machine_id,
                QuotaSnapshot.bucket == bucket.value,
                Machine.user_id == current_user.id,
            )
            .order_by(QuotaSnapshot.created_at.desc())
            .first()
        )
        if latest:
            results.append(latest)
    return results


def _to_usage_bucket(
    *,
    bucket: str,
    label: str,
    utilization: float,
    resets_at: Optional[datetime] = None,
    created_at: Optional[datetime] = None,
) -> UsageBucket:
    util = max(0.0, min(float(utilization), 1.0))
    return UsageBucket(
        bucket=bucket,
        label=label,
        utilization=util,
        remaining=max(0.0, 1.0 - util),
        resets_at=resets_at,
        created_at=created_at,
    )


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _persist_bucket(
    db: Session,
    machine_id: int,
    bucket: str,
    utilization: float,
    resets_at: Optional[datetime],
) -> None:
    db.add(
        QuotaSnapshot(
            machine_id=machine_id,
            bucket=bucket,
            utilization=float(utilization),
            resets_at=resets_at,
        )
    )


def _latest_account_snapshots(
    db: Session, user_id: int, bucket_keys: List[str]
) -> dict[str, QuotaSnapshot]:
    """Most recent snapshot per bucket across all of the user's machines."""
    machine_ids = [
        m.id for m in db.query(Machine.id).filter(Machine.user_id == user_id).all()
    ]
    if not machine_ids:
        return {}
    out: dict[str, QuotaSnapshot] = {}
    for key in bucket_keys:
        latest = (
            db.query(QuotaSnapshot)
            .filter(
                QuotaSnapshot.machine_id.in_(machine_ids),
                QuotaSnapshot.bucket == key,
            )
            .order_by(QuotaSnapshot.created_at.desc())
            .first()
        )
        if latest:
            out[key] = latest
    return out


@router.get("/usage", response_model=UsageSummaryResponse)
async def usage_summary(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Dashboard « Utilisation » — account-level Claude Max + Cursor (when readable).

    Same Claude/Cursor account across machines: pick any online agent for a live
    refresh, otherwise fall back to the freshest stored snapshots.
    """
    machines = (
        db.query(Machine)
        .filter(Machine.user_id == current_user.id)
        .order_by(Machine.last_seen_at.desc(), Machine.name.asc())
        .all()
    )
    online = next((m for m in machines if agent_hub.is_online(m.id)), None)

    claude: List[UsageBucket] = []
    cursor: Optional[List[UsageBucket]] = None
    source = "none"
    auth_error: Optional[str] = None

    if online is not None:
        response = await agent_hub.request_agent(
            online.id, {"type": "quota.read"}, timeout=20.0
        )
        if response:
            auth_error = response.get("auth_error")
            if isinstance(auth_error, str) and not auth_error.strip():
                auth_error = None
            raw_buckets = response.get("buckets")
            if isinstance(raw_buckets, list) and raw_buckets:
                source = "live"
                for entry in raw_buckets:
                    if not isinstance(entry, dict):
                        continue
                    bucket = str(entry.get("bucket") or "")
                    if bucket not in _CLAUDE_LABELS:
                        continue
                    util = normalize_utilization(entry.get("utilization"))
                    if util is None:
                        continue
                    # Re-normalize wrongly stored percent-as-fraction for live values
                    # already fixed on the agent; keep as-is.
                    resets = _parse_iso(entry.get("resets_at"))
                    _persist_bucket(db, online.id, bucket, util, resets)
                    claude.append(
                        _to_usage_bucket(
                            bucket=bucket,
                            label=_CLAUDE_LABELS[bucket],
                            utilization=util,
                            resets_at=resets,
                        )
                    )
                db.commit()

        cursor_resp = await agent_hub.request_agent(
            online.id, {"type": "cursor.usage"}, timeout=25.0
        )
        if cursor_resp and isinstance(cursor_resp.get("buckets"), list):
            cursor_buckets: List[UsageBucket] = []
            for entry in cursor_resp["buckets"]:
                if not isinstance(entry, dict):
                    continue
                bucket = str(entry.get("bucket") or "")
                if bucket not in _CURSOR_LABELS:
                    continue
                label = str(entry.get("label") or _CURSOR_LABELS[bucket])
                util = normalize_utilization(entry.get("utilization"))
                # Cursor percents arrive already as 0–1 from the agent.
                if util is None:
                    continue
                # Agent already divided by 100; if value looks like a leftover percent (e.g. 28), fix.
                raw = entry.get("utilization")
                if isinstance(raw, (int, float)) and raw > 1.0:
                    util = min(float(raw) / 100.0, 1.0)
                resets = _parse_iso(entry.get("resets_at"))
                _persist_bucket(db, online.id, bucket, util, resets)
                cursor_buckets.append(
                    _to_usage_bucket(
                        bucket=bucket,
                        label=label,
                        utilization=util,
                        resets_at=resets,
                    )
                )
            if cursor_buckets:
                db.commit()
                cursor = cursor_buckets

    if not claude:
        snaps = _latest_account_snapshots(
            db, current_user.id, list(_CLAUDE_LABELS.keys())
        )
        for key, label in _CLAUDE_LABELS.items():
            snap = snaps.get(key)
            if not snap:
                continue
            util = normalize_utilization(snap.utilization)
            if util is None:
                continue
            claude.append(
                _to_usage_bucket(
                    bucket=key,
                    label=label,
                    utilization=util,
                    resets_at=snap.resets_at,
                    created_at=snap.created_at,
                )
            )
        if claude and source == "none":
            source = "snapshot"

    if cursor is None:
        snaps = _latest_account_snapshots(
            db, current_user.id, list(_CURSOR_LABELS.keys())
        )
        cursor_buckets = []
        for key, label in _CURSOR_LABELS.items():
            snap = snaps.get(key)
            if not snap:
                continue
            util = normalize_utilization(snap.utilization)
            if util is None:
                continue
            cursor_buckets.append(
                _to_usage_bucket(
                    bucket=key,
                    label=label,
                    utilization=util,
                    resets_at=snap.resets_at,
                    created_at=snap.created_at,
                )
            )
        if cursor_buckets:
            cursor = cursor_buckets

    # Prefer a stable Claude order.
    order = list(_CLAUDE_LABELS.keys())
    claude.sort(key=lambda b: order.index(b.bucket) if b.bucket in order else 99)

    return UsageSummaryResponse(
        claude=claude,
        cursor=cursor,
        source=source,
        quota_auth_error=auth_error if isinstance(auth_error, str) else None,
    )
