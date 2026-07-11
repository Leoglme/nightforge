"""
Quota planner — turns "N quotas from time T" into a per-window timeline.

When the machine reports OAuth ``resets_at`` / utilization, window 1 is anchored on that
real bucket. With ``wait_for_fresh_quota`` (default), a partially used bucket schedules
the first window at the real reset time instead of starting immediately.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from schemas.quota import QuotaPlanRequest, QuotaPlanResponse, QuotaWindow

QUOTA_HOURS = 5
# Bucket considered full enough to wait for the real ``resets_at`` before window 1.
SATURATION_THRESHOLD = 0.85
# Any meaningful usage triggers a wait when ``wait_for_fresh_quota`` is enabled.
ACTIVE_BUCKET_THRESHOLD = 0.02


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


def _snap_bucket_start(start: datetime, begins_at: datetime, ends_at: datetime) -> datetime:
    """
    Snap the displayed bucket start to a round hour when already inside the window.

    Args:
        start: Current time.
        begins_at: Inferred bucket start (``ends_at - 5h``).
        ends_at: OAuth bucket end.

    Returns:
        Adjusted bucket start for display.
    """
    if begins_at < start < ends_at:
        hour_floor = start.replace(minute=0, second=0, microsecond=0)
        if hour_floor >= begins_at:
            return hour_floor
    return begins_at


def _should_wait_for_fresh_reset(
    utilization: Optional[float],
    wait_for_fresh_quota: bool,
) -> bool:
    if utilization is None:
        return wait_for_fresh_quota
    if utilization >= SATURATION_THRESHOLD:
        return True
    return wait_for_fresh_quota and utilization >= ACTIVE_BUCKET_THRESHOLD


def window_1_bounds(
    start: datetime,
    anchor_reset_at: Optional[datetime],
    anchor_utilization: Optional[float],
    *,
    wait_for_fresh_quota: bool = True,
) -> Tuple[datetime, datetime, bool]:
    """
    Compute window 1 start/end, preferring live OAuth bucket data when available.

    Args:
        start: Planned or actual launch time (aware UTC).
        anchor_reset_at: Real ``resets_at`` from the machine snapshot, if any.
        anchor_utilization: Latest five-hour utilization for the machine.
        wait_for_fresh_quota: When True, schedule window 1 at the next reset if the
            current bucket is already in use.

    Returns:
        Tuple of (starts_at, resets_at, used_real_oauth_data).
    """
    start = _aware_utc(start)
    utilization = normalize_utilization(anchor_utilization)
    anchor = anchor_reset_at_from_snapshot(anchor_reset_at)

    if anchor is None and utilization is None:
        return start, start + timedelta(hours=QUOTA_HOURS), False

    # Active bucket with a future OAuth end time.
    if anchor is not None and anchor > start:
        if _should_wait_for_fresh_reset(utilization, wait_for_fresh_quota):
            return anchor, anchor + timedelta(hours=QUOTA_HOURS), True

        ends_at = anchor
        begins_at = _snap_bucket_start(start, ends_at - timedelta(hours=QUOTA_HOURS), ends_at)
        return begins_at, ends_at, True

    # Stale ``resets_at`` but fresh utilization — infer remaining window from usage.
    if utilization is not None and utilization < SATURATION_THRESHOLD:
        if _should_wait_for_fresh_reset(utilization, wait_for_fresh_quota):
            remaining_hours = max(0.25, QUOTA_HOURS * (1.0 - utilization))
            wait_until = start + timedelta(hours=remaining_hours)
            return wait_until, wait_until + timedelta(hours=QUOTA_HOURS), True

        remaining_hours = max(0.25, QUOTA_HOURS * (1.0 - utilization))
        ends_at = start + timedelta(hours=remaining_hours)
        begins_at = _snap_bucket_start(
            start, ends_at - timedelta(hours=QUOTA_HOURS), ends_at
        )
        return begins_at, ends_at, True

    return start, start + timedelta(hours=QUOTA_HOURS), False


def build_plan(
    payload: QuotaPlanRequest,
    anchor_reset_at: Optional[datetime] = None,
    anchor_utilization: Optional[float] = None,
    weekly_budget_left_fraction: Optional[float] = None,
    anchor_source: Optional[str] = None,
) -> QuotaPlanResponse:
    """
    Build the quota timeline for the requested number of quotas.

    Args:
        payload: Planner request (quota count, start time, optional wake time).
        anchor_reset_at: Real ``resets_at`` of the machine's current five-hour bucket, if any.
        anchor_utilization: Latest five-hour utilization for anchoring a saturated bucket.
        weekly_budget_left_fraction: Remaining weekly budget (0.0 -> 1.0) for the warning.
        anchor_source: How the anchor was resolved (``live``, ``snapshot``, ``none``).

    Returns:
        The planned timeline with per-window start/reset and the fresh-quota time.
    """
    start = payload.start_at or datetime.now(timezone.utc)
    start = _aware_utc(start)
    wake_at = payload.wake_at
    if wake_at is not None:
        wake_at = _aware_utc(wake_at)

    windows: List[QuotaWindow] = []
    w1_start, w1_end, w1_real = window_1_bounds(
        start,
        anchor_reset_at,
        anchor_utilization,
        wait_for_fresh_quota=payload.wait_for_fresh_quota,
    )
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
    wait_until = w1_start if w1_real and w1_start > start else None

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
        wait_until=wait_until,
        anchor_source=anchor_source,
        hours_after_wake=hours_after_wake,
        weekly_warning=weekly_warning,
    )
