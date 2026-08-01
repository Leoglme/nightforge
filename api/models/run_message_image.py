"""
Run message image model — an image attached to a run message from the mobile PWA.

Images are compressed client-side and stored as base64 (without the ``data:`` prefix)
in their own table so that listing/polling run messages never loads the blobs. They
ride along in the agent run payload only while their message is still pending, then the
agent writes them to disk in the project clone and points the CLI prompt at them.
"""
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import Base

if TYPE_CHECKING:
    from models.run_message import RunMessage


class RunMessageImage(Base):
    """
    A single image attached to a run message.

    Attributes:
        id: Unique identifier.
        run_message_id: Owning run message.
        mime: Image MIME type (e.g. ``image/jpeg``).
        filename: Original file name, for display and disk naming.
        data: Base64-encoded image bytes (no ``data:`` prefix), stored as LONGTEXT on MariaDB.
    """

    __tablename__ = "run_message_images"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    run_message_id: Mapped[int] = mapped_column(
        ForeignKey("run_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mime: Mapped[str] = mapped_column(String(64), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False, default="image")
    data: Mapped[str] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    message: Mapped["RunMessage"] = relationship("RunMessage", back_populates="images")

    def __repr__(self) -> str:
        return f"<RunMessageImage id={self.id} message={self.run_message_id} mime={self.mime}>"
