"""投诉工单服务（M28，A2 收尾）：与住客/预订关联，处理流转闭环。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, Complaint
from app.services.audit_service import record as audit_record

VALID_TRANSITIONS = {
    "OPEN": {"HANDLING", "RESOLVED", "CANCELLED"},
    "HANDLING": {"RESOLVED", "CANCELLED"},
    "RESOLVED": set(),
    "CANCELLED": set(),
}


class ComplaintService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        tenant_id: str,
        *,
        hotel_id: int,
        guest_name: str,
        description: str = "",
        booking_id: int | None = None,
        guest_phone: str | None = None,
        room_no: str | None = None,
        source: str = "FRONT_DESK",
        category: str = "SERVICE",
        operator: str = "front_desk",
    ) -> Complaint:
        """创建投诉。若提供 booking_id，自动回填住客姓名/房号（可显式覆盖）。"""
        if booking_id is not None:
            bk = await self.session.get(Booking, booking_id)
            if bk is None or bk.tenant_id != tenant_id:
                raise ValueError(f"关联预订不存在：{booking_id}")
            # 关联预订时以预订档案为准（自动回填住客/手机号/房号）
            guest_name = bk.guest_name or guest_name
            room_no = room_no or bk.room_no
            guest_phone = guest_phone or bk.guest_phone
        c = Complaint(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            booking_id=booking_id,
            guest_name=guest_name,
            guest_phone=guest_phone,
            room_no=room_no,
            source=source,
            category=category,
            status="OPEN",
            description=description,
        )
        self.session.add(c)
        await self.session.flush()
        await audit_record(
            self.session,
            tenant_id,
            "complaint.create",
            actor=operator,
            resource_type="complaint",
            resource_id=c.id,
            hotel_id=hotel_id,
            detail={"booking_id": booking_id, "category": category, "source": source},
        )
        return c

    async def list(
        self,
        tenant_id: str,
        *,
        hotel_id: int | None = None,
        status: str | None = None,
        booking_id: int | None = None,
        guest_phone: str | None = None,
        guest_name: str | None = None,
        limit: int = 5000,
        offset: int = 0,
    ) -> list[Complaint]:
        stmt = select(Complaint).where(Complaint.tenant_id == tenant_id)
        if hotel_id is not None:
            stmt = stmt.where(Complaint.hotel_id == hotel_id)
        if status:
            stmt = stmt.where(Complaint.status == status)
        if booking_id is not None:
            stmt = stmt.where(Complaint.booking_id == booking_id)
        if guest_phone:
            stmt = stmt.where(Complaint.guest_phone == guest_phone)
        if guest_name:
            stmt = stmt.where(Complaint.guest_name.contains(guest_name))
        # M30 性能护栏：多维过滤端点按 limit/offset 分页，避免全量拉取
        stmt = stmt.order_by(Complaint.id.desc()).limit(limit).offset(offset)
        rows = await self.session.execute(stmt)
        return list(rows.scalars())

    async def transition(
        self,
        complaint_id: int,
        *,
        to_status: str,
        operator: str,
        handler: str | None = None,
        resolution: str | None = None,
    ) -> Complaint:
        c = await self.session.get(Complaint, complaint_id)
        if c is None:
            raise ValueError(f"投诉不存在：{complaint_id}")
        allowed = VALID_TRANSITIONS.get(c.status, set())
        if to_status not in allowed:
            raise ValueError(f"非法流转：{c.status} → {to_status}")
        if to_status == "HANDLING" and not handler:
            raise ValueError("受理须指定处理人")
        if to_status == "RESOLVED" and not resolution:
            raise ValueError("办结须填写处理结果")
        c.status = to_status
        if handler:
            c.handler = handler
        if resolution:
            c.resolution = resolution
        if to_status in ("RESOLVED", "CANCELLED"):
            c.handled_at = datetime.now(timezone.utc)
        self.session.add(c)
        await self.session.flush()
        await audit_record(
            self.session,
            c.tenant_id,
            f"complaint.{to_status.lower()}",
            actor=operator,
            resource_type="complaint",
            resource_id=c.id,
            hotel_id=c.hotel_id,
            detail={"handler": c.handler, "resolution": c.resolution},
        )
        return c
