"""
Claude account vault — stored OAuth access tokens + last known Claude Max usage.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base

if TYPE_CHECKING:
    from models.user import User


class ClaudeAccount(Base):
    """
    A Claude Max account owned by a NightForge user.

    Sensitive fields (password, OAuth block) are stored Fernet-encrypted.
    Usage columns are best-effort caches refreshed on demand.

    Attributes:
        id: Primary key.
        user_id: Owner.
        label: Display name (e.g. "Perso", "Pro 2"; defaults to email).
        email: Login email (plaintext — not secret by itself).
        password_encrypted: Optional login password reminder (encrypted).
        oauth_encrypted: Encrypted JSON OAuth block (``accessToken``/``refreshToken``/``expiresAt``).
        five_hour_utilization: Last rolling 5-hour bucket usage 0–1.
        seven_day_utilization: Last rolling 7-day bucket usage 0–1.
        seven_day_opus_utilization: Last rolling 7-day Opus bucket usage 0–1.
        resets_at: Next known bucket reset, when known.
        last_checked_at: Last successful or failed usage probe.
        last_error: Last probe error message.
        is_active: Soft-disable without deleting.
        from_machine: True when this row mirrors the local agent's active session.
    """

    __tablename__ = "claude_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    oauth_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    five_hour_utilization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    seven_day_utilization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    seven_day_opus_utilization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resets_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    from_machine: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=True
    )

    user: Mapped["User"] = relationship("User", back_populates="claude_accounts")

    def __repr__(self) -> str:
        """String representation."""
        return f"<ClaudeAccount id={self.id} label={self.label!r}>"
