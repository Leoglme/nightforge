"""
Web Push subscription model — a browser push endpoint registered for a user.
"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base

if TYPE_CHECKING:
    from models.user import User


class PushSubscription(Base):
    """
    A browser Web Push subscription used to notify a user on their mobile PWA.

    Attributes:
        id: Unique identifier.
        user_id: Owner of the subscription.
        endpoint: Push service endpoint URL (unique per browser install).
        p256dh: Client public key for payload encryption.
        auth: Client auth secret for payload encryption.
        user_agent: Optional device hint for the settings UI.
        created_at: When the subscription was registered.
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    endpoint: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    user_agent: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    user: Mapped["User"] = relationship("User")

    def __repr__(self) -> str:
        """String representation of the subscription."""
        return f"<PushSubscription id={self.id} user_id={self.user_id}>"
