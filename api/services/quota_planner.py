"""
Quota planner — turns "N quotas from time T" into a per-window timeline.

When the machine reports OAuth ``resets_at``, window 1 is anchored on that real bucket:
- Saturated bucket: work resumes at ``resets_at``, then runs for 5 h.
- Active bucket: the window ends at ``resets_at``; the start is inferred as
  ``resets_at - 5 h``, snapped to the current hour when already part-way through.

Further quotas chain forward in 5 h steps from window 1's end.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from schemas.quota import QuotaPlanRequest, QuotaPlanResponse, QuotaWindow

QUOTA_HOURS = 5
# Bucket considered full enough to wait for the real ``resets_at`` before window 1.
SATURATION_THRESHOLD = 0.85


def normalize_utilization(value: Optional[float]) -> Optional[float]:
    """
    Normalize utilization to a 0.0 -> 1.0 fraction.

    Args:
        value: Raw utilization from a snapshot or OAuth payload.

    Returns:
        A fraction in [0, 1], or None when unknown.
    """
    if value is None:
        return None
    if value > 1.0:
        return min(value / 100.0, 1.0)
    return min(max(float(value), 0.0), 1.0)


def anchor_reset_at_from_snapshot(resets_at: Optional[datetime]) -> Optional[datetime]:
    """
    Normalize a stored quota snapshot reset time to timezone-aware UTC.

    Args:
        resets_at: Naive UTC from the database, or None.

    Returns:
        Aware UTC datetime, or None.
    """
    if resets_at is None:
        return None
    if resets_at.tzinfo is None:
        return resets_at.replace(tzinfo=timezone.utc)
    return resets_at.astimezone(timezone.utc)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def window_1_bounds(
    start: datetime,
    anchor_reset_at: Optional[datetime],
    anchor_utilization: Optional[float],
) -> Tuple[datetime, datetime, bool]:
    """
    Compute window 1 start/end, preferring live OAuth bucket data when available.

    Args:
        start: Planned or actual launch time (aware UTC).
        anchor_reset_at: Real ``resets_at`` from the machine snapshot, if any.
        anchor_utilization: Latest five-hour utilization for the machine.

    Returns:
        Tuple of (starts_at, resets_at, used_real_oauth_data).
    """
    start = _aware_utc(start)
    utilization = normalize_utilization(anchor_utilization)
    anchor = anchor_reset_at_from_snapshot(anchor_reset_at)

    if anchor is None:
        return start, start + timedelta(hours=QUOTA_HOURS), False

    # Saturated: the bucket is empty again only after the real reset.
    if (
        utilization is not None
        and utilization >= SATURATION_THRESHOLD
        and anchor > start
    ):
        return anchor, anchor + timedelta(hours=QUOTA_HOURS), True

    # Active bucket: OAuth ``resets_at`` is when the current window ends.
    if anchor > start:
        ends_at = anchor
        begins_at = ends_at - timedelta(hours=QUOTA_HOURS)
        if begins_at < start < ends_at:
            hour_floor = start.replace(minute=0, second=0, microsecond=0)
            if hour_floor >= begins_at:
                begins_at = hour_floor
        return begins_at, ends_at, True

    # Stale or past reset — fall back to a rolling estimate from now.
    return start, start + timedelta(hours=QUOTA_HOURS), False


def build_plan(
    payload: QuotaPlanRequest,
    anchor_reset_at: Optional[datetime] = None,
    anchor_utilization: Optional[float] = None,
    weekly_budget_left_fraction: Optional[float] = None,
) -> QuotaPlanResponse:
    """
    Build the quota timeline for the requested number of quotas.

    Args:
        payload: Planner request (quota count, start time, optional wake time).
        anchor_reset_at: Real ``resets_at`` of the machine's current five-hour bucket, if any.
        anchor_utilization: Latest five-hour utilization for anchoring a saturated bucket.
        weekly_budget_left_fraction: Remaining weekly budget (0.0 -> 1.0) for the warning.

    Returns:
        The planned timeline with per-window start/reset and the fresh-quota time.
    """
    start = payload.start_at or datetime.now(timezone.utc)
    start = _aware_utc(start)
    wake_at = payload.wake_at
    if wake_at is not None:
        wake_at = _aware_utc(wake_at)

    windows: List[QuotaWindow] = []
    w1_start, w1_end, w1_real = window_1_bounds(start, anchor_reset_at, anchor_utilization)
    cursor = w1_start
    for i in range(payload.quota_count):
        if i == 0:
            starts_at = w1_start
            resets_at = w1_end
            estimated = not w1_real
        else:
            starts_at = cursor
            resets_at = starts_at + timedelta(hours=QUOTA_HOURS)
            estimated = True
        windows.append(
            QuotaWindow(index=i + 1, starts_at=starts_at, resets_at=resets_at, estimated=estimated)
        )
        cursor = resets_at

    fresh_at = windows[-1].resets_at

    hours_after_wake: Optional[float] = None
    if wake_at is not None:
        hours_after_wake = round((fresh_at - wake_at).total_seconds() / 3600.0, 2)

    weekly_warning: Optional[str] = None
    if weekly_budget_left_fraction is not None:
        if weekly_budget_left_fraction <= 0.15 * payload.quota_count:
            weekly_warning = (
                "Budget hebdomadaire faible : brûler ces quotas peut atteindre le plafond "
                "hebdo (surtout Opus) avant la fin des fenêtres."
            )

    return QuotaPlanResponse(
        windows=windows,
        fresh_quota_available_at=fresh_at,
        hours_after_wake=hours_after_wake,
        weekly_warning=weekly_warning,
    )
