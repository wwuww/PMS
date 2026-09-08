"""交班服务（M3，FR-QT 交班/现金对账）。

开班登记备用金；交班时按 `应交现金 = 备用金 + 班内现金收款` 计算（现金收款来自
Payment(created_by=收银员, method=CASH, created_at>=开班时间) 聚合），差异 = 实点 − 应交。
不解耦 Payment 表，靠收银员标识 + 时间戳聚合，保证与收银账务一致（单一事实源）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.base import ShiftClosed, utc_now
from app.events.bus import event_bus
from app.models import Bill, BillItem, Payment, ShiftHandover


class ShiftService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def open_shift(
        self, tenant_id: str, hotel_id: int, cashier: str, opening_float_cents: int = 0
    ) -> ShiftHandover:
        if opening_float_cents < 0:
            raise ValueError("备用金不可为负")
        shift = ShiftHandover(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            cashier=cashier,
            status="OPEN",
            opening_float_cents=opening_float_cents,
            opened_at=utc_now().isoformat(),
        )
        self.session.add(shift)
        await self.session.commit()
        await self.session.refresh(shift)
        return shift

    async def _cash_in_shift(self, shift: ShiftHandover) -> int:
        """班内现金收款合计（分）：收银员本班在店 CASH 收款。"""
        opened_dt = datetime.fromisoformat(shift.opened_at) if shift.opened_at else datetime.min
        rows = await self.session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .select_from(Payment)
            .join(Bill, Bill.id == Payment.bill_id)
            .where(
                Bill.hotel_id == shift.hotel_id,
                Bill.tenant_id == shift.tenant_id,
                Payment.method == "CASH",
                Payment.created_by == shift.cashier,
                Payment.created_at >= opened_dt,
            )
        )
        return int(rows.scalar() or 0)

    async def _received_in_shift(self, shift: ShiftHandover) -> int:
        """班内实收合计（分）：本班收银员在本店的**全部支付方式**收款。"""
        opened_dt = datetime.fromisoformat(shift.opened_at) if shift.opened_at else datetime.min
        rows = await self.session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .select_from(Payment)
            .join(Bill, Bill.id == Payment.bill_id)
            .where(
                Bill.hotel_id == shift.hotel_id,
                Bill.tenant_id == shift.tenant_id,
                Payment.created_by == shift.cashier,
                Payment.created_at >= opened_dt,
            )
        )
        return int(rows.scalar() or 0)

    async def _receivable_in_shift(self, shift: ShiftHandover) -> int:
        """班内应收合计（分）：本班新增的正向应收条目（房租/杂费），不含折扣与冲减。"""
        opened_dt = datetime.fromisoformat(shift.opened_at) if shift.opened_at else datetime.min
        rows = await self.session.execute(
            select(func.coalesce(func.sum(BillItem.amount), 0))
            .select_from(BillItem)
            .join(Bill, Bill.id == BillItem.bill_id)
            .where(
                Bill.hotel_id == shift.hotel_id,
                Bill.tenant_id == shift.tenant_id,
                BillItem.created_by == shift.cashier,
                BillItem.created_at >= opened_dt,
                BillItem.amount > 0,
            )
        )
        return int(rows.scalar() or 0)

    async def close_shift(
        self, shift: ShiftHandover, counted_cash_cents: int, note: str = ""
    ) -> ShiftHandover:
        if shift.status == "CLOSED":
            return shift
        expected = shift.opening_float_cents + await self._cash_in_shift(shift)
        # M23（验收清单#11）交班三口径：现金流 / 实收 / 应收
        shift.received_cents = await self._received_in_shift(shift)
        shift.receivable_cents = await self._receivable_in_shift(shift)
        shift.expected_cash_cents = expected
        shift.counted_cash_cents = counted_cash_cents
        shift.discrepancy_cents = counted_cash_cents - expected
        shift.status = "CLOSED"
        shift.closed_at = utc_now().isoformat()
        shift.note = note
        self.session.add(shift)
        await self.session.commit()
        await self.session.refresh(shift)

        await event_bus.publish(
            ShiftClosed(
                tenant_id=shift.tenant_id,
                hotel_id=shift.hotel_id,
                shift_id=shift.id,
                cashier=shift.cashier,
                expected_cash=expected,
                counted_cash=counted_cash_cents,
                discrepancy=shift.discrepancy_cents,
            )
        )
        return shift

    async def list_shifts(self, tenant_id: str, hotel_id: int | None = None) -> list[ShiftHandover]:
        stmt = select(ShiftHandover).where(ShiftHandover.tenant_id == tenant_id)
        if hotel_id is not None:
            stmt = stmt.where(ShiftHandover.hotel_id == hotel_id)
        rows = await self.session.execute(stmt)
        return list(rows.scalars())
