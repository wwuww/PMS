"""夜审与营业日（M4，FR-YS）。DEC-03 营业日与自然日解耦。

营业日(business_date)可不等于自然日；夜审将 OPEN 营业日翻为 CLOSED 并沉淀不可变日报快照。
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, BigInteger, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class BusinessDay(IntPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "business_days"
    __table_args__ = (UniqueConstraint("hotel_id", "business_date"),)

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    business_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    status: Mapped[str] = mapped_column(String(16), default="OPEN", nullable=False)  # OPEN|CLOSED|SUSPENDED
    audited_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    audited_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    suspended_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 异常挂起原因


class DailyReport(IntPkMixin, TenantMixin, Base):
    """营业日报快照（M4-3），夜审后生成且不可变。"""

    __tablename__ = "daily_reports"

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    business_date: Mapped[str] = mapped_column(String(10), nullable=False)
    arrived_rooms: Mapped[int] = mapped_column(Integer, default=0)
    departed_rooms: Mapped[int] = mapped_column(Integer, default=0)
    occupied_rooms: Mapped[int] = mapped_column(Integer, default=0)
    total_rooms: Mapped[int] = mapped_column(Integer, default=0)
    room_revenue: Mapped[int] = mapped_column(Integer, default=0)  # 分
    other_revenue: Mapped[int] = mapped_column(Integer, default=0)
    total_revenue: Mapped[int] = mapped_column(Integer, default=0)
    adr: Mapped[int] = mapped_column(Integer, default=0)  # 平均房价（分）
    occ_pct: Mapped[int] = mapped_column(Integer, default=0)  # 出租率 * 100
    snapshot: Mapped[str] = mapped_column(Text, default="{}")  # JSON 明细
    # M32.18 押金域三栏（与 shift_handovers 对齐）
    deposit_in_cents: Mapped[int] = mapped_column(Integer, default=0)  # 当日收押
    deposit_out_cents: Mapped[int] = mapped_column(Integer, default=0)  # 当日退押
    deposit_held_cents: Mapped[int] = mapped_column(Integer, default=0)  # 当日在押余额（负债）
