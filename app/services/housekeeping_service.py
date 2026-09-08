"""清扫工单服务（M10-3，FR-APP-03 / FR-FT-04）：退房自动建单 → 派单 → 完成联动净房。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.room_state import RoomTrigger
from app.events.base import HousekeepingDone
from app.events.bus import event_bus
from app.models import HousekeepingTask, Room
from app.services.notification_service import NotificationService
from app.services.room_service import RoomService

TASK_TYPES = ("CLEANUP", "MAINTENANCE", "INSPECT")


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


class HousekeepingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_task(
        self,
        tenant_id: str,
        hotel_id: int,
        room_no: str,
        task_type: str = "CLEANUP",
        assignee: str | None = None,
        note: str = "",
        due_at: datetime | None = None,
        source: str = "MANUAL",
    ) -> HousekeepingTask:
        if task_type not in TASK_TYPES:
            raise ValueError(f"未知工单类型: {task_type}")
        task = HousekeepingTask(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            room_no=room_no,
            task_type=task_type,
            status="ASSIGNED" if assignee else "PENDING",
            assignee=assignee,
            note=note,
            due_at=due_at,
            source=source,
        )
        self.session.add(task)
        await self.session.flush()
        # ② 通知中心推送点：建单即提醒（退房自动派单 / 手动建单均触发，点击深链直达工单）
        await NotificationService(self.session).push(
            tenant_id,
            f"新清扫工单：{task_type}",
            body=f"房间 {room_no} 待处理（来源 {source}）",
            hotel_id=hotel_id,
            ref_type="task",
            ref_id=task.id,
        )
        return task

    async def create_from_checkout(
        self, tenant_id: str, hotel_id: int, room_no: str, operator: str = "front_desk"
    ) -> HousekeepingTask:
        """退房自动派清扫工单（FR-FT-04：退房触发脏房→派单保洁）。"""
        return await self.create_task(
            tenant_id,
            hotel_id,
            room_no,
            task_type="CLEANUP",
            note=f"退房自动生成（操作人 {operator}）",
            source="AUTO_CHECKOUT",
        )

    async def assign(self, task: HousekeepingTask, assignee: str) -> HousekeepingTask:
        if task.status in ("DONE", "CANCELLED"):
            raise ValueError(f"工单已结束（{task.status}）不可派单")
        # M31：免打扰守卫——在住房挂 DND 时暂停清扫派单（维修/查房不受限）
        if task.task_type == "CLEANUP":
            room = (
                await self.session.execute(
                    select(Room).where(
                        Room.tenant_id == task.tenant_id, Room.room_no == task.room_no
                    )
                )
            ).scalars().first()
            if room is not None and getattr(room, "dnd", 0):
                raise ValueError(f"房间 {task.room_no} 免打扰中，暂缓清扫派单")
        task.status = "ASSIGNED"
        task.assignee = assignee
        self.session.add(task)
        await self.session.flush()
        return task

    async def done(self, task: HousekeepingTask, operator: str = "front_desk") -> HousekeepingTask:
        if task.status in ("DONE", "PENDING_INSPECT"):
            return task
        if task.status == "CANCELLED":
            raise ValueError("已取消工单不可完成")
        if task.task_type == "CLEANUP":
            # M32（验收 #38）：保洁完成 → 待检查，主管检查通过后才回归净房可售
            task.status = "PENDING_INSPECT"
            self.session.add(task)
            await self.session.flush()
            await self._notify_inspect(task)
        else:
            task.status = "DONE"
            task.done_at = datetime.now(UTC)
            self.session.add(task)
        await self.session.flush()
        await event_bus.publish(
            HousekeepingDone(
                tenant_id=task.tenant_id,
                task_id=task.id,
                room_no=task.room_no,
                task_type=task.task_type,
            )
        )
        return task

    async def _notify_inspect(self, task: HousekeepingTask) -> None:
        """M32（验收 #38）：保洁完成 → 站内通知主管待检查。"""
        await NotificationService(self.session).push(
            task.tenant_id,
            f"清扫待检查：{task.room_no}",
            f"房间 {task.room_no} 清扫完成，请检查确认后放行可售。",
            hotel_id=task.hotel_id,
            recipient="housekeeping_manager",
            ref_type="task",
            ref_id=task.id,
            level="normal",
        )

    async def inspect(
        self,
        task: HousekeepingTask,
        passed: bool,
        operator: str = "supervisor",
        note: str = "",
    ) -> HousekeepingTask:
        """主管检查（M32，验收 #38/#39）：通过 → 净房可售；不通过 → 退回返工。"""
        if task.status != "PENDING_INSPECT":
            raise ValueError(f"工单不在待检查状态（{task.status}）")
        if passed:
            task.status = "DONE"
            task.done_at = datetime.now(UTC)
            self.session.add(task)
            await self.session.flush()
            # 检查通过 → 房态回归空净可售（FR-FT-04）
            row = await self.session.execute(
                select(Room).where(
                    Room.tenant_id == task.tenant_id, Room.room_no == task.room_no
                )
            )
            room = row.scalar_one_or_none()
            if room:
                try:
                    await RoomService(self.session).transition(
                        room, RoomTrigger.CLEAN_DONE, operator=operator
                    )
                except Exception:  # noqa: BLE001 — 已净房则忽略
                    pass
            await self.session.flush()
        else:
            # 返工：退回已派单状态，原 assignee 继续处理
            task.status = "ASSIGNED"
            if note:
                task.note = f"检查退回：{note}"[:256]
            self.session.add(task)
            await self.session.flush()
        return task

    async def list_tasks(
        self,
        tenant_id: str,
        hotel_id: int | None = None,
        status: str | None = None,
        task_type: str | None = None,
        assignee: str | None = None,
        floor: str | None = None,
        limit: int = 5000,
        offset: int = 0,
    ) -> list[HousekeepingTask]:
        stmt = select(HousekeepingTask).where(HousekeepingTask.tenant_id == tenant_id)
        if hotel_id is not None:
            stmt = stmt.where(HousekeepingTask.hotel_id == hotel_id)
        if status:
            stmt = stmt.where(HousekeepingTask.status == status)
        if task_type:
            stmt = stmt.where(HousekeepingTask.task_type == task_type)
        if assignee:
            stmt = stmt.where(HousekeepingTask.assignee == assignee)
        if floor:
            # 按楼层过滤：经房间表匹配该层房号（M26 清单 #26 多维过滤）
            room_rows = await self.session.execute(
                select(Room.room_no).where(
                    Room.tenant_id == tenant_id, Room.floor == str(floor)
                )
            )
            room_nos = [r[0] for r in room_rows.all()]
            if not room_nos:
                return []
            stmt = stmt.where(HousekeepingTask.room_no.in_(room_nos))
        # M30 性能护栏：硬上限 limit + offset，避免高频轮询端点一次打满内存
        stmt = stmt.order_by(HousekeepingTask.id.desc()).limit(limit).offset(offset)
        rows = await self.session.execute(stmt)
        return list(rows.scalars())

    # ---- M26 客房深度：批量操作 + 员工绩效 ----

    async def batch_assign(
        self, tenant_id: str, task_ids: list[int], assignee: str
    ) -> dict:
        """批量派单：逐单尝试，跳过已结束工单并记录失败原因。"""
        assigned, failed = [], []
        for tid in task_ids:
            task = await self.session.get(HousekeepingTask, tid)
            if not task or task.tenant_id != tenant_id:
                failed.append({"task_id": tid, "reason": "工单不存在"})
                continue
            try:
                await self.assign(task, assignee)
                assigned.append(tid)
            except ValueError as exc:
                failed.append({"task_id": tid, "reason": str(exc)})
        return {"assigned": assigned, "failed": failed, "assignee": assignee}

    async def batch_done(self, tenant_id: str, task_ids: list[int], operator: str = "front_desk") -> dict:
        """批量完成：清扫单逐单联动空脏→空净。"""
        done, failed = [], []
        for tid in task_ids:
            task = await self.session.get(HousekeepingTask, tid)
            if not task or task.tenant_id != tenant_id:
                failed.append({"task_id": tid, "reason": "工单不存在"})
                continue
            try:
                await self.done(task, operator)
                done.append(tid)
            except ValueError as exc:
                failed.append({"task_id": tid, "reason": str(exc)})
        return {"done": done, "failed": failed}

    async def staff_performance(
        self,
        tenant_id: str,
        hotel_id: int,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict:
        """员工清扫绩效（M26，验收 #28）：完成单数 / 平均耗时（分钟）。"""
        stmt = select(HousekeepingTask).where(
            HousekeepingTask.tenant_id == tenant_id,
            HousekeepingTask.hotel_id == hotel_id,
            HousekeepingTask.status == "DONE",
            HousekeepingTask.done_at.isnot(None),
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        by_staff: dict[str, dict] = {}
        for t in rows:
            done_date = t.done_at.date().isoformat()
            if start_date and done_date < start_date:
                continue
            if end_date and done_date > end_date:
                continue
            key = t.assignee or "未指派"
            entry = by_staff.setdefault(
                key, {"assignee": key, "done_count": 0, "total_minutes": 0.0}
            )
            minutes = (t.done_at - t.created_at).total_seconds() / 60.0
            entry["done_count"] += 1
            entry["total_minutes"] += max(minutes, 0.0)
        staff = []
        for e in by_staff.values():
            staff.append({
                "assignee": e["assignee"],
                "done_count": e["done_count"],
                "avg_minutes": round(e["total_minutes"] / e["done_count"], 1),
            })
        staff.sort(key=lambda x: -x["done_count"])
        return {
            "hotel_id": hotel_id,
            "start_date": start_date,
            "end_date": end_date,
            "staff": staff,
            "total_done": sum(s["done_count"] for s in staff),
        }

    async def overdue_count(self, tenant_id: str, hotel_id: int) -> int:
        """超时未完成工单数（FR-FT-04 清扫超时提醒店长，默认阈值 2h 由 due_at 承载）。"""
        rows = await self.session.execute(
            select(HousekeepingTask).where(
                HousekeepingTask.tenant_id == tenant_id,
                HousekeepingTask.hotel_id == hotel_id,
                HousekeepingTask.status.in_(["PENDING", "ASSIGNED"]),
            )
        )
        now = datetime.now(UTC)
        n = 0
        for t in rows.scalars():
            due = _as_utc(t.due_at)
            if due is not None and due < now:
                n += 1
        return n
