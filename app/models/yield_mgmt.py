"""收益管理 M15 简版调价建议（动态定价起点）。

设计取舍（dev-plan v1.3）：
- 规则驱动的「简版调价建议」而非完整收益管理（M20），先用可解释、可审计的
  启发式把 RevPAR 提升路径跑通；后续 M20 可平滑替换为 ML 模型，接口与落库不变。
- 需求指数来自夜审沉淀的 DailyReport 历史出租率（occ_pct），零额外埋点。
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, BigInteger, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class PricingRule(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """调价规则配置（租户级，单条启用）。

    涨/降价幅度以「bps」存储（万分之一，1500 = 15%）；阈值以百分比整数存储。
    """

    __tablename__ = "pricing_rules"

    name: Mapped[str] = mapped_column(String(64), default="default")
    enabled: Mapped[int] = mapped_column(Integer, default=1)  # 0/1
    # 需求阈值（出租率 %）
    high_occ_threshold: Mapped[int] = mapped_column(Integer, default=85)
    low_occ_threshold: Mapped[int] = mapped_column(Integer, default=50)
    # 幅度上限（bps）
    max_uplift_bps: Mapped[int] = mapped_column(Integer, default=1500)  # 15%
    max_discount_bps: Mapped[int] = mapped_column(Integer, default=1000)  # 10%
    weekend_uplift_bps: Mapped[int] = mapped_column(Integer, default=500)  # 5%
    # 竞品对标策略
    competitor_strategy: Mapped[str] = mapped_column(
        String(16), default="none"
    )  # none|match|undercut
    competitor_undercut_bps: Mapped[int] = mapped_column(Integer, default=300)  # 3%


class PriceRecommendation(IntPkMixin, TenantMixin, Base):
    """调价建议快照（不可变记录，供审核/回访/未来训练）。

    base_price_cents / recommended_price_cents 以「分」存储；adjustment_bps 相对基价的调整。
    """

    __tablename__ = "price_recommendations"

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    room_type_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("room_types.id"), nullable=True)
    business_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    base_price_cents: Mapped[int] = mapped_column(Integer, default=0)
    recommended_price_cents: Mapped[int] = mapped_column(Integer, default=0)
    adjustment_bps: Mapped[int] = mapped_column(Integer, default=0)
    demand_index: Mapped[int] = mapped_column(Integer, default=0)  # 历史出租率均值(%)
    sample_days: Mapped[int] = mapped_column(Integer, default=0)
    rule_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("pricing_rules.id"), nullable=True)
    rationale: Mapped[str] = mapped_column(Text, default="[]")  # JSON list[str]
    status: Mapped[str] = mapped_column(String(16), default="suggested")  # suggested|applied|rejected
