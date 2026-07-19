"""
Cursor account vault — stored credentials + last known plan usage.
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


class CursorAccount(Base):
    """
    A Cursor plan account owned by a NightForge user.

    Sensitive fields (password, session token, API key) are stored Fernet-encrypted.
    Usage columns are best-effort caches refreshed on demand.

    Attributes:
        id: Primary key.
        user_id: Owner.
        label: Display name (e.g. "Perso", "Pro 2").
        email: Login email (plaintext — not secret by itself).
        password_encrypted: Optional login password reminder (encrypted).
        session_token_encrypted: WorkosCursorSessionToken / access token (encrypted).
        api_key_encrypted: Optional CURSOR_API_KEY for CLI auth (encrypted).
        auto_utilization: Last Composer/Auto usage 0–1.
        api_utilization: Last API usage 0–1.
        resets_at: Billing cycle end when known.
        last_checked_at: Last successful or failed usage probe.
        last_error: Last probe error message.
        is_active: Soft-disable without deleting.
        from_machine: True when this row was imported from the local IDE session.
    """

    __tablename__ = "cursor_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    session_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auto_utilization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    api_utilization: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    resets_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    from_machine: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=True
    )

    user: Mapped["User"] = relationship("User", back_populates="cursor_accounts")

    def __repr__(self) -> str:
        """String representation."""
        return f"<CursorAccount id={self.id} label={self.label!r}>"
