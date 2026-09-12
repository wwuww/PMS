"""押金与预授权域服务（M32.18 T03）。

设计文档：``deliverables/architecture/design-m32-18-deposit-2026-09-07.md`` §3.4-§3.5。
错误码规范：``§3.4 错误码表``。事务约定：``§9.3``（service 只 flush，路由显式 commit）。

**核心铁律（务必分清）**
- **收押金不碰 Bill**，**冲抵写 Payment**（不写 BillItem），**退款不写 Payment**（不动 Bill.balance）。
- **FORFEITED 是唯一例外**：没收时写 ``BillItem(type=MISC, amount=+X)`` 计入 ``other_revenue``。
- **乐观锁**：所有写动作 ``version`` 字段 ``+1``，并发场景由路由层传 ``expected_version`` 守护。
- **不可变流水**：``DepositTransaction`` 只追加，不更新不删除（WORM 风格）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import Bill, BillItem, Payment
from app.models.deposit import (
    Deposit,
    DepositAction,
    DepositKind,
    DepositStatus,
    DepositTransaction,
    ReleaseCause,
    legal_statuses,
)
from app.models.tenant import Hotel
from app.services.audit_service import record as audit_record

# ---------- 错误 ----------
class DepositError(Exception):
    """押金域业务错误，路由层统一转换为 HTTP 409/404。"""

    def __init__(self, code: str, message: str | None = None) -> None:
        self.code = code
        self.message = message or code
        super().__init__(self.message)


# ---------- 状态转移与守卫 ----------
_TERMINAL = {
    DepositStatus.APPLIED.value,
    DepositStatus.REFUNDED.value,
    DepositStatus.FORFEITED.value,
    DepositStatus.VOID.value,
    DepositStatus.RELEASED.value,
}

# 可冲抵池：DEPOSIT ∪ {HELD, PARTIALLY_APPLIED}  ∪  PREAUTH ∩ {CAPTURED}
_APPLICABLE_POOL = {
    (DepositKind.DEPOSIT.value, DepositStatus.HELD.value),
    (DepositKind.DEPOSIT.value, DepositStatus.PARTIALLY_APPLIED.value),
    (DepositKind.PREAUTH.value, DepositStatus.CAPTURED.value),
}

# 允许的实收押金方式（FR-DP-02/03：UNIONPAY 须走预授权）
_DEPOSIT_METHODS = {"CASH", "WECHAT", "ALIPAY", "STORE_VALUE"}
_PREAUTH_METHODS = {"CASH", "WECHAT", "ALIPAY", "UNIONPAY", "STORE_VALUE"}


# ---------- Service ----------
class DepositService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- 业务主入口 ----
    async def create(
        self,
        tenant_id: str,
        hotel_id: int,
        *,
        kind: str,
        method: str,
        amount_cents: int,
        booking_id: int | None = None,
        room_no: str | None = None,
        bill_id: int | None = None,
        ref_no: str | None = None,
        currency: str = "CNY",
        operator: str = "front_desk",
        note: str | None = None,
        actor: str | None = None,
    ) -> Deposit:
        """收实收押金 / 冻结预授权。

        - ``kind=DEPOSIT`` → ``status=HELD``，available=amount
        - ``kind=PREAUTH`` → ``status=AUTHORIZED``，available=amount，expires_at=now+30d

        **不**触碰 Bill.balance（押金不进 Bill）。**不**写 Payment（收押金不产生实收记账）。
        """
        # --- 守卫 ---
        if amount_cents < 1 or amount_cents > 99_999_999:
            raise DepositError(
                "DEPOSIT_AMOUNT_OUT_OF_RANGE",
                f"金额需在 [1, 99999999] 分之间，当前 {amount_cents}",
            )
        if kind not in (DepositKind.DEPOSIT.value, DepositKind.PREAUTH.value):
            raise DepositError("DEPOSIT_KIND_INVALID", f"kind 仅支持 DEPOSIT/PREAUTH，当前 {kind!r}")
        if kind == DepositKind.DEPOSIT.value and method not in _DEPOSIT_METHODS:
            raise DepositError(
                "DEPOSIT_UNIONPAY_NEED_PREAUTH",
                f"实收押金不支持 {method!r}（银行卡请走预授权）",
            )
        if kind == DepositKind.PREAUTH.value and method not in _PREAUTH_METHODS:
            raise DepositError("DEPOSIT_METHOD_NOT_ALLOWED", f"预授权方式 {method!r} 非法")

        # 跨租户校验：bill_id
        if bill_id is not None:
            bill = await self.session.get(Bill, bill_id)
            if bill is None or bill.tenant_id != tenant_id:
                raise DepositError("DEPOSIT_BILL_MISMATCH", f"账单 {bill_id} 不属于本租户")
            if bill.status == "SETTLED":
                raise DepositError("DEPOSIT_BILL_SETTLED", "账单已结账，不可再收押金")

        # 幂等键：同租户 ref_no 唯一
        if ref_no:
            dup = await self.session.execute(
                select(Deposit).where(
                    Deposit.tenant_id == tenant_id,
                    Deposit.ref_no == ref_no,
                )
            )
            if dup.scalar_one_or_none():
                raise DepositError("DEPOSIT_REF_NO_DUPLICATE", f"ref_no={ref_no!r} 已存在")

        # 酒店存在性
        hotel = await self.session.get(Hotel, hotel_id)
        if hotel is None or hotel.tenant_id != tenant_id:
            raise DepositError("DEPOSIT_HOTEL_INVALID", f"酒店 {hotel_id} 不属于本租户")

        # --- 构造 Deposit ---
        deposit_no = await self._generate_deposit_no(tenant_id)
        if kind == DepositKind.DEPOSIT.value:
            status = DepositStatus.HELD.value
            expires_at: str | None = None
        else:
            status = DepositStatus.AUTHORIZED.value
            expires_at = (datetime.now(UTC) + timedelta(days=30)).isoformat(timespec="seconds")

        deposit = Deposit(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            deposit_no=deposit_no,
            booking_id=booking_id,
            room_no=room_no,
            bill_id=bill_id,
            kind=kind,
            method=method,
            amount_cents=amount_cents,
            applied_cents=0,
            refunded_cents=0,
            forfeited_cents=0,
            available_cents=amount_cents,
            status=status,
            currency=currency,
            ref_no=ref_no,
            operator=operator,
            version=0,
            expires_at=expires_at,
            note=note,
        )
        self.session.add(deposit)
        await self.session.flush()  # 取 id

        # 流水
        await self._write_txn(
            deposit,
            action=DepositAction.CREATE.value,
            amount_cents=amount_cents,
            method=method,
            ref_no=ref_no,
            bill_id=bill_id,
            operator=operator,
            note=note,
        )
        # 审计
        await audit_record(
            self.session,
            tenant_id=tenant_id,
            action="deposit.create",
            actor=actor or operator,
            resource_type="deposit",
            resource_id=str(deposit.id),
            hotel_id=hotel_id,
            detail={
                "deposit_no": deposit_no,
                "kind": kind,
                "method": method,
                "amount": amount_cents,
                "booking_id": booking_id,
                "room_no": room_no,
            },
        )
        return deposit

    async def list(
        self,
        tenant_id: str,
        *,
        hotel_id: int | None = None,
        booking_id: int | None = None,
        room_no: str | None = None,
        status: str | None = None,
        kind: str | None = None,
        limit: int = 50,
    ) -> list[Deposit]:
        """列表查询，支持多种过滤；limit 上限 200。"""
        limit = max(1, min(int(limit), 200))
        stmt = select(Deposit).where(Deposit.tenant_id == tenant_id)
        if hotel_id is not None:
            stmt = stmt.where(Deposit.hotel_id == hotel_id)
        if booking_id is not None:
            stmt = stmt.where(Deposit.booking_id == booking_id)
        if room_no is not None:
            stmt = stmt.where(Deposit.room_no == room_no)
        if status is not None:
            stmt = stmt.where(Deposit.status == status)
        if kind is not None:
            stmt = stmt.where(Deposit.kind == kind)
        stmt = stmt.order_by(Deposit.id.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars())

    async def get(self, tenant_id: str, deposit_id: int) -> Deposit:
        """详情。返回 Deposit 对象（调用方按需加载 transactions）。"""
        d = await self.session.get(Deposit, deposit_id)
        if d is None or d.tenant_id != tenant_id:
            raise DepositError("DEPOSIT_NOT_FOUND", f"押金 {deposit_id} 不存在")
        return d

    async def get_with_transactions(self, tenant_id: str, deposit_id: int) -> tuple[Deposit, list[DepositTransaction]]:
        d = await self.get(tenant_id, deposit_id)
        res = await self.session.execute(
            select(DepositTransaction)
            .where(DepositTransaction.deposit_id == d.id)
            .order_by(DepositTransaction.created_at.asc())
        )
        return d, list(res.scalars())

    async def _find_open_bill_id(self, tenant_id: str, booking_id: int) -> int | None:
        """取该订单当前在开的账单（多笔时取最新）。用于冲抵的目标账单兜底。"""
        res = await self.session.execute(
            select(Bill.id)
            .where(
                Bill.tenant_id == tenant_id,
                Bill.booking_id == booking_id,
                Bill.status == "OPEN",
            )
            .order_by(Bill.id.desc())
            .limit(1)
        )
        return res.scalar_one_or_none()

    # ---- 冲抵 / 退款 / 作废 / 没收 / 释放 ----
    async def apply(
        self,
        tenant_id: str,
        deposit_id: int,
        amount_cents: int,
        *,
        target_bill_id: int | None = None,
        operator: str = "front_desk",
        expected_version: int | None = None,
        actor: str | None = None,
    ) -> Deposit:
        """冲抵：写 Payment（method=DEPOSIT）+ Bill.balance -= amount。

        **不**写 BillItem（避免重复计营收）。
        """
        d = await self.get(tenant_id, deposit_id)
        if (d.kind, d.status) not in _APPLICABLE_POOL:
            raise DepositError(
                "DEPOSIT_NOT_HELD",
                f"当前状态 {d.kind}/{d.status} 不可冲抵",
            )
        if amount_cents < 1 or amount_cents > d.available_cents:
            raise DepositError(
                "DEPOSIT_INSUFFICIENT",
                f"冲抵金额 {amount_cents} 超出可用余额 {d.available_cents}",
            )

        bill_id = target_bill_id or d.bill_id
        if bill_id is None and d.booking_id is not None:
            # 开押时不绑账单是常态（快捷面板只带 booking_id + room_no，押金管理页同样
            # 不采集账单）。冲抵在业务上就是「抵这位客人的账」，因此回退到该订单的在开
            # 账单，否则前端两处冲抵入口都会 100% 撞 DEPOSIT_BILL_REQUIRED。
            # 只用于本次冲抵，不回写 d.bill_id —— 保留跨账单冲抵能力（bill_id 可空的设计意图）。
            bill_id = await self._find_open_bill_id(tenant_id, d.booking_id)
        if bill_id is None:
            raise DepositError("DEPOSIT_BILL_REQUIRED", "冲抵必须指定目标账单")
        bill = await self.session.get(Bill, bill_id)
        if bill is None or bill.tenant_id != tenant_id:
            raise DepositError("DEPOSIT_BILL_MISMATCH", f"账单 {bill_id} 不属于本租户")

        if expected_version is not None and d.version != expected_version:
            raise DepositError(
                "DEPOSIT_VERSION_CONFLICT",
                f"version 不匹配：current={d.version}, expected={expected_version}",
            )

        # 写 Payment（method=DEPOSIT 表示「押金冲抵」，不写 BillItem）。
        # is_deposit=False：这是真实冲抵（客人的钱已抵房费），须计入会员积分基数
        # （_paid_excl_deposit 过滤 is_deposit=True 的旧押金路径）；旧 is_deposit=True
        # 路径为历史遗留，二者不混。
        payment = Payment(
            tenant_id=tenant_id,
            bill_id=bill_id,
            method="DEPOSIT",
            amount=amount_cents,
            is_deposit=False,
            ref_no=d.deposit_no,
            created_by=operator,
        )
        self.session.add(payment)
        await self.session.flush()
        # Bill.balance 联动
        bill.balance = (bill.balance or 0) - amount_cents

        # 更新 Deposit
        d.applied_cents = (d.applied_cents or 0) + amount_cents
        self._recompute_available(d)
        d.status = (
            DepositStatus.APPLIED.value
            if d.applied_cents >= d.amount_cents
            else DepositStatus.PARTIALLY_APPLIED.value
        )
        if d.payment_id is None:
            d.payment_id = payment.id
        d.version = (d.version or 0) + 1

        await self._write_txn(
            d,
            action=DepositAction.APPLY.value,
            amount_cents=amount_cents,
            method=d.method,
            ref_no=d.ref_no,
            bill_id=bill_id,
            operator=operator,
        )
        await audit_record(
            self.session,
            tenant_id=tenant_id,
            action="deposit.apply",
            actor=actor or operator,
            resource_type="deposit",
            resource_id=str(d.id),
            hotel_id=d.hotel_id,
            detail={
                "amount": amount_cents,
                "bill_id": bill_id,
                "payment_id": payment.id,
                "remaining": d.available_cents,
            },
        )
        return d

    async def refund(
        self,
        tenant_id: str,
        deposit_id: int,
        amount_cents: int,
        *,
        operator: str = "front_desk",
        note: str | None = None,
        expected_version: int | None = None,
        actor: str | None = None,
    ) -> Deposit:
        """原路退还。**不**写 Payment，**不**动 Bill.balance。强制审计留痕。"""
        if not note:
            raise DepositError("DEPOSIT_REASON_REQUIRED", "退款必须填写 note（审计必留）")
        d = await self.get(tenant_id, deposit_id)
        if d.status in _TERMINAL:
            raise DepositError(
                "DEPOSIT_ALREADY_SETTLED",
                f"状态 {d.status} 不可再退",
            )
        if amount_cents < 1 or amount_cents > d.available_cents:
            raise DepositError(
                "DEPOSIT_REFUND_EXCEEDS",
                f"退款金额 {amount_cents} 超出可用余额 {d.available_cents}",
            )
        if d.status == DepositStatus.APPLIED.value and d.applied_cents >= d.amount_cents:
            raise DepositError("DEPOSIT_ALREADY_APPLIED", "已全额冲抵的押金不可退")

        if expected_version is not None and d.version != expected_version:
            raise DepositError(
                "DEPOSIT_VERSION_CONFLICT",
                f"version 不匹配：current={d.version}, expected={expected_version}",
            )

        d.refunded_cents = (d.refunded_cents or 0) + amount_cents
        self._recompute_available(d)
        d.status = (
            DepositStatus.REFUNDED.value
            if d.available_cents == 0
            else DepositStatus.PARTIALLY_APPLIED.value
        )
        d.version = (d.version or 0) + 1

        await self._write_txn(
            d,
            action=DepositAction.REFUND.value,
            amount_cents=amount_cents,
            method=d.method,
            ref_no=d.ref_no,
            bill_id=d.bill_id,
            operator=operator,
            note=note,
        )
        await audit_record(
            self.session,
            tenant_id=tenant_id,
            action="deposit.refund",
            actor=actor or operator,
            resource_type="deposit",
            resource_id=str(d.id),
            hotel_id=d.hotel_id,
            detail={
                "amount": amount_cents,
                "method": d.method,
                "ref_no": d.ref_no,
                "note": note,
                "operator": operator,
            },
        )
        return d

    async def void(
        self,
        tenant_id: str,
        deposit_id: int,
        *,
        operator: str = "front_desk",
        reason: str | None = None,
        expected_version: int | None = None,
        actor: str | None = None,
    ) -> Deposit:
        """作废（24h 内、applied==0）。仅 DEPOSIT。"""
        d = await self.get(tenant_id, deposit_id)
        if d.kind != DepositKind.DEPOSIT.value:
            raise DepositError("DEPOSIT_NOT_PREAUTH_OR_DEPOSIT", "仅实收押金可作废")
        if d.status != DepositStatus.HELD.value:
            raise DepositError("DEPOSIT_VOID_NOT_ALLOWED", f"状态 {d.status} 不可作废")
        if d.applied_cents and d.applied_cents > 0:
            raise DepositError("DEPOSIT_VOID_NOT_ALLOWED", "已冲抵部分不可作废")
        # 24h 限制
        created = d.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        if created is not None and datetime.now(UTC) - created > timedelta(hours=24):
            raise DepositError("DEPOSIT_VOID_NOT_ALLOWED", "已超 24 小时，不可作废")
        if expected_version is not None and d.version != expected_version:
            raise DepositError(
                "DEPOSIT_VERSION_CONFLICT",
                f"version 不匹配：current={d.version}, expected={expected_version}",
            )

        d.status = DepositStatus.VOID.value
        d.voided_at = datetime.now(UTC).isoformat(timespec="seconds")
        d.version = (d.version or 0) + 1
        await self._write_txn(
            d,
            action=DepositAction.VOID.value,
            amount_cents=d.amount_cents,
            method=d.method,
            ref_no=d.ref_no,
            bill_id=d.bill_id,
            operator=operator,
            note=reason,
        )
        await audit_record(
            self.session,
            tenant_id=tenant_id,
            action="deposit.void",
            actor=actor or operator,
            resource_type="deposit",
            resource_id=str(d.id),
            hotel_id=d.hotel_id,
            detail={"reason": reason, "amount": d.amount_cents},
        )
        return d

    async def release(
        self,
        tenant_id: str,
        deposit_id: int,
        *,
        operator: str = "front_desk",
        cause: str = ReleaseCause.MANUAL.value,
        expected_version: int | None = None,
        actor: str | None = None,
    ) -> Deposit:
        """预授权释放。仅 PREAUTH + applied==0。"""
        d = await self.get(tenant_id, deposit_id)
        if d.kind != DepositKind.PREAUTH.value:
            raise DepositError("DEPOSIT_NOT_PREAUTH", "仅预授权可释放")
        if d.applied_cents and d.applied_cents > 0:
            raise DepositError(
                "DEPOSIT_PREAUTH_CAPTURED",
                "已请款，余款请走 refund 而非 release",
            )
        if d.status == DepositStatus.CAPTURED.value:
            # 已请款 = 钱已真实入账（等同 HELD），此时「释放冻结」在语义上不成立，
            # 只能通过 refund 退回。缺此守卫会出现「已收的钱被当作冻结额度释放掉」的资金漏洞。
            raise DepositError(
                "DEPOSIT_PREAUTH_CAPTURED",
                "已请款，请走 refund 而非 release",
            )
        if d.status in (DepositStatus.RELEASED.value, DepositStatus.APPLIED.value):
            raise DepositError("DEPOSIT_ALREADY_SETTLED", f"状态 {d.status} 不可再释放")
        if expected_version is not None and d.version != expected_version:
            raise DepositError(
                "DEPOSIT_VERSION_CONFLICT",
                f"version 不匹配：current={d.version}, expected={expected_version}",
            )

        d.status = DepositStatus.RELEASED.value
        d.release_cause = cause
        d.released_at = datetime.now(UTC).isoformat(timespec="seconds")
        d.version = (d.version or 0) + 1
        await self._write_txn(
            d,
            action=DepositAction.RELEASE.value,
            amount_cents=d.available_cents,
            method=d.method,
            ref_no=d.ref_no,
            bill_id=d.bill_id,
            operator=operator,
            note=f"cause={cause}",
        )
        await audit_record(
            self.session,
            tenant_id=tenant_id,
            action="deposit.release" if cause != ReleaseCause.EXPIRED.value else "deposit.expire",
            actor=actor or operator,
            resource_type="deposit",
            resource_id=str(d.id),
            hotel_id=d.hotel_id,
            detail={"amount": d.amount_cents, "ref_no": d.ref_no, "cause": cause},
        )
        return d

    async def capture(
        self,
        tenant_id: str,
        deposit_id: int,
        *,
        amount_cents: int | None = None,
        operator: str = "front_desk",
        expected_version: int | None = None,
        actor: str | None = None,
    ) -> Deposit:
        """预授权请款（AUTHORIZED → CAPTURED）：把冻结额度转为实收。

        语义（对齐 ``DepositStatus.CAPTURED`` 的定义「已转实收，此后等同 HELD 参与冲抵」）：

        - **不**写 ``Payment``、**不**写 ``BillItem``、**不**动 ``Bill.balance``。
          计营收是后续 :meth:`apply` 的职责（那里写 ``Payment(method="DEPOSIT")``
          并 ``bill.balance -= amount``）。若 capture 也写 Payment 会**重复计营收**。
        - 请款后状态为 ``CAPTURED``，命中 ``_APPLICABLE_POOL`` 中的
          ``(PREAUTH, CAPTURED)``，:meth:`apply` 才可正常冲抵。

        ``amount_cents=None`` 表示全额请款。部分请款时未被请款的部分视同放弃冻结，
        ``amount_cents`` 收敛为实际请款额（流水 note 与审计 detail 记录放弃额度以便追溯）。

        Args:
            tenant_id: 租户 ID。
            deposit_id: 押金（预授权）主键。
            amount_cents: 请款金额（分）；``None`` = 全额请款。
            operator: 操作人（流水/审计留痕）。
            expected_version: 乐观锁期望版本；``None`` 表示不校验。
            actor: 审计 actor，缺省回落到 ``operator``。

        Returns:
            更新后的 :class:`Deposit`（已 flush，未 commit）。

        Raises:
            DepositError: 非预授权、状态不可请款、金额越界或版本冲突。
        """
        d = await self.get(tenant_id, deposit_id)
        if d.kind != DepositKind.PREAUTH.value:
            raise DepositError("DEPOSIT_NOT_PREAUTH", "仅预授权可请款")
        # 幂等性不做：重复请款直接拒（CAPTURED 亦落入此分支）
        if d.status != DepositStatus.AUTHORIZED.value:
            raise DepositError(
                "DEPOSIT_CAPTURE_NOT_ALLOWED",
                f"状态 {d.status} 不可请款",
            )

        authorized_cents = d.amount_cents
        target = amount_cents if amount_cents is not None else authorized_cents
        if target < 1 or target > authorized_cents:
            raise DepositError(
                "DEPOSIT_CAPTURE_EXCEEDS",
                f"请款金额 {target} 超出授权额度 {authorized_cents}",
            )
        if expected_version is not None and d.version != expected_version:
            raise DepositError(
                "DEPOSIT_VERSION_CONFLICT",
                f"version 不匹配：current={d.version}, expected={expected_version}",
            )

        released_cents = authorized_cents - target
        d.captured_at = datetime.now(UTC).isoformat(timespec="seconds")
        if released_cents > 0:
            # 部分请款：未请款部分放弃冻结，授权额度收敛为实际请款额
            d.amount_cents = target
            self._recompute_available(d)
        d.status = DepositStatus.CAPTURED.value
        d.version = (d.version or 0) + 1

        await self._write_txn(
            d,
            action=DepositAction.CAPTURE.value,
            amount_cents=target,
            method=d.method,
            ref_no=d.ref_no,
            bill_id=d.bill_id,
            operator=operator,
            note=(
                f"authorized={authorized_cents};released_cents={released_cents}"
                if released_cents > 0
                else None
            ),
        )
        await audit_record(
            self.session,
            tenant_id=tenant_id,
            action="deposit.capture",
            actor=actor or operator,
            resource_type="deposit",
            resource_id=str(d.id),
            hotel_id=d.hotel_id,
            detail={
                "amount": target,
                "authorized": authorized_cents,
                "released_cents": released_cents,
                "remaining": d.available_cents,
            },
        )
        return d

    async def auto_release_expired(
        self,
        tenant_id: str,
        *,
        hotel_id: int | None = None,
        days: int = 30,
        operator: str = "system",
    ) -> dict[str, Any]:
        """扫描超期 PREAUTH，批量 release。供夜审钩子与外部 cron 共用。"""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        stmt = select(Deposit).where(
            Deposit.tenant_id == tenant_id,
            Deposit.kind == DepositKind.PREAUTH.value,
            Deposit.status.in_([
                DepositStatus.AUTHORIZED.value,
                DepositStatus.CAPTURED.value,
            ]),
            Deposit.created_at < cutoff,
        )
        if hotel_id is not None:
            stmt = stmt.where(Deposit.hotel_id == hotel_id)
        res = await self.session.execute(stmt)
        candidates = list(res.scalars())
        released_ids: list[int] = []
        for d in candidates:
            # 若已 captured → 走 refund 而非 release
            if d.status == DepositStatus.CAPTURED.value:
                # CAPTURED 状态的「超期」走 refund（不在本方法范围）
                continue
            # AUTHORIZED + applied==0 → release
            if d.applied_cents and d.applied_cents > 0:
                continue
            try:
                await self.release(
                    tenant_id,
                    d.id,
                    operator=operator,
                    cause=ReleaseCause.EXPIRED.value,
                )
                released_ids.append(d.id)
            except DepositError:
                # 并发下别人已释放；跳过
                continue
        return {"released": len(released_ids), "ids": released_ids}

    # ---- 内部工具 ----
    def _recompute_available(self, d: Deposit) -> None:
        d.available_cents = (
            d.amount_cents
            - (d.applied_cents or 0)
            - (d.refunded_cents or 0)
            - (d.forfeited_cents or 0)
        )
        if d.available_cents < 0:
            # 不变式 I2：绝不允许超发
            raise DepositError("DEPOSIT_INVARIANT_VIOLATION", "available_cents 不可为负")

    async def _write_txn(
        self,
        deposit: Deposit,
        *,
        action: str,
        amount_cents: int,
        method: str = "",
        ref_no: str | None = None,
        bill_id: int | None = None,
        operator: str = "front_desk",
        note: str | None = None,
    ) -> DepositTransaction:
        txn = DepositTransaction(
            tenant_id=deposit.tenant_id,
            deposit_id=deposit.id,
            action=action,
            amount_cents=amount_cents,
            method=method or "",
            ref_no=ref_no,
            bill_id=bill_id,
            operator=operator,
            note=note,
        )
        self.session.add(txn)
        await self.session.flush()
        return txn

    async def _generate_deposit_no(self, tenant_id: str) -> str:
        today = datetime.now(UTC).strftime("%y%m%d")
        prefix = f"D{today}"
        # 简单计数：同租户同日前缀已有多少条
        res = await self.session.execute(
            select(func.count()).select_from(Deposit).where(
                Deposit.tenant_id == tenant_id,
                Deposit.deposit_no.like(f"{prefix}%"),
            )
        )
        seq = (res.scalar() or 0) + 1
        return f"{prefix}{seq:04d}"
