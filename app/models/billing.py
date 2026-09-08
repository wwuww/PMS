"""前台收银账务模型（M3，FR-QT-01~09）。

金额统一以「分」(int) 存储，规避浮点误差；账单 = 应收条目(BillItem) + 实收(Payment)，
余额 = Σ应收 - Σ实收。押金(Deposit)计入实收，退房时多退少补。
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.adjustment import AdjustmentVoucher
from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class Bill(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """宾客账单（一笔结账单位）。可绑定预订，也可散客挂账。"""

    __tablename__ = "bills"
    # M30 性能（分片键 tenant_id 前导）
    __table_args__ = (
        UniqueConstraint("tenant_id", "bill_no"),
        # 收益最高的单条索引：6 处「查某预订的在开账单」由扫描+回表过滤 → 近唯一命中
        Index("ix_bills_tenant_booking_status", "tenant_id", "booking_id", "status"),
        Index("ix_bills_tenant_hotel_status", "tenant_id", "hotel_id", "status"),
    )

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    bill_no: Mapped[str] = mapped_column(String(32), nullable=False)
    booking_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("bookings.id"), nullable=True, index=True)
    guest_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    room_no: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ar_account_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("ar_accounts.id"), nullable=True, index=True
    )  # M24：挂账协议单位（结账方式 COMPANY 时回填）
    source: Mapped[str] = mapped_column(String(16), default="BOOKING", nullable=False)  # BOOKING|WALK_IN
    status: Mapped[str] = mapped_column(String(16), default="OPEN", nullable=False)  # OPEN|SETTLED
    balance: Mapped[int] = mapped_column(Integer, default=0)  # 分，应收-实收
    items: Mapped[list["BillItem"]] = relationship(
        "BillItem", back_populates="bill", cascade="all, delete-orphan", lazy="selectin"
    )
    payments: Mapped[list["Payment"]] = relationship(
        "Payment", back_populates="bill", cascade="all, delete-orphan", lazy="selectin"
    )
    adjustments: Mapped[list["AdjustmentVoucher"]] = relationship(
        "AdjustmentVoucher", back_populates="bill", cascade="all, delete-orphan", lazy="selectin"
    )


class BillItem(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """账单应收条目（房租/杂费/折扣/冲账）。amount>0 应收，<0 冲减。"""

    __tablename__ = "bill_items"

    # M30 性能：按账单+类型聚合（对账/夜审高频）；加 business_date 尾列支持夜审等值判重
    __table_args__ = (
        Index("ix_bill_items_bill_type", "bill_id", "type"),
        Index("ix_bill_items_bill_type_date", "bill_id", "type", "business_date"),
    )

    bill_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("bills.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # ROOM_CHARGE|MISC|DISCOUNT|REFUND
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str] = mapped_column(String(128), default="")
    business_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # M30：房租条目回填营业日，替换 LIKE 判重
    created_by: Mapped[str] = mapped_column(String(64), default="system")

    bill: Mapped["Bill"] = relationship("Bill", back_populates="items")


class Payment(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """实收记录（现金/预授权/微信/支付宝/银联/储值）。"""

    __tablename__ = "payments"

    bill_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("bills.id"), nullable=False, index=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False)  # CASH|PREAUTH|WECHAT|ALIPAY|UNIONPAY|STORE_VALUE
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 分，正数收款
    is_deposit: Mapped[bool] = mapped_column(default=False)  # 押金标记（退房可退）
    ref_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="system")

    bill: Mapped["Bill"] = relationship("Bill", back_populates="payments")


class ArAccount(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """协议单位挂账账户（M24，验收 #10 公司挂账月结）。

    balance_cents > 0 表示该单位累计未清欠款（挂账即增、还款即减）。
    """

    __tablename__ = "ar_accounts"
    __table_args__ = (UniqueConstraint("tenant_id", "name"),)

    hotel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hotels.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False)  # 单位名称
    contact: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 联系人
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    credit_limit_cents: Mapped[int] = mapped_column(Integer, default=0)  # 信用额度（0=不限）
    balance_cents: Mapped[int] = mapped_column(Integer, default=0)  # 未清欠款（分）
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")  # ACTIVE|CLOSED


class ArRepayment(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """协议单位还款流水（挂账月结回款记录）。"""

    __tablename__ = "ar_repayments"

    ar_account_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ar_accounts.id"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # 分，正数
    method: Mapped[str] = mapped_column(String(16), default="BANK")  # BANK|CASH|WECHAT|ALIPAY|UNIONPAY
    operator: Mapped[str] = mapped_column(String(64), default="front_desk")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
