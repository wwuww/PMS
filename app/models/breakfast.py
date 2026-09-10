"""M37-④ 早餐券（breakfast_tickets）。

对齐维也纳 PMS 数据字典 ``Breakfast``（17 字段 → 我方 16，datetime 降为 ``String(10)``）。
券随订单发放（``card_type=0`` 接待单 / 1 临时卡），餐厅核销（幂等：已核销再核返回冲突）。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class BreakfastTicket(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """早餐券（送早/兑早/购早）。"""

    __tablename__ = "breakfast_tickets"

    __table_args__ = (
        UniqueConstraint("tenant_id", "ticket_no", name="uq_bf_tenant_ticket_no"),
        Index("ix_bf_tenant_booking", "tenant_id", "booking_id"),
        Index("ix_bf_tenant_type", "tenant_id", "ticket_type"),
        Index("ix_bf_tenant_used", "tenant_id", "is_used", "valid_to"),
    )

    hotel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hotels.id"), nullable=False
    )
    ticket_no: Mapped[str] = mapped_column(String(32), nullable=False)  # 券编号（租户内唯一）
    booking_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("bookings.id"), nullable=True
    )
    room_no: Mapped[str | None] = mapped_column(String(16), nullable=True)
    card_type: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )  # 0 接待单 / 1 临时卡
    ticket_type: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )  # 0 送早 / 5 兑早 / 9 购早
    ticket_type_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    valid_from: Mapped[str | None] = mapped_column(String(10), nullable=True)
    valid_to: Mapped[str | None] = mapped_column(String(10), nullable=True)
    used_business_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    shift_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operator: Mapped[str] = mapped_column(String(64), nullable=False, default="front_desk")
    memo: Mapped[str | None] = mapped_column(String(255), nullable=True)
