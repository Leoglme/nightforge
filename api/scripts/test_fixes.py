"""Local regression tests for machine delete cascade and quota planner."""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base
from enums.queue_item_status import QueueItemStatus
from enums.run_status import RunStatus
from models.machine import Machine
from models.project import Project  # noqa: F401
from models.project_message import ProjectMessage  # noqa: F401
from models.project_machine_path import ProjectMachinePath  # noqa: F401
from models.queue_item import QueueItem  # noqa: F401
from models.quota_snapshot import QuotaSnapshot
from models.run import Run
from models.run_event import RunEvent
from models.run_message import RunMessage
from models.run_project import RunProject
from models.user import User
from schemas.quota import QuotaPlanRequest
from services.machine_cleanup import delete_machine_cascade
from services.quota_anchor import resolve_machine_quota_anchor
from services.quota_planner import build_plan, window_1_bounds


def test_machine_delete_cascade() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(email="t@example.com", name="Test", hashed_password="x", role="USER")
    db.add(user)
    db.flush()
    project = Project(user_id=user.id, name="P", github_repo="x/y", base_branch="main")
    db.add(project)
    db.flush()
    machine = Machine(user_id=user.id, name="PC", agent_token_hash="hash")
    db.add(machine)
    db.flush()
    run = Run(
        user_id=user.id,
        machine_id=machine.id,
        status=RunStatus.SCHEDULED.value,
        quota_count=1,
        parallel=False,
    )
    db.add(run)
    db.flush()
    db.add(RunProject(run_id=run.id, project_id=project.id, order_index=0))
    db.add(RunEvent(run_id=run.id, level="info", message="hello"))
    db.add(
        RunMessage(
            run_id=run.id,
            project_id=project.id,
            order_index=0,
            content="go",
            status=QueueItemStatus.PENDING.value,
        )
    )
    db.commit()

    delete_machine_cascade(db, machine)
    db.commit()

    assert db.query(Machine).count() == 0
    assert db.query(Run).count() == 0
    assert db.query(RunMessage).count() == 0
    assert db.query(RunEvent).count() == 0
    assert db.query(RunProject).count() == 0
    print("OK test_machine_delete_cascade")


def test_planner_stale_saturated_sets_auth_error() -> None:
    start = datetime(2026, 7, 11, 19, 0, tzinfo=timezone.utc)
    stale = datetime(2026, 7, 11, 2, 50, tzinfo=timezone.utc)
    plan = build_plan(
        QuotaPlanRequest(quota_count=1, machine_id=7, wait_for_fresh_quota=True),
        anchor_reset_at=stale,
        anchor_utilization=1.0,
        anchor_source="live",
        quota_auth_error="Session Claude expirée — NightForge tente une reconnexion automatique via le navigateur.",
    )
    assert plan.windows[0].estimated is True
    assert plan.quota_auth_error is not None
    print("OK test_planner_stale_saturated_sets_auth_error")


def test_planner_future_reset_wait() -> None:
    start = datetime(2026, 7, 11, 19, 0, tzinfo=timezone.utc)
    reset = datetime(2026, 7, 11, 21, 0, tzinfo=timezone.utc)
    w1_start, w1_end, real = window_1_bounds(start, reset, 0.35, wait_for_fresh_quota=True)
    assert real is True
    assert w1_start == reset
    print("OK test_planner_future_reset_wait")


async def test_quota_anchor_online_empty_no_stale_snapshot() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    user = User(email="t@example.com", name="Test", hashed_password="x", role="USER")
    db.add(user)
    db.flush()
    machine = Machine(user_id=user.id, name="PC", agent_token_hash="hash")
    db.add(machine)
    db.flush()
    db.add(
        QuotaSnapshot(
            machine_id=machine.id,
            bucket="five_hour",
            utilization=1.0,
            resets_at=None,
        )
    )
    db.commit()

    with patch("services.quota_anchor.agent_hub") as hub:
        hub.is_online.return_value = True
        hub.request_agent = AsyncMock(return_value=None)

        reset, util, source, err = await resolve_machine_quota_anchor(
            db, machine.id, user.id
        )

    assert reset is None
    assert util is None
    assert source == "none"
    assert err is not None and "agent" in err.lower()
    print("OK test_quota_anchor_online_empty_no_stale_snapshot")


if __name__ == "__main__":
    test_machine_delete_cascade()
    test_planner_stale_saturated_sets_auth_error()
    test_planner_future_reset_wait()
    asyncio.run(test_quota_anchor_online_empty_no_stale_snapshot())
    print("ALL TESTS PASSED")
