"""前台收银服务（M3，FR-QT-01~09）。

职责：开单 → 加账(房租/杂费) → 收款(现金/预授权/微信/支付宝/银联/储值)
→ 退房结账(多方式分账) → 挂账/退款。余额 = Σ应收 - Σ实收。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.base import BillSettled, utc_now
from app.events.bus import event_bus
from app.models import (
    AdjustmentVoucher,
    AuditLog,
    Bill,
    BillItem,
    Booking,
    BookingStatus,
    Deposit,
    DepositKind,
    DepositStatus,
    Hotel,
    Member,
    Payment,
    Room,
)
from app.services.audit_service import record as audit_record
from app.services.deposit_service import DepositError, DepositService
from app.services.member_service import MemberService
from app.services.room_service import RoomService


class CashierService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def open_bill(
        self,
        tenant_id: str,
        hotel_id: int,
        guest_name: str,
        room_no: str | None = None,
        booking_id: int | None = None,
        source: str | None = None,
    ) -> Bill:
        # 街客账（M3-7）：无预订直接开单时来源记为 WALK_IN，便于财务区分散客挂账
        bill_source = source or ("BOOKING" if booking_id else "WALK_IN")
        bill = Bill(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            bill_no=f"B{int(datetime.now(timezone.utc).timestamp() * 1000 % 1e8):08d}",
            booking_id=booking_id,
            guest_name=guest_name,
            room_no=room_no,
            source=bill_source,
            status="OPEN",
            balance=0,
        )
        self.session.add(bill)
        await self.session.flush()
        return bill

    async def _invalidate_dashboard_cache(self, tenant_id: str) -> None:
        """M30 C4：收银写路径失效店总 dashboard 热点缓存（TTL 兜底 60s）。"""
        try:
            from app.infra.cache import get_cache  # noqa: PLC0415

            await get_cache().invalidate_prefix(f"dashboard:{tenant_id}")
        except Exception:  # noqa: BLE001 - 缓存失效失败不阻断主流程
            pass

    async def add_charge(
        self,
        bill: Bill,
        charge_type: str,
        amount: int,
        description: str = "",
        operator: str = "front_desk",
        business_date: str | None = None,
    ) -> BillItem:
        """加应收条目。amount 为正应收、负冲减。返回 BillItem。"""
        if amount == 0:
            raise ValueError("金额不可为 0")
        item = BillItem(
            tenant_id=bill.tenant_id,
            bill_id=bill.id,
            type=charge_type,
            amount=amount,
            description=description,
            business_date=business_date,
            created_by=operator,
        )
        self.session.add(item)
        bill.balance += amount
        self.session.add(bill)
        await self.session.flush()
        await self._invalidate_dashboard_cache(bill.tenant_id)
        return item

    async def take_payment(
        self,
        bill: Bill,
        method: str,
        amount: int,
        operator: str = "front_desk",
        ref_no: str | None = None,
        is_deposit: bool = False,
    ) -> Payment:
        if amount <= 0:
            raise ValueError("收款金额必须为正")
        pay = Payment(
            tenant_id=bill.tenant_id,
            bill_id=bill.id,
            method=method,
            amount=amount,
            is_deposit=is_deposit,
            ref_no=ref_no,
            created_by=operator,
        )
        self.session.add(pay)
        bill.balance -= amount
        self.session.add(bill)
        await self.session.flush()
        await self._invalidate_dashboard_cache(bill.tenant_id)
        return pay

    async def settle(self, bill: Bill, operator: str = "front_desk") -> Bill:
        """结账。余额须为 0（多退少补已通过 add_charge/退款调整）；置 SETTLED 并发事件。

        M32.18 结账集成：settle 前自动 FIFO 冲抵押金并退余款。
        - 押金足额：冲抵后余额归零，余款自动原路退还（不写 Payment）。
        - 押金不足：冲抵后余额仍 > 0 → 抛 DepositError(DEPOSIT_INSUFFICIENT)，409。
        - 无押金账单：两段均为空操作，沿用既有「balance != 0 → 409」语义（F1 回归保护）。
        """
        if bill.status == "SETTLED":
            return bill

        # ---- M32.18 押金自动冲抵 ----
        if bill.booking_id is not None:
            await self._apply_deposits_to_bill(bill, operator)
            # 冲抵后余额恰为 0 → 退押金余款（不写 Payment，不撬已平账单）
            if bill.balance == 0:
                await self._refund_deposit_surplus(bill, operator)

        # 冲抵后仍结余（押金不足）→ 明确 409，提示缺口
        if bill.balance > 0:
            raise DepositError(
                "DEPOSIT_INSUFFICIENT",
                f"押金不足，需补收 {bill.balance} 分",
            )
        # 既有语义：非押金原因导致的未平 → 409（兼容手工结账场景）
        if bill.balance != 0:
            raise ValueError(f"账单未平（余额 {bill.balance} 分），请先补全收款或退款")

        bill.status = "SETTLED"
        self.session.add(bill)

        # 会员积分：按实收（非押金、非积分支付部分）累积——防积分回流套利
        member = await self._linked_member(bill)
        if member:
            paid = await self._paid_excl_deposit(bill.id)
            points_paid = (
                await self.session.execute(
                    select(func.coalesce(func.sum(Payment.amount), 0)).where(
                        Payment.bill_id == bill.id, Payment.method == "POINTS"
                    )
                )
            ).scalar_one()
            ms = MemberService(self.session)
            await ms.earn_points(member, max(paid - int(points_paid), 0), operator)

        await self.session.commit()
        await self.session.refresh(bill)
        await self._invalidate_dashboard_cache(bill.tenant_id)

        methods = await self._payment_methods(bill.id)
        await event_bus.publish(
            BillSettled(
                tenant_id=bill.tenant_id,
                bill_id=bill.id,
                hotel_id=bill.hotel_id,
                guest_name=bill.guest_name,
                settle_amount=await self._paid_total(bill.id),
                payment_methods=",".join(methods),
            )
        )
        return bill

    # ---- M32.18 押金结账集成 ----
    async def _apply_deposits_to_bill(self, bill: Bill, operator: str) -> int:
        """FIFO 冲抵本账单预订关联的押金到余额。

        仅对 kind=DEPOSIT 且状态为 HELD / PARTIALLY_APPLIED 的押金按创建时间
        升序（FIFO）冲抵，每笔冲抵 min(可用余额, 剩余应收)，写 Payment(method=DEPOSIT)
        并联动 Bill.balance。预授权(PREAUTH) 不在此冲抵（退房结账后由 release 释放）。
        返回实际冲抵总额（分）。
        """
        remaining = bill.balance or 0
        if remaining <= 0:
            return 0
        ds = DepositService(self.session)
        rows = await self.session.execute(
            select(Deposit).where(
                Deposit.tenant_id == bill.tenant_id,
                Deposit.booking_id == bill.booking_id,
                Deposit.kind == DepositKind.DEPOSIT.value,
                Deposit.status.in_([
                    DepositStatus.HELD.value,
                    DepositStatus.PARTIALLY_APPLIED.value,
                ]),
            ).order_by(Deposit.created_at.asc(), Deposit.id.asc())
        )
        applied_total = 0
        for d in list(rows.scalars()):
            if remaining <= 0:
                break
            avail = d.available_cents or 0
            if avail <= 0:
                continue
            amt = min(avail, remaining)
            await ds.apply(
                bill.tenant_id, d.id, amt,
                target_bill_id=bill.id, operator=operator,
            )
            remaining -= amt
            applied_total += amt
        return applied_total

    async def _refund_deposit_surplus(self, bill: Bill, operator: str) -> int:
        """结账余额归零后，退还仍残留可用余额的押金（不写 Payment，不撬已平账单）。

        仅对 kind=DEPOSIT 且 status 仍可退（HELD / PARTIALLY_APPLIED）、available>0 的
        押金全退。返回实际退款总额（分）。
        """
        ds = DepositService(self.session)
        rows = await self.session.execute(
            select(Deposit).where(
                Deposit.tenant_id == bill.tenant_id,
                Deposit.booking_id == bill.booking_id,
                Deposit.kind == DepositKind.DEPOSIT.value,
                Deposit.status.in_([
                    DepositStatus.HELD.value,
                    DepositStatus.PARTIALLY_APPLIED.value,
                ]),
                Deposit.available_cents > 0,
            )
        )
        refunded_total = 0
        for d in list(rows.scalars()):
            avail = d.available_cents or 0
            if avail <= 0:
                continue
            await ds.refund(
                bill.tenant_id, d.id, avail,
                operator=operator,
                note="结账自动退押金余款",
            )
            refunded_total += avail
        return refunded_total

    async def pay_with_points(
        self,
        bill: Bill,
        member_phone: str,
        points: int,
        operator: str = "front_desk",
    ) -> tuple[Payment, object]:
        """积分抵扣支付（M31，验收 #9）：1 积分 = 1 分。

        校验会员存在与积分余额，扣减后落 method=POINTS 收款流水。
        结账再累积积分时扣除积分支付部分，防回流套利（见 settle）。
        """
        if bill.status == "SETTLED":
            raise ValueError("账单已结清")
        ms = MemberService(self.session)
        member = await ms.get_by_phone(bill.tenant_id, member_phone)
        if member is None:
            raise ValueError(f"会员不存在：{member_phone}")
        if points <= 0:
            raise ValueError("积分须为正")
        if bill.balance < points:
            raise ValueError(f"积分抵扣（{points} 分）超过账单余额（{bill.balance} 分）")
        await ms.use_points(member, points, operator)
        pay = await self.take_payment(
            bill,
            "POINTS",
            points,
            operator=operator,
            ref_no=f"member:{member.id}",
        )
        await audit_record(
            self.session,
            bill.tenant_id,
            "payment.points",
            actor=operator,
            resource_type="bill",
            resource_id=bill.id,
            hotel_id=bill.hotel_id,
            detail={"points": points, "member_phone": member_phone},
        )
        return pay, member

    async def refund(
        self, bill: Bill, amount: int, operator: str = "front_desk", method: str = "CASH"
    ) -> Payment:
        """退款（押金退回/多收退回）。以负应收冲平余额。"""
        if amount <= 0:
            raise ValueError("退款金额必须为正")
        # 退款通过一条负向 Payment 体现（账面流出），并冲减余额
        pay = Payment(
            tenant_id=bill.tenant_id,
            bill_id=bill.id,
            method=method,
            amount=-amount,
            created_by=operator,
        )
        self.session.add(pay)
        bill.balance += amount  # 退款增加应收缺口（即减少实收净额）
        self.session.add(bill)
        await self.session.flush()
        return pay

    # ---- 联房结转（M32.16）：从房账务并入主房 ----

    async def transfer_to_master(
        self, tenant_id: str, room_no: str, operator: str = "front_desk"
    ) -> dict:
        """把从房 OPEN 账单的未结余额整体并入主房账单。

        从房账单加等额 REFUND 冲减项归零（随后可正常退房），
        主房账单加 MISC 转入项；组内净额不变，负债集中到主房。
        """
        sub = (
            await self.session.execute(
                select(Booking).where(
                    Booking.tenant_id == tenant_id,
                    Booking.status == BookingStatus.CHECKED_IN,
                    Booking.room_no == room_no,
                )
            )
        ).scalar_one_or_none()
        if sub is None:
            raise ValueError(f"房间 {room_no} 没有在住单")
        if not sub.link_group_id or sub.is_link_master:
            raise ValueError("仅联房从房可并入主房")
        master = (
            await self.session.execute(
                select(Booking).where(
                    Booking.tenant_id == tenant_id,
                    Booking.link_group_id == sub.link_group_id,
                    Booking.is_link_master.is_(True),
                    Booking.status == BookingStatus.CHECKED_IN,
                )
            )
        ).scalar_one_or_none()
        if master is None:
            raise ValueError("联房组内没有在住主房，无法并入")

        sub_bill = (
            await self.session.execute(
                select(Bill).where(
                    Bill.tenant_id == tenant_id,
                    Bill.booking_id == sub.id,
                    Bill.status == "OPEN",
                )
            )
        ).scalar_one_or_none()
        if sub_bill is None or sub_bill.balance == 0:
            raise ValueError("从房没有待并入的未结账务")

        master_bill = (
            await self.session.execute(
                select(Bill).where(
                    Bill.tenant_id == tenant_id,
                    Bill.booking_id == master.id,
                    Bill.status == "OPEN",
                )
            )
        ).scalar_one_or_none()
        if master_bill is None:
            master_bill = await self.open_bill(
                tenant_id,
                master.hotel_id,
                master.guest_name,
                room_no=master.room_no,
                booking_id=master.id,
            )

        amount = sub_bill.balance
        await self.add_charge(
            master_bill,
            "MISC",
            amount,
            description=f"联房转入：从房 {room_no}（{sub.guest_name}）账务并入",
            operator=operator,
        )
        await self.add_charge(
            sub_bill,
            "REFUND",
            -amount,
            description=f"联房转出：账务并入主房 {master.room_no}",
            operator=operator,
        )
        await audit_record(
            self.session,
            tenant_id,
            "settle_to_master",
            actor=operator,
            resource_type="booking_link",
            resource_id=sub.link_group_id,
            detail={"from_room": room_no, "to_room": master.room_no, "amount": amount},
        )
        await self.session.flush()
        return {
            "master_room_no": master.room_no,
            "sub_room_no": room_no,
            "amount": amount,
            "master_bill_balance": master_bill.balance,
            "sub_bill_balance": sub_bill.balance,
        }

    async def issue_adjustment(
        self,
        bill: Bill,
        adjustment_type: str,
        amount_cents: int,
        reason: str = "",
        operator: str = "front_desk",
    ) -> Bill:
        """冲调账（M4-5）：在 OPEN 账单上开具有符号调整凭证，重算余额。

        - 仅允许对未结账账单操作（已结账请走独立红冲流程，本 Sprint 不做）；
        - 原应收/实收条目保持不可变（WORM），余额 = Σ应收 − Σ实收 + Σ调整(有符号)。
        """
        if bill.status == "SETTLED":
            raise ValueError("已结账账单不可直接冲调，请走红冲流程")
        if amount_cents == 0:
            raise ValueError("调整金额不可为 0")
        if adjustment_type not in ("VOID", "ADJUST"):
            raise ValueError("调整类型须为 VOID 或 ADJUST")
        voucher = AdjustmentVoucher(
            tenant_id=bill.tenant_id,
            bill_id=bill.id,
            type=adjustment_type,
            amount_cents=amount_cents,
            reason=reason,
            operator=operator,
        )
        self.session.add(voucher)
        await self.session.flush()
        await self._recompute_balance(bill)
        return bill

    # ---- 内部辅助 ----
    async def _recompute_balance(self, bill: Bill) -> None:
        """按 余额 = Σ应收 − Σ实收 + Σ调整(有符号) 重算，保证冲调账后一致。"""
        items = await self._sum(BillItem.amount, BillItem.bill_id == bill.id)
        pays = await self._sum(Payment.amount, Payment.bill_id == bill.id)
        adjs = await self._sum(AdjustmentVoucher.amount_cents, AdjustmentVoucher.bill_id == bill.id)
        bill.balance = items - pays + adjs
        self.session.add(bill)
        await self.session.flush()

    # ---- 内部辅助 ----
    async def _sum(self, column, *where: object) -> int:
        row = await self.session.execute(select(func.coalesce(func.sum(column), 0)).where(*where))
        return int(row.scalar() or 0)

    async def _linked_member(self, bill: Bill) -> Member | None:
        if not bill.booking_id:
            return None
        bk = await self.session.get(Booking, bill.booking_id)
        if not bk or not bk.guest_phone:
            return None
        ms = MemberService(self.session)
        return await ms.get_by_phone(bill.tenant_id, bk.guest_phone)

    async def _paid_total(self, bill_id: int) -> int:
        row = await self.session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.bill_id == bill_id)
        )
        return int(row.scalar() or 0)

    async def _paid_excl_deposit(self, bill_id: int) -> int:
        row = await self.session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.bill_id == bill_id, Payment.is_deposit.is_(False)
            )
        )
        return int(row.scalar() or 0)

    async def _payment_methods(self, bill_id: int) -> list[str]:
        rows = await self.session.execute(
            select(Payment.method).where(Payment.bill_id == bill_id)
        )
        return list({r[0] for r in rows.all()})
