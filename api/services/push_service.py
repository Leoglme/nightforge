"""
Web Push delivery — send mobile PWA notifications to a user's browsers (VAPID).
"""
import asyncio
import base64
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy.orm import Session

from core.config import settings
from core.database import SessionLocal
from models.push_subscription import PushSubscription

logger = logging.getLogger(__name__)


@dataclass
class PushResult:
    """Outcome of a push send — surfaced to the test endpoint to diagnose delivery failures."""

    delivered: int = 0
    failed: int = 0
    details: List[str] = field(default_factory=list)


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


def send_push(db: Session, user_id: int, title: str, body: str, url: str) -> PushResult:
    """
    Send a Web Push notification to every subscription of a user (blocking).

    Args:
        db: Database session.
        user_id: Target user.
        title: Notification title.
        body: Notification body.
        url: In-app path to open on click.

    Returns:
        The delivery outcome (delivered / failed counts + per-failure detail).
    """
    result = PushResult()
    pem = _vapid_private_pem()
    if not pem:
        result.details.append("VAPID not configured")
        return result
    from pywebpush import WebPushException, webpush
    from py_vapid import Vapid01

    subscriptions = (
        db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    )
    payload = json.dumps({"title": title, "body": body, "url": url})
    try:
        # pywebpush treats a *string* key as a raw base64url key (Vapid.from_string) and cannot
        # parse a PEM — load the PEM explicitly and pass the Vapid instance instead.
        vapid = Vapid01.from_pem(pem.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        result.failed = len(subscriptions)
        result.details.append(f"VAPID key load failed: {str(exc)[:160]}")
        logger.error("VAPID key load failed: %s", exc)
        return result
    stale: List[int] = []
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload,
                vapid_private_key=vapid,
                vapid_claims={"sub": settings.vapid_subject},
                ttl=3600,
            )
            result.delivered += 1
        except WebPushException as exc:
            status = getattr(exc.response, "status_code", None)
            result.failed += 1
            result.details.append(f"HTTP {status}: {str(exc)[:160]}")
            logger.warning("Push failed (user=%s status=%s): %s", user_id, status, exc)
            if status in (404, 410):
                stale.append(subscription.id)
        except Exception as exc:  # noqa: BLE001
            result.failed += 1
            result.details.append(str(exc)[:160])
            logger.warning("Push error (user=%s): %s", user_id, exc)

    if stale:
        db.query(PushSubscription).filter(PushSubscription.id.in_(stale)).delete(
            synchronize_session=False
        )
        db.commit()
    return result


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
