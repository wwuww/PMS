"""移动支付模型（M7-2，微信小程序支付）。

PayOrder 支付单：统一下单 → 用户支付 → 回调确认（幂等）→ 关单/掉单对账。
PayNotify 回调流水：以 notify_id 幂等去重，WORM 留存原始报文基线。
金额统一以「分」(int) 存储。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, BigInteger, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class PayOrder(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """支付单（M7-2）。一笔小程序预订对应一笔待支付订单。"""

    __tablename__ = "pay_orders"
    __table_args__ = (UniqueConstraint("tenant_id", "out_trade_no"),)

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    out_trade_no: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(16), default="WECHAT_MP")  # 预留 ALIPAY_MP 等
    booking_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("bookings.id"), nullable=True, index=True)
    bill_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("bills.id"), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(128), default="")
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # 分，>0
    status: Mapped[str] = mapped_column(String(16), default="CREATED", index=True)  # CREATED|PAID|CLOSED
    prepay_id: Mapped[str | None] = mapped_column(String(64))
    transaction_id: Mapped[str | None] = mapped_column(String(64))  # 渠道支付流水号
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(String(128))


class PayNotify(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """支付回调流水（notify_id 幂等去重 + 报文留痕）。"""

    __tablename__ = "pay_notifies"
    __table_args__ = (UniqueConstraint("tenant_id", "notify_id"),)

    out_trade_no: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    notify_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[str] = mapped_column(String(16), nullable=False)  # PROCESSED|DUPLICATE|REJECTED
