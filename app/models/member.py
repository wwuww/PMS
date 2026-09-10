"""会员 CRM 模型（M13，FR-MB）。

连锁场景下 tenant_id 共享会员主数据，hotel_id 记录归属门店；
储值/积分在租户内跨店通用（客史标签跨店可查）。
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, BigInteger, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class Member(IntPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("tenant_id", "phone"),)

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[str] = mapped_column(String(16), default="NORMAL", nullable=False)  # NORMAL|SILVER|GOLD|PLATINUM
    stored_value: Mapped[int] = mapped_column(Integer, default=0)  # 分
    points: Mapped[int] = mapped_column(Integer, default=0)
    stays: Mapped[int] = mapped_column(Integer, default=0)  # 入住次数
    total_spend: Mapped[int] = mapped_column(Integer, default=0)  # 分
    # ── 批次② 字段补全（维也纳字典对齐，全 additive）──
    member_no: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 会员号（对外可读编号）
    card_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 卡类型（贵宾/钻石/至尊/绅士）
    join_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 入会日期 YYYY-MM-DD
