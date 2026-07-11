"""
Quota planner — turns "N quotas from time T" into a per-window timeline.

Model (simplification, re-anchored on real reset data when available): a "quota" is a
rolling 5-hour window. Burning quota N fully means the next window opens ~5h after the
first message of window N, so N sequential quotas span [t0, t0 + N*5h] and a fresh, empty
quota is available at t0 + N*5h.

The API ``resets_at`` is when the current five-hour *bucket* rolls off (e.g. after a 429).
It anchors the effective start of window 1 only when the bucket is saturated; it is never
used as the window end. Each burned quota always ends ``starts_at + 5h``.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from schemas.quota import QuotaPlanRequest, QuotaPlanResponse, QuotaWindow

QUOTA_HOURS = 5


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


def first_window_start(
    start: datetime,
    anchor_reset_at: Optional[datetime],
    anchor_utilization: Optional[float],
) -> datetime:
    """
    Effective start of quota window 1.

    When the five-hour bucket is saturated (utilization ~100 %), burning only resumes
    after the real bucket reset — not at the original launch time.

    Args:
        start: Planned or actual launch time.
        anchor_reset_at: Real bucket reset from the machine snapshot, if any.
        anchor_utilization: Latest five-hour utilization (0.0 -> 1.0), if known.

    Returns:
        When quota 1 effectively starts for timeline purposes.
    """
    if (
        anchor_reset_at is not None
        and anchor_reset_at > start
        and anchor_utilization is not None
        and anchor_utilization >= 0.99
    ):
        return anchor_reset_at
    return start


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
    # Work entirely in timezone-aware UTC so the serialized ISO carries an offset and the
    # front-end can render reliable local times.
    start = payload.start_at or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    wake_at = payload.wake_at
    if wake_at is not None and wake_at.tzinfo is None:
        wake_at = wake_at.replace(tzinfo=timezone.utc)

    windows: List[QuotaWindow] = []
    cursor = first_window_start(start, anchor_reset_at, anchor_utilization)
    for i in range(payload.quota_count):
        starts_at = cursor
        resets_at = starts_at + timedelta(hours=QUOTA_HOURS)
        estimated = not (i == 0 and anchor_reset_at is not None)
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
        # Very rough: each burned 5h quota consumes a slice of the weekly budget.
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
