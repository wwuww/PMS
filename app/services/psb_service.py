"""PSB 上传队列服务（M3-5）。

职责：入住（enqueue_from_booking）/ 散客登记（enqueue）时生成上报任务；
upload() 执行 mock 上报（置 UPLOADED + 记录报文与上报时间）。失败可重试。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.base import PsbUploaded, utc_now
from app.events.bus import event_bus
from app.models import Booking, PsbUploadTask


def _mask_doc(doc: str | None) -> str | None:
    """证件号脱敏：保留前 4 后 2，中间打码（合规留痕，避免明文落库）。"""
    if not doc:
        return None
    if len(doc) <= 6:
        return doc[:2] + "****"
    return doc[:4] + "****" + doc[-2:]


class PsbService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue_from_booking(self, booking: Booking) -> PsbUploadTask:
        """入住时依据预订自动建上报任务（公安住客登记）。"""
        task = PsbUploadTask(
            tenant_id=booking.tenant_id,
            hotel_id=booking.hotel_id,
            booking_id=booking.id,
            guest_name=booking.guest_name,
            id_doc_no=booking.id_doc_no,
            room_no=booking.room_no,
            status="QUEUED",
            payload={
                "guest_name": booking.guest_name,
                "id_doc_no_masked": _mask_doc(booking.id_doc_no),
                "room_no": booking.room_no,
                "check_in_date": booking.check_in_date,
                "check_out_date": booking.check_out_date,
                "channel": booking.channel,
            },
            operator="check_in",
        )
        self.session.add(task)
        await self.session.flush()
        return task

    async def enqueue(
        self,
        tenant_id: str,
        hotel_id: int,
        guest_name: str,
        id_doc_no: str | None = None,
        room_no: str | None = None,
        operator: str = "front_desk",
    ) -> PsbUploadTask:
        """散客（无预订）现场登记上报。"""
        task = PsbUploadTask(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            booking_id=None,
            guest_name=guest_name,
            id_doc_no=id_doc_no,
            room_no=room_no,
            status="QUEUED",
            payload={
                "guest_name": guest_name,
                "id_doc_no_masked": _mask_doc(id_doc_no),
                "room_no": room_no,
            },
            operator=operator,
        )
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def upload(self, task: PsbUploadTask, operator: str = "system") -> PsbUploadTask:
        """执行上报（mock）：置 UPLOADED，记录上报时间与报文。"""
        if task.status == "UPLOADED":
            return task
        task.status = "UPLOADED"
        task.uploaded_at = utc_now()
        task.operator = operator
        task.error = None
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        await event_bus.publish(
            PsbUploaded(
                tenant_id=task.tenant_id,
                hotel_id=task.hotel_id,
                booking_id=task.booking_id,
                task_id=task.id,
            )
        )
        return task

    async def mark_failed(self, task: PsbUploadTask, error: str) -> PsbUploadTask:
        task.status = "FAILED"
        task.error = error[:255]
        self.session.add(task)
        await self.session.commit()
        await self.session.refresh(task)
        return task

    async def list_tasks(
        self, tenant_id: str, hotel_id: int | None = None, status_: str | None = None
    ) -> list[PsbUploadTask]:
        stmt = select(PsbUploadTask).where(PsbUploadTask.tenant_id == tenant_id)
        if hotel_id is not None:
            stmt = stmt.where(PsbUploadTask.hotel_id == hotel_id)
        if status_:
            stmt = stmt.where(PsbUploadTask.status == status_)
        stmt = stmt.order_by(PsbUploadTask.id.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars())
