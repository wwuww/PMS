"""夜审佣金对账（M4-4，FR-YS 佣金）。

OTA/分销渠道产生的房费收入需按渠道佣金率计提佣金，夜审时自动对账：
- CommissionRule：租户级佣金规则（按渠道设定费率，basis points）；
- CommissionReconciliation：夜审沉淀的不可变佣金对账行（按 酒店×营业日×渠道）。
直订/微信渠道通常不设规则，故仅对配置规则的渠道计提。
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, BigInteger, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class CommissionRule(IntPkMixin, TenantMixin, Base):
    """佣金规则：租户内按渠道设定费率（basis points，10000=100%）。"""

    __tablename__ = "commission_rules"
    __table_args__ = (UniqueConstraint("tenant_id", "channel"),)

    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    rate_bps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 费率（基点）
    note: Mapped[str] = mapped_column(String(255), default="")


class CommissionReconciliation(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """佣金对账行（夜审生成，不可变快照）。"""

    __tablename__ = "commission_reconciliations"
    __table_args__ = (UniqueConstraint("hotel_id", "business_date", "channel"),)

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    business_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    room_revenue_cents: Mapped[int] = mapped_column(Integer, default=0)  # 计提基数（佣金性房费收入，分）
    commission_rate_bps: Mapped[int] = mapped_column(Integer, default=0)
    commission_cents: Mapped[int] = mapped_column(Integer, default=0)  # 应计佣金（分）
    status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)  # PENDING|RECONCILED
    reconciled_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
