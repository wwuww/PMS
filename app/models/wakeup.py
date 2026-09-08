"""叫醒服务模型（M3-7）。

前台为在住客提供按时叫醒；记录房号、叫醒时刻与状态，供前台定时触发与对账。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class WakeUpCall(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """叫醒任务（PENDING → DONE | MISSED | CANCELLED）。"""

    __tablename__ = "wake_up_calls"

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    room_no: Mapped[str] = mapped_column(String(16), nullable=False)
    guest_name: Mapped[str] = mapped_column(String(64), default="")
    call_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    note: Mapped[str] = mapped_column(String(128), default="")
    created_by: Mapped[str] = mapped_column(String(64), default="front_desk")
