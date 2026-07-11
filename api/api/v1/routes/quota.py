"""
Quota routes — planner and latest snapshots.
"""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database import get_db
from enums.quota_bucket import QuotaBucket
from models.machine import Machine
from models.quota_snapshot import QuotaSnapshot
from models.user import User
from schemas.quota import QuotaPlanRequest, QuotaPlanResponse, QuotaSnapshotResponse
from services.auth_service import get_current_active_user
from services.quota_planner import anchor_reset_at_from_snapshot, build_plan

router = APIRouter(prefix="/quota", tags=["quota"])


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
    if payload.machine_id is not None:
        machine = (
            db.query(Machine)
            .filter(Machine.id == payload.machine_id, Machine.user_id == current_user.id)
            .first()
        )
        if machine:
            snapshot = (
                db.query(QuotaSnapshot)
                .filter(
                    QuotaSnapshot.machine_id == machine.id,
                    QuotaSnapshot.bucket == QuotaBucket.FIVE_HOUR.value,
                )
                .order_by(QuotaSnapshot.created_at.desc())
                .first()
            )
            if snapshot:
                anchor_utilization = snapshot.utilization
                if snapshot.resets_at:
                    anchor_reset_at = anchor_reset_at_from_snapshot(snapshot.resets_at)

    return build_plan(
        payload,
        anchor_reset_at=anchor_reset_at,
        anchor_utilization=anchor_utilization,
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
        latest: Optional[QuotaSnapshot] = (
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
