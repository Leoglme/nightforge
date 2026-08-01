"""
Web Push delivery — send mobile PWA notifications to a user's browsers (VAPID).
"""
import asyncio
import base64
import json
import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from core.config import settings
from core.database import SessionLocal
from models.push_subscription import PushSubscription

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """Whether VAPID keys are set (push disabled otherwise)."""
    return bool(settings.vapid_public_key and settings.vapid_private_key_b64)


def _vapid_private_pem() -> Optional[str]:
    """Decode the PKCS8 PEM VAPID private key from its base64 env value."""
    if not settings.vapid_private_key_b64:
        return None
    try:
        return base64.b64decode(settings.vapid_private_key_b64).decode("utf-8")
    except Exception:  # noqa: BLE001
        logger.error("Invalid VAPID_PRIVATE_KEY_B64 — push disabled")
        return None


def send_push(db: Session, user_id: int, title: str, body: str, url: str) -> int:
    """
    Send a Web Push notification to every subscription of a user (blocking).

    Args:
        db: Database session.
        user_id: Target user.
        title: Notification title.
        body: Notification body.
        url: In-app path to open on click.

    Returns:
        Number of notifications delivered.
    """
    pem = _vapid_private_pem()
    if not pem:
        return 0
    from pywebpush import WebPushException, webpush

    subscriptions = (
        db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    )
    payload = json.dumps({"title": title, "body": body, "url": url})
    delivered = 0
    stale: List[int] = []
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload,
                vapid_private_key=pem,
                vapid_claims={"sub": settings.vapid_subject},
                ttl=3600,
            )
            delivered += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            if status in (404, 410):
                stale.append(subscription.id)
            else:
                logger.warning("Push failed (user=%s status=%s): %s", user_id, status, exc)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Push error (user=%s): %s", user_id, exc)

    if stale:
        db.query(PushSubscription).filter(PushSubscription.id.in_(stale)).delete(
            synchronize_session=False
        )
        db.commit()
    return delivered


async def notify(user_id: int, title: str, body: str, url: str = "/dashboard/chat") -> None:
    """
    Deliver a push without blocking the event loop (own session in a worker thread).

    Args:
        user_id: Target user.
        title: Notification title.
        body: Notification body.
        url: In-app path to open on click.

    Returns:
        Nothing.
    """
    if not is_configured():
        return

    def _run() -> None:
        db = SessionLocal()
        try:
            send_push(db, user_id, title, body, url)
        finally:
            db.close()

    try:
        await asyncio.to_thread(_run)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Push notify failed (user=%s): %s", user_id, exc)
