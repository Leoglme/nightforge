"""
Quota snapshot — a reading of the Claude Max usage buckets for a machine.
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base

if TYPE_CHECKING:
    pass


class QuotaSnapshot(Base):
    """
    A point-in-time reading of the Claude usage buckets on a machine.

    Attributes:
        id: Unique identifier.
        machine_id: Machine the reading came from.
        bucket: Bucket key (five_hour, seven_day, seven_day_opus, ...).
        utilization: Utilization fraction 0.0 -> 1.0.
        resets_at: ISO timestamp when the bucket next rolls off.
        created_at: When the snapshot was taken.
    """

    __tablename__ = "quota_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), nullable=False, index=True)
    bucket: Mapped[str] = mapped_column(String(40), nullable=False)
    utilization: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    resets_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
