"""RateCode 价格码（SRS v1.1 FR-JG-06：渠道×会员等级×协议×房型×入住类型）。

设计期即落地五维建模（P0，设计期补充不加排期）——dev-plan v1.3。
"""

from sqlalchemy import Boolean, ForeignKey, BigInteger, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class RateCode(IntPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "rate_codes"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # 五维：渠道 / 会员等级 / 协议类型 / 房型 / 入住类型
    channel: Mapped[str] = mapped_column(String(32), default="direct")  # direct/ota_ctrip/ota_meituan/...
    member_level: Mapped[str] = mapped_column(String(16), default="none")  # none/silver/gold/...
    agreement_type: Mapped[str] = mapped_column(String(16), default="none")  # none/walk_in/corporate/long_stay
    room_type_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("room_types.id"))
    stay_type: Mapped[str] = mapped_column(String(16), default="daily")  # daily/hourly/monthly
    # 计价规则
    discount_pct: Mapped[int] = mapped_column(Integer, default=10000)  # 万分比，10000=无折扣
    restrictions: Mapped[dict] = mapped_column(JSON, default=dict)  # MinLOS/MaxLOS/含早等
    # ── 批次② 字段补全（维也纳字典对齐，全 additive）──
    stay_class: Mapped[str] = mapped_column(String(8), default="DR", nullable=False)  # DR日租/FR全日租/HR半日租/NS夜宵房/SU钟点
    rate_type: Mapped[str] = mapped_column(String(16), default="MULTIPLIER", nullable=False)  # MULTIPLIER倍数/FIXED定值/DELTA加减
    valid_from: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 生效日
    valid_to: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 失效日
    is_overlay: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 是否叠加会员优惠
    week: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 适用星期 "1,2,3,4,5"，空=不限

    def resolve_price(self, base_price: int) -> int:
        """按折扣解析最终价（各触点统一入口：前台/小程序/直连）。

        rate_type:
          - MULTIPLIER（默认）：万分比倍率，base * discount_pct // 10000
          - FIXED：定值（分），discount_pct 即最终价
          - DELTA：加减（分），base + discount_pct
        """
        if self.rate_type == "FIXED":
            return self.discount_pct
        if self.rate_type == "DELTA":
            return base_price + self.discount_pct
        return base_price * self.discount_pct // 10000
