"""Integration test: DELETE /machines via FastAPI against local MariaDB."""
from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from core.database import SessionLocal  # noqa: E402
from enums.run_status import RunStatus  # noqa: E402
from models.machine import Machine  # noqa: E402
from models.project import Project  # noqa: E402
from models.run import Run  # noqa: E402
from models.run_event import RunEvent  # noqa: E402
from models.run_message import RunMessage  # noqa: E402
from models.run_project import RunProject  # noqa: E402
from models.user import User  # noqa: E402
from services.auth_service import create_access_token  # noqa: E402


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token({"sub": user.email})
    return {"Authorization": f"Bearer {token}"}


def main() -> None:
    db = SessionLocal()
    user = db.query(User).filter(User.email == "contact@dibodev.fr").first()
    if user is None:
        print("SKIP: seed user missing — run init_db.py first")
        return

    project = db.query(Project).filter(Project.user_id == user.id).first()
    if project is None:
        project = Project(user_id=user.id, name="Test", github_repo="x/y", base_branch="main")
        db.add(project)
        db.commit()
        db.refresh(project)

    machine = Machine(user_id=user.id, name="DELETE-TEST", agent_token_hash="x")
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
    db.add(RunEvent(run_id=run.id, level="info", message="test"))
    db.add(
        RunMessage(
            run_id=run.id,
            project_id=project.id,
            order_index=0,
            content="hello",
            status="PENDING",
        )
    )
    db.commit()
    machine_id = machine.id
    user_email = user.email
    db.close()

    client = TestClient(app)
    user_stub = type("U", (), {"email": user_email})()
    response = client.delete(
        f"/api/v1/machines/{machine_id}",
        headers=_auth_headers(user_stub),
    )
    assert response.status_code == 204, response.text

    db = SessionLocal()
    assert db.query(Machine).filter(Machine.id == machine_id).count() == 0
    assert db.query(Run).filter(Run.machine_id == machine_id).count() == 0
    db.close()
    print("OK test_delete_integration")


if __name__ == "__main__":
    main()
