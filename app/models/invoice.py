"""M37-③ 发票模块（invoices）。

对齐维也纳 PMS 数据字典 ``Invoice``：18 字段照搬 + 4 我方扩展（``invoice_type`` 三态、
``title`` 抬头、``tax_no`` 纳税人识别号、``status`` 作废态）。用 ``bill_id`` 替代维也纳
``OrderID``，并以 ``tenant_id, invoice_no`` 唯一约束保证发票号不重号。

WORM 原则：作废仅置 ``status=VOID``，不删不改金额（审计刚需）。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class Invoice(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """发票（账项-抬头-税号-金额-审批-状态）。

    - ``invoice_no`` 租户内唯一（UQ）。
    - ``consume - invoice > 1000 分（¥10）`` 时 ``approver`` 必填（开票时校验）。
    - ``status`` 仅两态：``ISSUED``（已开）/ ``VOID``（作废，WORM 不改金额）。
    """

    __tablename__ = "invoices"

    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_no", name="uq_invoices_tenant_invoice_no"),
        Index("ix_invoices_tenant_bill", "tenant_id", "bill_id"),
        Index("ix_invoices_tenant_booking", "tenant_id", "booking_id"),
        Index("ix_invoices_tenant_status", "tenant_id", "status"),
    )

    hotel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hotels.id"), nullable=False
    )
    invoice_no: Mapped[str] = mapped_column(String(32), nullable=False)
    bill_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("bills.id"), nullable=True
    )
    booking_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("bookings.id"), nullable=True
    )
    room_no: Mapped[str | None] = mapped_column(String(16), nullable=True)
    guest_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agreement_no: Mapped[str | None] = mapped_column(String(32), nullable=True)
    check_in_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    check_out_at: Mapped[str] = mapped_column(String(32), nullable=False)
    check_in_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    consume_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invoice_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    invoice_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="NORMAL"
    )  # NORMAL|VAT_SPECIAL|ELECTRONIC
    title: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 发票抬头
    tax_no: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 纳税人识别号（专票必填）
    approver: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 审批人
    work_shift: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 班次
    flag: Mapped[str] = mapped_column(String(1), nullable=False, default="1")  # 1用户/2系统/3临时/4修改作废/5删除作废/6转出作废/7非收入
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ISSUED"
    )  # ISSUED|VOID
    operator: Mapped[str] = mapped_column(String(64), nullable=False, default="front_desk")
    memo: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 软启用
