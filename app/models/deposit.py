"""押金与预授权（M32.18 FR-DP）。

**设计要点（详见 ``deliverables/architecture/design-m32-18-deposit-2026-09-07.md``）**

- 单表 ``deposits`` + ``kind ∈ {DEPOSIT, PREAUTH}`` 区分实收押金与预授权冻结。
- **押金不进 Bill**（保护已 SETTLED 账单不被撬开）。冲抵时写 ``Payment(method="DEPOSIT", ref_no=deposit_no)``；
  退款不写 Payment。FORFEITED 是唯一例外，生成 ``BillItem(MISC, +X)`` 计入 ``other_revenue``。
- ``available_cents`` 是冗余字段 = ``amount - applied - refunded - forfeited``，由 service 维持
  恒等（不变式 I1），用于 WHERE 守卫；事务边界由 ``version`` 乐观锁守护。
- ``DepositTransaction`` 是不可变流水（WORM），用于交班/日报按窗口聚合与审计溯源。
- 9 个状态按 kind 取合法子集（不变式 I4），由 service 守卫 + 测试断言。
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


# ---------- 枚举 ----------
class DepositKind(str, Enum):
    DEPOSIT = "DEPOSIT"  # 实收押金（真实资金流入，需原路退还）
    PREAUTH = "PREAUTH"  # 预授权冻结（仅冻结额度，需释放或转实收）


class DepositStatus(str, Enum):
    # kind=DEPOSIT
    HELD = "HELD"                              # 在押（默认初态）
    PARTIALLY_APPLIED = "PARTIALLY_APPLIED"    # 部分冲抵
    APPLIED = "APPLIED"                        # 已冲抵（终态）
    REFUNDED = "REFUNDED"                      # 已退还（终态）
    FORFEITED = "FORFEITED"                    # 已没收（终态，计入营收）FR-DP-34
    VOID = "VOID"                              # 已作废（终态）FR-DP-33
    # kind=PREAUTH
    AUTHORIZED = "AUTHORIZED"                  # 已授权（额度冻结）
    CAPTURED = "CAPTURED"                      # 已转实收（此后等同 HELD 参与冲抵）
    RELEASED = "RELEASED"                      # 已释放（终态，附 release_cause）


class ReleaseCause(str, Enum):
    SETTLED = "SETTLED"  # 结账后释放
    EXPIRED = "EXPIRED"  # T+30 超期自动释放
    MANUAL = "MANUAL"    # 手动释放


class DepositAction(str, Enum):
    CREATE = "CREATE"    # 收押金 / 发起预授权
    APPLY = "APPLY"      # 冲抵（写 Payment）
    REFUND = "REFUND"    # 退还（不写 Payment，仅动押金表）
    FORFEIT = "FORFEIT"  # 没收（写 BillItem MISC，计营收）
    VOID = "VOID"        # 作废（24h 内、applied==0）
    CAPTURE = "CAPTURE"  # 预授权转实收
    RELEASE = "RELEASE"  # 预授权释放


# 状态合法子集（不变式 I4）
_DEPOSIT_STATUSES = {
    DepositStatus.HELD,
    DepositStatus.PARTIALLY_APPLIED,
    DepositStatus.APPLIED,
    DepositStatus.REFUNDED,
    DepositStatus.FORFEITED,
    DepositStatus.VOID,
}
_PREAUTH_STATUSES = {
    DepositStatus.AUTHORIZED,
    DepositStatus.CAPTURED,
    DepositStatus.PARTIALLY_APPLIED,
    DepositStatus.APPLIED,
    DepositStatus.REFUNDED,
    DepositStatus.RELEASED,
}


def legal_statuses(kind: str) -> set[str]:
    """返回 kind 对应的合法状态集合。"""
    if kind == DepositKind.DEPOSIT.value:
        return {s.value for s in _DEPOSIT_STATUSES}
    if kind == DepositKind.PREAUTH.value:
        return {s.value for s in _PREAUTH_STATUSES}
    return set()


# ---------- 模型 ----------
class Deposit(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """押金 / 预授权（实收或额度冻结）。

    ``available_cents`` 由 service 维持恒等（I1），事务安全由 ``version`` 乐观锁守护。
    """

    __tablename__ = "deposits"
    __table_args__ = (
        UniqueConstraint("tenant_id", "deposit_no", name="uq_deposits_tenant_deposit_no"),
        Index("ix_deposits_tenant_status", "tenant_id", "status"),
        Index("ix_deposits_booking", "tenant_id", "booking_id"),
        Index(
            "ix_deposits_preauth_expiry",
            "tenant_id",
            "kind",
            "status",
            "created_at",
        ),
    )

    hotel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hotels.id"), nullable=False, index=True
    )
    deposit_no: Mapped[str] = mapped_column(String(32), nullable=False)  # D{yymmdd}{seq}
    booking_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("bookings.id"), nullable=True, index=True
    )
    room_no: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bill_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("bills.id"), nullable=True, index=True
    )  # 可空：支持跨账单冲抵
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # DEPOSIT | PREAUTH
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    # CASH|UNIONPAY|WECHAT|ALIPAY|STORE_VALUE|PREAUTH_CAPTURE
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    refunded_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    forfeited_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_cents: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # = amount - applied - refunded - forfeited
    status: Mapped[str] = mapped_column(
        String(16), default=DepositStatus.HELD.value, nullable=False
    )
    release_cause: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # SETTLED|EXPIRED|MANUAL（仅 PREAUTH 终态用）
    currency: Mapped[str] = mapped_column(String(3), default="CNY", nullable=False)
    ref_no: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 外部凭证/预授权号
    payment_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("payments.id"), nullable=True, index=True
    )  # 首笔冲抵 Payment（可反查）
    sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    risk_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    aging_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    refund_channel_override: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # FR-DP-20：如 "WECHAT->CASH"
    post_checkout_refund: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )  # E3：已退房后退款标记
    forfeit_reason: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # FR-DP-34 必填
    operator: Mapped[str] = mapped_column(String(64), default="front_desk", nullable=False)
    version: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # 乐观锁（见 §3.6）
    expires_at: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # ISO8601：仅 PREAUTH
    released_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    captured_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    voided_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)


class DepositTransaction(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """押金 / 预授权不可变流水（WORM）。"""

    __tablename__ = "deposit_transactions"
    __table_args__ = (
        Index("ix_dep_txn_deposit", "deposit_id", "created_at"),
        Index(
            "ix_dep_txn_shift",
            "tenant_id",
            "action",
            "created_at",
        ),  # 交班/日报按窗口聚合
    )

    deposit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("deposits.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    # CREATE|APPLY|REFUND|FORFEIT|VOID|CAPTURE|RELEASE
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # 恒正，方向由 action 决定
    method: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    ref_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bill_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )  # APPLY/FORFEIT 时记录目标账单
    operator: Mapped[str] = mapped_column(String(64), default="front_desk", nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
