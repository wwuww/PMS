"""叫醒服务（M3-7）。

职责：登记叫醒 → 到点触发(置 DONE) / 漏叫(置 MISSED) / 取消(置 CANCELLED)；
并提供 due_calls 供前台轮询「待叫」列表。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.base import WakeUpCallScheduled, utc_now
from app.events.bus import event_bus
from app.models import WakeUpCall


class WakeUpCallService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        tenant_id: str,
        hotel_id: int,
        room_no: str,
        call_at: datetime,
        guest_name: str = "",
        note: str = "",
        operator: str = "front_desk",
    ) -> WakeUpCall:
        if call_at <= utc_now():
            raise ValueError("叫醒时间须晚于当前时刻")
        call = WakeUpCall(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            room_no=room_no,
            guest_name=guest_name,
            call_at=call_at,
            note=note,
            created_by=operator,
            status="PENDING",
        )
        self.session.add(call)
        await self.session.commit()
        await self.session.refresh(call)
        await event_bus.publish(
            WakeUpCallScheduled(
                tenant_id=tenant_id,
                hotel_id=hotel_id,
                room_no=room_no,
                call_at=call_at.isoformat(),
            )
        )
        return call

    async def mark_done(self, call: WakeUpCall, operator: str = "front_desk") -> WakeUpCall:
        if call.status != "PENDING":
            return call
        call.status = "DONE"
        self.session.add(call)
        await self.session.commit()
        await self.session.refresh(call)
        return call

    async def mark_missed(self, call: WakeUpCall) -> WakeUpCall:
        if call.status != "PENDING":
            return call
        call.status = "MISSED"
        self.session.add(call)
        await self.session.commit()
        await self.session.refresh(call)
        return call

    async def cancel(self, call: WakeUpCall, operator: str = "front_desk") -> WakeUpCall:
        if call.status != "PENDING":
            return call
        call.status = "CANCELLED"
        self.session.add(call)
        await self.session.commit()
        await self.session.refresh(call)
        return call

    async def due_calls(
        self, tenant_id: str, hotel_id: int, before: datetime | None = None
    ) -> list[WakeUpCall]:
        """未完成的叫醒任务（PENDING），按叫醒时刻升序。before 为空则取全部待叫。"""
        stmt = select(WakeUpCall).where(
            WakeUpCall.tenant_id == tenant_id,
            WakeUpCall.hotel_id == hotel_id,
            WakeUpCall.status == "PENDING",
        )
        if before is not None:
            stmt = stmt.where(WakeUpCall.call_at <= before)
        stmt = stmt.order_by(WakeUpCall.call_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars())
