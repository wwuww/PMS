"""团队 / 会议排房服务（M15，FR-GROUP）。

编排层：把若干物理房间作为一个 block 分配（锁房预留），到点一键批量入住。
入住仍复用 ``BookingService.check_in`` 的全部副作用（房态/PSB/开账/客史，
以及客档联动会员）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.room_state import InvalidTransition, RoomState, RoomTrigger
from app.models import (
    ALLOC_ASSIGNED,
    ALLOC_CHECKED_IN,
    ALLOC_CHECKED_OUT,
    ALLOC_CHECKED_OUT,
    GROUP_BLOCK_ACTIVE,
    GROUP_BLOCK_CLOSED,
    Bill,
    Booking,
    GroupAllocation,
    GroupBlock,
    Room,
)
from app.services.cashier_service import CashierService
from app.services.audit_service import record as audit_record
from app.services.booking_service import BookingService
from app.services.guest_service import GuestService
from app.services.room_service import RoomService


class GroupBlockService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_block(
        self,
        tenant_id: str,
        hotel_id: int,
        name: str,
        arrival_date: str,
        departure_date: str,
        notes: str | None = None,
    ) -> GroupBlock:
        if departure_date <= arrival_date:
            raise ValueError("离店日期必须晚于入住日期")
        block = GroupBlock(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            name=name,
            arrival_date=arrival_date,
            departure_date=departure_date,
            status="active",
            notes=notes,
        )
        self.session.add(block)
        await self.session.flush()
        return block

    async def list_blocks(
        self,
        tenant_id: str,
        hotel_id: int | None = None,
        limit: int = 5000,
        offset: int = 0,
    ) -> list[GroupBlock]:
        """团队排房列表（M32 性能护栏：Paged limit/offset，默认 5000 兼容既有全量拉取）。"""
        stmt = select(GroupBlock).where(GroupBlock.tenant_id == tenant_id)
        if hotel_id is not None:
            stmt = stmt.where(GroupBlock.hotel_id == hotel_id)
        stmt = stmt.order_by(GroupBlock.id.desc()).limit(limit).offset(offset)
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def get_block(self, tenant_id: str, block_id: int) -> GroupBlock | None:
        block = await self.session.get(GroupBlock, block_id)
        if block is None or block.tenant_id != tenant_id:
            return None
        return block

    async def list_allocations(self, block_id: int) -> list[GroupAllocation]:
        stmt = (
            select(GroupAllocation)
            .where(GroupAllocation.block_id == block_id)
            .order_by(GroupAllocation.id)
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def assign_rooms(
        self,
        block: GroupBlock,
        allocations: list[dict],
    ) -> list[GroupAllocation]:
        """排房：把指定物理房锁为锁房（预留），并记录分配。

        ``allocations`` 每项：``room_no`` / ``room_type_id`` / ``guest_name?`` / ``guest_phone?``。
        仅空净房可排；已被其他活动 block 占用的房拒绝。
        """
        rs = RoomService(self.session)
        created: list[GroupAllocation] = []
        if block.status != GROUP_BLOCK_ACTIVE:
            raise ValueError("团队排房已关闭，不可排房")
        for a in allocations:
            room_no = a["room_no"]
            room = (
                await self.session.execute(
                    select(Room).where(
                        Room.tenant_id == block.tenant_id, Room.room_no == room_no
                    )
                )
            ).scalar_one_or_none()
            if room is None:
                raise ValueError(f"房间 {room_no} 不存在")
            if RoomState(room.state) != RoomState.VACANT_CLEAN:
                raise ValueError(f"房间 {room_no} 非空闲（{room.state}）不可排房")
            busy = (
                await self.session.execute(
                    select(GroupAllocation).where(
                        GroupAllocation.tenant_id == block.tenant_id,
                        GroupAllocation.room_id == room.id,
                        GroupAllocation.status.in_([ALLOC_ASSIGNED, ALLOC_CHECKED_IN]),
                    )
                )
            ).scalar_one_or_none()
            if busy is not None:
                raise ValueError(f"房间 {room_no} 已被其他团队排房")
            # 锁房预留（空净 → 锁房）
            await rs.transition(room, RoomTrigger.LOCK_FOR_ARRIVAL, operator="front_desk")
            alloc = GroupAllocation(
                tenant_id=block.tenant_id,
                block_id=block.id,
                room_id=room.id,
                room_no=room.room_no,
                room_type_id=int(a["room_type_id"]),
                guest_name=a.get("guest_name"),
                guest_phone=a.get("guest_phone"),
                status=ALLOC_ASSIGNED,
            )
            self.session.add(alloc)
            created.append(alloc)
        await self.session.flush()
        return created

    async def check_in_block(
        self, block: GroupBlock, operator: str = "front_desk"
    ) -> list[object]:
        """批量入住：对每个已排房（assigned）分配建预订 + 入住。

        房间在排房时已锁为锁房，``BookingService.check_in`` 直接将其转在住，
        并触发 PSB/开账/客史/会员关联。
        """
        bs = BookingService(self.session)
        gs = GuestService(self.session)
        if block.status != GROUP_BLOCK_ACTIVE:
            raise ValueError("团队排房已关闭，不可入住")
        allocs = await self.list_allocations(block.id)
        checked_in: list[object] = []
        for a in allocs:
            if a.status != ALLOC_ASSIGNED:
                continue
            guest_name = a.guest_name or f"团队-{block.name}"
            if a.guest_phone:
                await gs.create(
                    block.tenant_id, block.hotel_id, guest_name, a.guest_phone
                )
            booking = await bs.create(
                tenant_id=block.tenant_id,
                hotel_id=block.hotel_id,
                room_type_id=a.room_type_id,
                guest_name=guest_name,
                check_in_date=block.arrival_date,
                check_out_date=block.departure_date,
                channel="group",
                guest_phone=a.guest_phone,
                operator=operator,
            )
            booking = await bs.check_in(booking, a.room_no, operator=operator)
            a.status = ALLOC_CHECKED_IN
            self.session.add(a)
            checked_in.append(booking)
        await self.session.flush()
        return checked_in


    # ---------- M31：团队分批结账（验收 #10） ----------

    async def _alloc_open_bill(self, block: GroupBlock, alloc: GroupAllocation) -> tuple[Booking, Bill] | tuple[None, None]:
        """定位 allocation 对应的在住预订与 OPEN 账单。"""
        bk = (
            await self.session.execute(
                select(Booking)
                .where(
                    Booking.tenant_id == block.tenant_id,
                    Booking.hotel_id == block.hotel_id,
                    Booking.room_no == alloc.room_no,
                    Booking.channel == "group",
                    Booking.status == "checked_in",
                )
                .order_by(Booking.id.desc())
            )
        ).scalars().first()
        if bk is None:
            return None, None
        bill = (
            await self.session.execute(
                select(Bill).where(
                    Bill.tenant_id == block.tenant_id,
                    Bill.booking_id == bk.id,
                    Bill.status == "OPEN",
                )
            )
        ).scalars().first()
        return bk, bill

    async def settle_allocation(
        self, block: GroupBlock, alloc_id: int, operator: str = "front_desk"
    ) -> dict:
        """逐间分批结账：结清该间账单（余额自动现金补收）并退房释放房间。

        - 余额 >0 自动按 CASH 补收（分批现结场景）；<0（多收）按 CASH 退回。
        - 结账后联动 check-out（空脏+清扫单），团主侧经 settlement 汇总视图跟踪进度。
        """
        alloc = await self.session.get(GroupAllocation, alloc_id)
        if alloc is None or alloc.tenant_id != block.tenant_id or alloc.block_id != block.id:
            raise ValueError(f"团队成员不存在：{alloc_id}")
        if alloc.status != ALLOC_CHECKED_IN:
            raise ValueError(f"该间未在住（{alloc.status}），无需结账")
        bk, bill = await self._alloc_open_bill(block, alloc)
        if bk is None or bill is None:
            raise ValueError(f"房间 {alloc.room_no} 未找到在住预订或在开账单")

        bs = BookingService(self.session)
        if bk.status == "checked_in":
            await bs.check_out(bk, operator=operator)
        # 分批结账即该间退出团队在住序列
        alloc.status = ALLOC_CHECKED_OUT
        # 分批结账即该间退出团队在住序列
        alloc.status = ALLOC_CHECKED_OUT

        cs = CashierService(self.session)
        if bill.balance > 0:
            await cs.take_payment(bill, "CASH", bill.balance, operator=operator)
        elif bill.balance < 0:
            await cs.refund(bill, -bill.balance, operator=operator, method="CASH")
        await cs.settle(bill, operator=operator)

        await audit_record(
            self.session,
            block.tenant_id,
            "group.settle_allocation",
            actor=operator,
            resource_type="group_block",
            resource_id=block.id,
            hotel_id=block.hotel_id,
            detail={"allocation_id": alloc.id, "room_no": alloc.room_no, "bill_id": bill.id},
        )
        summary = await self.settlement(block)
        row = next(r for r in summary["rows"] if r["allocation_id"] == alloc.id)
        row["block_settled_count"] = summary["settled_allocations"]
        row["block_total_count"] = summary["total_allocations"]
        return row

    async def settlement(self, block: GroupBlock) -> dict:
        """团主结算汇总：逐间账单状态与整团进度。"""
        allocs = await self.list_allocations(block.id)
        rows = []
        total_cents = 0
        settled_cents = 0
        settled_cnt = 0
        for a in allocs:
            bk, bill = await self._alloc_open_bill(block, a)
            settled = False
            total = 0
            if bill is not None:
                # Bill 无总额列：总额 = Σ明细金额（应收口径）
                total = sum(int(i.amount) for i in bill.items)
                settled = bill.status == "SETTLED"
            elif a.status == ALLOC_CHECKED_IN:
                settled = False  # 在住但账单异常缺失 → 视为未结
            else:
                settled = True  # 未入住/已退出行不计入待结
                total = 0
            rows.append({
                "allocation_id": a.id,
                "room_no": a.room_no,
                "guest_name": a.guest_name,
                "booking_id": bk.id if bk else None,
                "bill_id": bill.id if bill else None,
                "total_cents": total,
                "settled": settled,
            })
            total_cents += total
            if settled:
                settled_cnt += 1
                settled_cents += total
        return {
            "block_id": block.id,
            "status": block.status,
            "total_allocations": len(allocs),
            "settled_allocations": settled_cnt,
            "total_cents": total_cents,
            "settled_cents": settled_cents,
            "rows": rows,
        }

    async def close_block(self, block: GroupBlock) -> GroupBlock:
        block.status = GROUP_BLOCK_CLOSED
        self.session.add(block)
        await self.session.flush()
        return block
