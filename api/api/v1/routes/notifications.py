"""
Web Push notification routes — VAPID key, subscribe/unsubscribe, test.
"""
import asyncio
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, status
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db
from models.push_subscription import PushSubscription
from models.user import User
from schemas.push import (
    PushSubscriptionCreate,
    PushSubscriptionDelete,
    TestNotificationResult,
    VapidKeyResponse,
)
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


#: Delay before the test push fires, so the user can lock the phone and confirm it arrives
#: as a real background notification (not just an in-app one).
NOTIFICATION_TEST_DELAY_SECONDS = 10


async def _send_test_push_after_delay(user_id: int) -> None:
    """
    Wait, then deliver the test push (own DB session, off the event loop).

    Args:
        user_id: The user to notify.
    """
    await asyncio.sleep(NOTIFICATION_TEST_DELAY_SECONDS)
    await push_service.notify(
        user_id,
        "NightForge",
        "Notification de test 🌙",
        "/dashboard/chat",
    )


@router.post("/test", response_model=TestNotificationResult)
async def test_notification(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> Any:
    """
    Schedule a test notification ~10s out (so the user can lock the phone), and report how many
    devices are subscribed — a 0 means the subscription never reached the server, which points
    the problem at the PWA rather than delivery.

    Args:
        background_tasks: FastAPI background runner (fires after the response is sent).
        current_user: The authenticated user.
        db: Database session.

    Returns:
        Whether push is configured, the subscription count, and the delay.
    """
    subscriptions = (
        db.query(PushSubscription).filter(PushSubscription.user_id == current_user.id).count()
    )
    background_tasks.add_task(_send_test_push_after_delay, current_user.id)
    return TestNotificationResult(
        configured=push_service.is_configured(),
        subscriptions=subscriptions,
        delay_seconds=NOTIFICATION_TEST_DELAY_SECONDS,
    )
