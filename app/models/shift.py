"""前台收银交班（M3，FR-QT 交班/对账）。

班次(Shift)记录收银员当班备用金、应交现金（备用金+班内现金收款）与实点现金，
差异 = 实点 − 应交，用于前台现金对账。不改 Payment 表结构：
应交现金通过 Payment(created_by=收银员, method=CASH, created_at>=开班时间) 聚合得到。
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class ShiftHandover(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """交班记录（一次完整班次：开班→交班）。"""

    __tablename__ = "shift_handovers"

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    cashier: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="OPEN", nullable=False)  # OPEN|CLOSED
    opening_float_cents: Mapped[int] = mapped_column(Integer, default=0)  # 备用金（分）
    expected_cash_cents: Mapped[int] = mapped_column(Integer, default=0)  # 应交现金（交班时计算，分）
    counted_cash_cents: Mapped[int] = mapped_column(Integer, default=0)  # 实点现金（分）
    discrepancy_cents: Mapped[int] = mapped_column(Integer, default=0)  # 差异 = 实点 − 应交（分）
    # 交班三口径（M23，清单#11）：现金流=备用金+班内现金；实收=班内全方式收款；应收=班内应收条目
    received_cents: Mapped[int] = mapped_column(Integer, default=0)  # 班内实收合计（分）
    receivable_cents: Mapped[int] = mapped_column(Integer, default=0)  # 班内应收合计（分）
    # M32.18 押金域三栏（team-lead 裁决，对齐 PM §6.5）：押金不写 Payment，因此需要独立聚合
    deposit_in_cents: Mapped[int] = mapped_column(Integer, default=0)  # 班内收押合计
    deposit_out_cents: Mapped[int] = mapped_column(Integer, default=0)  # 班内退押合计
    deposit_held_cents: Mapped[int] = mapped_column(Integer, default=0)  # 班末在押余额（负债）
    opened_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    closed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")
