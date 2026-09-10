"""M37-④ 优惠券（模板 + 实例两表）。

用户拍板：优惠券做「**券模板 + 券实例**」两表（设计文档 D4 建议先单表，但用户已明确要两表）。

- ``CouponTemplate``：券规则（类型/折扣方式/折扣值/有效期/发行总量），支持"一次生成
  N 张同规则券"。
- ``Coupon``：券实例（唯一券号、状态机 ISSUED/USED/VOID/EXPIRED、核销时关联订单/账单）。
  ``template_id`` 可空（向前兼容：无模板的散券）。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class CouponTemplate(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """优惠券模板（券规则）。"""

    __tablename__ = "coupon_templates"

    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_coupon_tpl_tenant_code"),
        Index("ix_coupon_tpl_tenant_valid", "tenant_id", "is_valid"),
    )

    hotel_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("hotels.id"), nullable=True
    )  # 空 = 集团级模板
    code: Mapped[str] = mapped_column(String(32), nullable=False)  # 模板编码（租户内唯一）
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    ticket_type: Mapped[str] = mapped_column(
        String(8), nullable=False, default="VOUCHER"
    )  # VOUCHER 代金券 / FREE 免费券
    discount_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="AMOUNT"
    )  # AMOUNT 定额(分) / PERCENT 折扣(万分比) / FIXED_PRICE 定价值(分)
    discount_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_from: Mapped[str] = mapped_column(String(10), nullable=False)
    valid_to: Mapped[str] = mapped_column(String(10), nullable=False)
    total_quantity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )  # 发行总量（0=不限）
    issued_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    operator: Mapped[str] = mapped_column(String(64), nullable=False, default="front_desk")


class Coupon(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """优惠券实例（可核销的实体券）。"""

    __tablename__ = "coupons"

    __table_args__ = (
        UniqueConstraint("tenant_id", "coupon_no", name="uq_coupons_tenant_coupon_no"),
        Index("ix_coupons_tenant_status", "tenant_id", "status"),
        Index("ix_coupons_tenant_valid", "tenant_id", "status", "valid_to"),
        Index("ix_coupons_tenant_booking", "tenant_id", "booking_id"),
        Index("ix_coupons_tenant_template", "tenant_id", "template_id"),
    )

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("coupon_templates.id"), nullable=True
    )
    coupon_no: Mapped[str] = mapped_column(String(32), nullable=False)
    ticket_type: Mapped[str] = mapped_column(String(8), nullable=False, default="VOUCHER")
    discount_type: Mapped[str] = mapped_column(String(16), nullable=False, default="AMOUNT")
    discount_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_from: Mapped[str] = mapped_column(String(10), nullable=False)
    valid_to: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ISSUED"
    )  # ISSUED|USED|VOID|EXPIRED
    booking_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("bookings.id"), nullable=True
    )
    bill_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("bills.id"), nullable=True
    )
    used_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_cover_other_discount: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_transfer_to_account: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # true 则核销时写 BillItem(DISCOUNT, -amount)
    operator: Mapped[str] = mapped_column(String(64), nullable=False, default="front_desk")
