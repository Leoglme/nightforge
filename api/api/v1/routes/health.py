"""
Health check routes.
"""
from datetime import datetime

from fastapi import APIRouter

from core.config import settings
from models.health import HealthStatus

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthStatus, summary="Health check endpoint")
async def health_check() -> HealthStatus:
    """
    Get the health status of the API.

    Returns:
        The current health status.
    """
    return HealthStatus(
        status="healthy",
        version=settings.api_version,
        timestamp=datetime.utcnow().isoformat() + "Z",
        services={"api": "healthy", "database": "healthy"},
    )
