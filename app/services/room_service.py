"""房态服务：状态机流转 + 领域事件发布 + 审计留痕（M1-1 核心链路）。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.room_state import InvalidTransition, RoomState, RoomTrigger, next_state
from app.events.base import RoomStateChanged, utc_now
from app.events.bus import event_bus
from app.models import (
    AuditLog,
    Booking,
    Complaint,
    HousekeepingTask,
    Room,
    RoomAttribute,
    RoomStateEvent,
)

# ---------- M37-④ 房间属性码表（维也纳 RoomAttribute / RoomDescript 合并命名空间） ----------
# 未知编码降级为编码本身，保证前端新增属性不至于写不进库。
ATTRIBUTE_NAMES: dict[str, str] = {
    "SMOKE_FREE": "无烟房",
    "BIG_BED": "大床",
    "TWIN_BED": "双床",
    "WINDOW": "有窗",
    "NO_WINDOW": "无窗",
    "HIGH_FLOOR": "高层",
    "LOW_FLOOR": "低层",
    "QUIET": "安静",
    "NEAR_ELEVATOR": "近电梯",
    "NEAR_STAIRS": "近楼梯",
    "ACCESSIBLE": "无障碍",
}


class RoomService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def transition(
        self,
        room: Room,
        trigger: RoomTrigger,
        operator: str = "system",
        auto_commit: bool = True,
    ) -> Room:
        """执行房态流转：状态机校验 → 落库 → 事件流水 → 审计 → 发布事件。"""
        current = RoomState(room.state)
        target = next_state(current, trigger)  # 非法流转抛 InvalidTransition

        # M32.3 通用锁房：解锁时恢复锁房前的房态（空净/空脏）——
        # 取最近一次 lock_for_arrival 事件记录的 from_state，无记录回退空净
        if trigger == RoomTrigger.RELEASE_ARRIVAL:
            stmt = (
                select(RoomStateEvent)
                .where(
                    RoomStateEvent.room_id == room.id,
                    RoomStateEvent.trigger == RoomTrigger.LOCK_FOR_ARRIVAL.value,
                )
                .order_by(RoomStateEvent.id.desc())
                .limit(1)
            )
            last_lock = (await self.session.execute(stmt)).scalar_one_or_none()
            if last_lock is not None and last_lock.from_state in (
                RoomState.VACANT_CLEAN.value,
                RoomState.VACANT_DIRTY.value,
            ):
                target = RoomState(last_lock.from_state)

        # M32.1 不变式：免打扰仅在住态有效——任何离开 occupied 的流转（退房/换房腾退等）
        # 统一在状态机层清除 DND，覆盖预订退房、房态盘手动操作、团队结账等全部路径
        dnd_cleared = False
        if current == RoomState.OCCUPIED and getattr(room, "dnd", 0):
            room.dnd = 0
            dnd_cleared = True

        room.state = target.value

        # 事件流水（事件溯源底账）
        self.session.add(
            RoomStateEvent(
                tenant_id=room.tenant_id,
                room_id=room.id,
                room_no=room.room_no,
                from_state=current.value,
                to_state=target.value,
                trigger=trigger.value,
                operator=operator,
                occurred_at=utc_now().isoformat(),
            )
        )
        # 审计留痕（DEC-04 基线：人/时间/改前改后）
        self.session.add(
            AuditLog(
                tenant_id=room.tenant_id,
                actor=operator,
                action=f"room.{trigger.value}",
                resource_type="room",
                resource_id=room.room_no,
                detail={"from_state": current.value, "to_state": target.value, **({"dnd_cleared": True} if dnd_cleared else {})},
            )
        )
        if auto_commit:
            await self.session.commit()
            await self.session.refresh(room)

        # Sprint 15：房态写路径显式失效热点读缓存（列表 TTL 30s 仅作兜底）
        try:
            from app.infra.cache import get_cache  # noqa: PLC0415

            await get_cache().invalidate_prefix(f"rooms:{room.tenant_id}")
        except Exception:  # noqa: BLE001 缓存失效失败不影响业务
            pass

        # 发布领域事件（「房态事件可订阅」验收点）
        await event_bus.publish(
            RoomStateChanged(
                tenant_id=room.tenant_id,
                room_id=room.id,
                room_no=room.room_no,
                from_state=current.value,
                to_state=target.value,
                trigger=trigger.value,
                operator=operator,
            )
        )
        return room

    async def get_room(self, tenant_id: str, room_no: str) -> Room | None:
        stmt = select(Room).where(Room.tenant_id == tenant_id, Room.room_no == room_no)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # ---- 智能排房推荐（M24，验收清单 #5） ----

    async def recommend_rooms(
        self,
        tenant_id: str,
        hotel_id: int,
        room_type_id: int | None = None,
        guest_phone: str | None = None,
        id_doc_no: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """按房态与客人历史偏好给出候选房排序。

        评分：空净 100 / 空脏 60（附「需先清扫」提示）；同房型 +30、
        历史偏好楼层 +20；排除在住/锁房/维修/停用。只读，不落审计。
        """
        r = await self.session.execute(
            select(Room).where(
                Room.tenant_id == tenant_id,
                Room.hotel_id == hotel_id,
                Room.state.in_(
                    [RoomState.VACANT_CLEAN.value, RoomState.VACANT_DIRTY.value]
                ),
            )
        )
        candidates = list(r.scalars())
        if room_type_id is not None:
            candidates = [c for c in candidates if c.room_type_id == room_type_id]

        # 历史偏好：该客人（手机号/证件号）过去实际住过的房型与楼层
        pref_type_ids: set[int] = set()
        pref_floors: set[str] = set()
        pref_room_nos: set[str] = set()
        if guest_phone or id_doc_no:
            conds = []
            if guest_phone:
                conds.append(Booking.guest_phone == guest_phone)
            if id_doc_no:
                conds.append(Booking.id_doc_no == id_doc_no)
            hr = await self.session.execute(
                select(Booking.room_no)
                .where(
                    Booking.tenant_id == tenant_id,
                    Booking.room_no.isnot(None),
                    *conds,
                )
                .order_by(Booking.id.desc())
                .limit(20)
            )
            hist_room_nos = [row[0] for row in hr.all()]
            if hist_room_nos:
                hs = await self.session.execute(
                    select(Room).where(
                        Room.tenant_id == tenant_id,
                        Room.room_no.in_(hist_room_nos),
                    )
                )
                for h in hs.scalars():
                    pref_type_ids.add(h.room_type_id)
                    pref_room_nos.add(h.room_no)
                    if h.floor:
                        pref_floors.add(str(h.floor))

        # M32：维修记录维度 —— 近 30 天有维修工单的房降权（复发风险）
        recent = datetime.now(UTC) - timedelta(days=30)
        maint_room_nos: set[str] = set()
        mr = await self.session.execute(
            select(HousekeepingTask.room_no)
            .where(
                HousekeepingTask.tenant_id == tenant_id,
                HousekeepingTask.task_type == "MAINTENANCE",
                HousekeepingTask.status.in_(["PENDING", "ASSIGNED", "DONE"]),
                HousekeepingTask.created_at >= recent,
                HousekeepingTask.room_no.in_([c.room_no for c in candidates] or [""]),
            )
            .distinct()
        )
        maint_room_nos = {row[0] for row in mr.all()}

        # M32：噪音投诉维度 —— 近 30 天 NOISE 投诉关联房间降权
        noise_room_nos: set[str] = set()
        nr = await self.session.execute(
            select(Complaint.room_no)
            .where(
                Complaint.tenant_id == tenant_id,
                Complaint.category == "NOISE",
                Complaint.created_at >= recent,
                Complaint.room_no.isnot(None),
                Complaint.room_no.in_([c.room_no for c in candidates] or [""]),
            )
            .distinct()
        )
        noise_room_nos = {row[0] for row in nr.all()}

        scored: list[dict] = []
        for room in candidates:
            score = 100 if room.state == RoomState.VACANT_CLEAN.value else 60
            reasons: list[str] = []
            if room.state == RoomState.VACANT_CLEAN.value:
                reasons.append("空净可即刻入住")
            else:
                reasons.append("需先完成清扫")
            if room.room_no in pref_room_nos:
                score += 50
                reasons.append("客人曾住过该房")
            if room.floor and str(room.floor) in pref_floors:
                score += 30
                reasons.append("与客人历史楼层一致")
            if room.room_type_id in pref_type_ids and len(
                {c.room_type_id for c in candidates}
            ) > 1:
                # 同房型是弱信号（单房型酒店全员命中），仅在多房型时加分
                score += 10
                reasons.append("与客人历史房型一致")
            if room.room_no in maint_room_nos:
                score -= 40
                reasons.append("近 30 天有维修记录（复发风险）")
            if room.room_no in noise_room_nos:
                score -= 30
                reasons.append("近 30 天有噪音投诉")
            scored.append(
                {
                    "room_id": room.id,
                    "room_no": room.room_no,
                    "floor": room.floor,
                    "room_type_id": room.room_type_id,
                    "state": room.state,
                    "score": score,
                    "reasons": reasons,
                }
            )
        scored.sort(key=lambda x: (-x["score"], x["room_no"]))
        return scored[:max(limit, 1)]

    # ---- 房间属性（M37-④）：全量覆盖写 + 排房过滤读 ----

    async def set_room_attributes(
        self,
        tenant_id: str,
        hotel_id: int,
        room_id: int,
        codes: list[str],
        memo: str | None = None,
        operator: str = "front_desk",
    ) -> list[RoomAttribute]:
        """幂等全量覆盖：先软删现有属性，再按 ``codes`` 重建。

        因 ``UQ(tenant_id, room_id, attribute_code)``，同编码不可重复插行——
        故已存在（含历史软删）的行改为**复活**（置 ``is_valid=True``）并刷新备注，
        其余行置 ``is_valid=False``，实现「一次 PUT 就是最终态」。
        """
        room = await self.session.get(Room, room_id)
        if room is None or room.tenant_id != tenant_id:
            raise ValueError("房间不存在")
        room_no = room.room_no

        existing = (
            await self.session.execute(
                select(RoomAttribute).where(
                    RoomAttribute.tenant_id == tenant_id,
                    RoomAttribute.room_id == room_id,
                )
            )
        ).scalars().all()
        by_code = {row.attribute_code: row for row in existing}

        wanted: list[str] = []
        for code in codes or []:
            code = (code or "").strip()  # noqa: PLW2901 - 归一化入参
            if code and code not in wanted:
                wanted.append(code)

        result: list[RoomAttribute] = []
        for row in existing:
            if row.attribute_code not in wanted and row.is_valid:
                row.is_valid = False
                row.operator = operator
                self.session.add(row)
        for code in wanted:
            row = by_code.get(code)
            if row is None:
                row = RoomAttribute(
                    tenant_id=tenant_id,
                    hotel_id=hotel_id or room.hotel_id,
                    room_id=room_id,
                    room_no=room_no,
                    attribute_code=code,
                    attribute_name=ATTRIBUTE_NAMES.get(code, code),
                    is_valid=True,
                    operator=operator,
                    memo=memo,
                )
            else:
                row.is_valid = True
                row.room_no = room_no
                row.attribute_name = ATTRIBUTE_NAMES.get(code, code)
                row.operator = operator
                row.memo = memo
            self.session.add(row)
            result.append(row)
        await self.session.flush()
        return result

    async def list_room_attributes(self, tenant_id: str, room_id: int) -> list[RoomAttribute]:
        """某房间的生效属性（软删的不返回）。"""
        result = await self.session.execute(
            select(RoomAttribute)
            .where(
                RoomAttribute.tenant_id == tenant_id,
                RoomAttribute.room_id == room_id,
                RoomAttribute.is_valid.is_(True),
            )
            .order_by(RoomAttribute.id.asc())
        )
        return list(result.scalars())

    async def list_rooms_by_attributes(self, tenant_id: str, codes: list[str]) -> list[str]:
        """排房过滤：返回**同时具备**全部 ``codes`` 的房号（去重，升序）。

        ``codes`` 为空时返回空列表（不放大成全量房，避免前端误当「不限」）。
        """
        wanted = [c for c in (codes or []) if c]
        if not wanted:
            return []
        stmt = (
            select(RoomAttribute.room_no)
            .where(
                RoomAttribute.tenant_id == tenant_id,
                RoomAttribute.is_valid.is_(True),
                RoomAttribute.attribute_code.in_(wanted),
            )
            .group_by(RoomAttribute.room_no)
            .having(func.count(distinct(RoomAttribute.attribute_code)) == len(wanted))
            .order_by(RoomAttribute.room_no.asc())
        )
        result = await self.session.execute(stmt)
        return [row[0] for row in result.all()]


__all__ = ["ATTRIBUTE_NAMES", "InvalidTransition", "RoomService"]
