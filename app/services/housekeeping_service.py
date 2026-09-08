"""清扫工单服务（M10-3，FR-APP-03 / FR-FT-04）：退房自动建单 → 派单 → 完成联动净房。"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.room_state import RoomTrigger
from app.events.base import HousekeepingDone
from app.events.bus import event_bus
from app.models import HousekeepingTask, Room
from app.services.notification_service import NotificationService
from app.services.room_service import RoomService

logger = logging.getLogger(__name__)

TASK_TYPES = ("CLEANUP", "MAINTENANCE", "INSPECT")

# M32 staff_performance 聚合护栏：单店聚合上限。极端大数据集下应拆分多次聚合，
# 当 done_count 越界时打 warning 提示管理员数据未完全覆盖（避免聚合耗时失控）。
STAFF_PERF_AGG_LIMIT = 5000


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _start_dt(d: str | None) -> datetime | None:
    """YYYY-MM-DD → UTC 00:00:00 含当天起。"""
    if not d:
        return None
    return datetime.combine(date.fromisoformat(d), time.min, tzinfo=UTC)


def _end_dt(d: str | None) -> datetime | None:
    """YYYY-MM-DD → UTC 次日 00:00:00（exclusive，含 end 当天全天）。"""
    if not d:
        return None
    end_day = date.fromisoformat(d) + timedelta(days=1)
    return datetime.combine(end_day, time.min, tzinfo=UTC)


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
        """员工清扫绩效（M26，验收 #28）：完成单数 / 平均耗时（分钟）。

        M32 SQL 下推优化：
            - 原版拉全部 DONE 工单后 Python 端按 ``start_date/end_date`` 过滤再按
              staff 聚合；高基数据下内存峰值与全表扫描都成问题。
            - 现版把日期范围、状态、tenant/hotel 全部下推到 SQL（含
              ``done_at BETWEEN``），并加 ``LIMIT 5000`` 防止极端数据集拖慢聚合；
              若真实完成数 > 5000，warning 日志提示管理员考虑分批或缩小日期窗口。
            - Python 端聚合逻辑（``by_staff: dict``）保留不变。
        """
        stmt = select(HousekeepingTask).where(
            HousekeepingTask.tenant_id == tenant_id,
            HousekeepingTask.hotel_id == hotel_id,
            HousekeepingTask.status == "DONE",
            HousekeepingTask.done_at.isnot(None),
        )
        start = _start_dt(start_date)
        end = _end_dt(end_date)
        if start is not None:
            stmt = stmt.where(HousekeepingTask.done_at >= start)
        if end is not None:
            stmt = stmt.where(HousekeepingTask.done_at < end)  # exclusive：含 end 当天全天
        stmt = stmt.order_by(HousekeepingTask.done_at.desc()).limit(STAFF_PERF_AGG_LIMIT)

        rows = (await self.session.execute(stmt)).scalars().all()
        if len(rows) >= STAFF_PERF_AGG_LIMIT:
            logger.warning(
                "housekeeping.staff_performance 聚合触达上限 %d 条，"
                "可能存在数据被截断；建议缩小日期窗口或按 assignee 分批查询。"
                " tenant=%s hotel=%s",
                STAFF_PERF_AGG_LIMIT,
                tenant_id,
                hotel_id,
            )

        by_staff: dict[str, dict] = {}
        for t in rows:
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
            "truncated": len(rows) >= STAFF_PERF_AGG_LIMIT,
        }

    async def overdue_count(self, tenant_id: str, hotel_id: int) -> int:
        """超时未完成工单数（FR-FT-04 清扫超时提醒店长，默认阈值 2h 由 due_at 承载）。

        M32 SQL 下推优化：直接 ``SELECT COUNT(*) WHERE status IN (...) AND
        due_at < now()``，避免拉全部 PENDING/ASSIGNED 工单后 Python 端遍历判断。
        ``due_at`` 字段为 ``DateTime(timezone=True)``（UTC 存储），比较用
        ``datetime.now(UTC)`` 统一时区，避开已弃用的 ``datetime.utcnow()``。
        """
        result = await self.session.execute(
            select(func.count())
            .select_from(HousekeepingTask)
            .where(
                HousekeepingTask.tenant_id == tenant_id,
                HousekeepingTask.hotel_id == hotel_id,
                HousekeepingTask.status.in_(["PENDING", "ASSIGNED"]),
                HousekeepingTask.due_at.isnot(None),
                HousekeepingTask.due_at < datetime.now(UTC),
            )
        )
        return int(result.scalar() or 0)
