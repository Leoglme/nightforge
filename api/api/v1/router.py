"""
Main API v1 router.
"""
from fastapi import APIRouter

from .routes import (
    agent_ws,
    auth,
    health,
    machines,
    project_messages,
    projects,
    quota,
    queue,
    runs,
)

router = APIRouter(prefix="", tags=["v1"])

router.include_router(health.router)
router.include_router(auth.router)
router.include_router(machines.router)
router.include_router(projects.router)
router.include_router(queue.router)
router.include_router(project_messages.router)
router.include_router(runs.router)
router.include_router(quota.router)
router.include_router(agent_ws.router)
