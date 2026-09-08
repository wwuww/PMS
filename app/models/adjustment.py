"""冲调账凭证（M4-5，FR-YS-05）。

夜审/结账后发现错账时，不开具反向发票，而是开具一张「有符号」的调整凭证：
- 原应收/实收条目保持不可变（WORM，DEC-04 审计基线）；
- 调整凭证以独立记录体现冲减/补收，余额 = Σ应收 − Σ实收 + Σ调整(有符号)。

type: VOID(红冲) | ADJUST(调账)
amount_cents: 有符号，余额增量（负=冲减应收/退收，正=补收）
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class AdjustmentVoucher(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """冲调账凭证（不可变，仅新增不修改；更正以新凭证体现）。"""

    __tablename__ = "adjustment_vouchers"

    bill_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("bills.id"), nullable=True, index=True
    )
    business_day_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("business_days.id"), nullable=True, index=True
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # VOID|ADJUST
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # 有符号余额增量
    reason: Mapped[str] = mapped_column(String(255), default="")
    operator: Mapped[str] = mapped_column(String(64), default="system")

    bill: Mapped["Bill"] = relationship("Bill", back_populates="adjustments")  # type: ignore[name-defined]
