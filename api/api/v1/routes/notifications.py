"""
Web Push notification routes — VAPID key, subscribe/unsubscribe, test.
"""
from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from models.push_subscription import PushSubscription
from models.user import User
from schemas.push import PushSubscriptionCreate, PushSubscriptionDelete, VapidKeyResponse
from services import push_service
from services.auth_service import get_current_active_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/vapid-key", response_model=VapidKeyResponse)
async def get_vapid_key(current_user: User = Depends(get_current_active_user)) -> Any:
    """
    Return the public VAPID key so the PWA can subscribe.

    Args:
        current_user: The authenticated user.

    Returns:
        The public key and whether push is configured server-side.
    """
    return VapidKeyResponse(
        public_key=settings.vapid_public_key,
        configured=push_service.is_configured(),
    )


@router.post("/subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def subscribe(
    payload: PushSubscriptionCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """
    Register (or refresh) a browser push subscription for the current user.

    Args:
        payload: The browser PushSubscription.
        current_user: The authenticated user.
        db: Database session.
    """
    existing = (
        db.query(PushSubscription).filter(PushSubscription.endpoint == payload.endpoint).first()
    )
    if existing:
        existing.user_id = current_user.id
        existing.p256dh = payload.keys.p256dh
        existing.auth = payload.keys.auth
        existing.user_agent = payload.user_agent or ""
    else:
        db.add(
            PushSubscription(
                user_id=current_user.id,
                endpoint=payload.endpoint,
                p256dh=payload.keys.p256dh,
                auth=payload.keys.auth,
                user_agent=payload.user_agent or "",
            )
        )
    db.commit()


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(
    payload: PushSubscriptionDelete,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """
    Remove a browser push subscription for the current user.

    Args:
        payload: The endpoint to unregister.
        current_user: The authenticated user.
        db: Database session.
    """
    db.query(PushSubscription).filter(
        PushSubscription.endpoint == payload.endpoint,
        PushSubscription.user_id == current_user.id,
    ).delete(synchronize_session=False)
    db.commit()


@router.post("/test", status_code=status.HTTP_204_NO_CONTENT)
async def test_notification(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> None:
    """
    Send a test notification to the current user's devices.

    Args:
        current_user: The authenticated user.
        db: Database session.
    """
    push_service.send_push(
        db,
        current_user.id,
        "NightForge",
        "Notifications activées ✅",
        "/dashboard/chat",
    )
