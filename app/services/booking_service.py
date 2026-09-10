"""预订引擎服务（M2）：创建/入住/退房/取消 + 房态联动 + 事件发布。

状态机：CREATED → CHECKED_IN → CHECKED_OUT ； CREATED → CANCELLED
- 创建：校验日期、逐晚校验房量可用性、按价格库存中心计算总价；可选预分配房号（锁房）。
- 入住：联动 RoomService 将具体房间转在住（房态 ARRIVAL_LOCKED/VACANT_CLEAN → OCCUPIED）。
- 退房：联动房态转空脏，订单置已离。
- 取消：释放预分配房（如锁房），订单置已取消。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.room_state import InvalidTransition, RoomState, RoomTrigger
from app.events.base import BookingStateChanged, utc_now
from app.events.bus import event_bus
from app.models import AuditLog, Bill, BillItem, Booking, BookingStatus, Hotel, RateCode, Room, RoomChange, RoomType, StayExtension
from app.services.cashier_service import CashierService
from app.services.guest_service import GuestService
from app.services.housekeeping_service import HousekeepingService
from app.services.price_service import PriceService
from app.services.psb_service import PsbService
from app.services.room_service import RoomService


def _nights(check_in: str, check_out: str) -> list[str]:
    """展开预订覆盖的每一晚日期（含入住日，不含离店日）。"""
    y1, m1, d1 = map(int, check_in.split("-"))
    y2, m2, d2 = map(int, check_out.split("-"))
    cur = date(y1, m1, d1)
    end = date(y2, m2, d2)
    out: list[str] = []
    while cur < end:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


class BookingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.price = PriceService(session)

    async def _invalidate_dashboard_cache(self, tenant_id: str) -> None:
        """M30：预订状态变化后失效店总 dashboard 热点缓存（TTL 兜底 30s）。"""
        try:
            from app.infra.cache import get_cache  # noqa: PLC0415

            await get_cache().invalidate_prefix(f"dashboard:{tenant_id}")
        except Exception:  # noqa: BLE001 - 缓存失效失败不阻断主流程
            pass

    async def create(
        self,
        tenant_id: str,
        hotel_id: int,
        room_type_id: int,
        guest_name: str,
        check_in_date: str,
        check_out_date: str,
        channel: str = "direct",
        rate_code_code: str | None = None,
        guest_phone: str | None = None,
        id_doc_no: str | None = None,
        room_no: str | None = None,
        chat_session_id: int | None = None,
        stay_type: str = "daily",
        hourly_hours: int | None = None,
        # 批次② 字段补全
        guest_source_type: str | None = None,
        member_no: str | None = None,
        member_type: str | None = None,
        is_vip: bool = False,
        is_secret: bool = False,
        is_quick_depart: bool = False,
        is_print_real_price: bool = True,
        is_add_point: bool = True,
        is_guarantee: bool = False,
        guarantee_hold_until: str | None = None,
        guarantor: str | None = None,
        sales_id: str | None = None,
        activity_code: str | None = None,
        upgrade_room_type_id: int | None = None,
        group_name: str | None = None,
        group_type: str | None = None,
        group_leader: str | None = None,
        group_tel: str | None = None,
        email: str | None = None,
        country: str | None = None,
        operator: str = "system",
    ) -> Booking:
        if stay_type not in ("daily", "hourly"):
            raise ValueError("stay_type 须为 daily|hourly")
        if stay_type == "hourly":
            # M24：时租允许同日入住退房，但须有正数时长
            if hourly_hours is None or hourly_hours <= 0:
                raise ValueError("时租房须提供正数 hourly_hours（小时）")
        elif check_out_date <= check_in_date:
            raise ValueError("离店日期必须晚于入住日期")

        # 房量可用性：批量校验（M30 B4，原逐晚 → 固定 2 次查询）
        # 时租同日入住退房 → nights 为空集，batch_availability 直接返回 {}，天然跳过
        nights = _nights(check_in_date, check_out_date)
        if nights:
            avail_map = await self.price.batch_availability(
                tenant_id, room_type_id, list(nights)
            )
            for nd in nights:
                a = avail_map[nd]
                if a["available"] <= 0:
                    raise ValueError(f"日期 {nd} 房量不足（可售 {a['available']}）")

        # 总价：批量按价格库存中心解析（含 RateCode 折扣）；M24 时租按小时计价
        if stay_type == "hourly":
            rt = await self.session.get(RoomType, room_type_id)
            if rt is None or rt.tenant_id != tenant_id:
                raise ValueError("房型不存在")
            hourly_rate = rt.hourly_rate or rt.base_price // 4  # 未配置时按日价 1/4 折算
            total = hourly_rate * int(hourly_hours or 0)
        else:
            price_map = await self.price.batch_resolve(
                room_type_id, list(nights), channel=channel, rate_code_code=rate_code_code
            )
            total = sum(price_map.values())

        booking = Booking(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            room_type_id=room_type_id,
            channel=channel,
            guest_name=guest_name,
            guest_phone=guest_phone,
            id_doc_no=id_doc_no,
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            room_no=room_no,
            chat_session_id=chat_session_id,
            status=BookingStatus.CREATED.value,
            total_price=total,
            stay_type=stay_type,
            hourly_hours=hourly_hours if stay_type == "hourly" else None,
            # 批次② 字段补全
            guest_source_type=guest_source_type or "WI",
            member_no=member_no,
            member_type=member_type,
            is_vip=is_vip,
            is_secret=is_secret,
            is_quick_depart=is_quick_depart,
            is_print_real_price=is_print_real_price,
            is_add_point=is_add_point,
            is_guarantee=is_guarantee,
            guarantee_hold_until=guarantee_hold_until,
            guarantor=guarantor,
            sales_id=sales_id,
            activity_code=activity_code,
            upgrade_room_type_id=upgrade_room_type_id,
            group_name=group_name,
            group_type=group_type,
            group_leader=group_leader,
            group_tel=group_tel,
            email=email,
            country=country,
        )
        self.session.add(booking)
        await self.session.flush()

        # 可选预分配房号 → 锁房（ARRIVAL_LOCKED）
        if room_no:
            room = await self._get_room(tenant_id, room_no)
            if room.room_type_id != room_type_id:
                raise ValueError("预分配房号房型与预订房型不一致")
            # M32.17：预锁失败（如在住/脏房）转业务错误，避免 500
            rs = RoomService(self.session)
            try:
                await rs.transition(room, RoomTrigger.LOCK_FOR_ARRIVAL, operator=operator)
            except InvalidTransition as exc:
                raise ValueError(f"房间 {room_no} 当前状态 {room.state} 不可预锁（可能已有在住单）") from exc

        await self.session.commit()
        await self.session.refresh(booking)
        await self._invalidate_dashboard_cache(tenant_id)

        await event_bus.publish(
            BookingStateChanged(
                tenant_id=tenant_id,
                booking_id=booking.id,
                room_type_id=room_type_id,
                from_status="-",
                to_status=BookingStatus.CREATED.value,
                channel=channel,
            )
        )
        await self._warn_blacklist(booking, operator)
        return booking

    async def _warn_blacklist(self, booking: Booking, operator: str) -> None:
        """黑名单命中提醒（M37-④ D1：**仅提醒，不硬阻断**）。

        命中即写一条 ``guest.blacklist_warning`` 审计（WORM 留痕），由前台/经理在前台
        提示中自行判断；任何异常都吞掉，绝不影响建单主流程。
        """
        try:
            hits = await GuestService(self.session).check_blacklist(
                booking.tenant_id,
                name=booking.guest_name,
                id_no=booking.id_doc_no,
                phone=booking.guest_phone,
                hotel_id=booking.hotel_id,
            )
            if not hits:
                return
            from app.services.audit_service import record as _audit_record  # noqa: PLC0415

            await _audit_record(
                self.session,
                booking.tenant_id,
                "guest.blacklist_warning",
                actor=operator or "front_desk",
                resource_type="booking",
                resource_id=booking.id,
                hotel_id=booking.hotel_id,
                result="success",
                detail={"guest_name": booking.guest_name, "hits": hits},
            )
            await self.session.commit()
        except Exception:  # noqa: BLE001 - 提醒失败绝不阻断建单
            pass

    async def check_in(
        self, booking: Booking, room_no: str, operator: str = "front_desk"
    ) -> Booking:
        if booking.status != BookingStatus.CREATED.value:
            raise ValueError(f"仅 CREATED 状态可入住，当前 {booking.status}")
        # 业务规则：一间房同时只能有一笔在住单；其余订单只能取消/离店/NoShow/挂账，不可重复入住
        dup = (
            await self.session.execute(
                select(Booking).where(
                    Booking.tenant_id == booking.tenant_id,
                    Booking.status == BookingStatus.CHECKED_IN,
                    Booking.room_no == room_no,
                )
            )
        ).scalars().all()
        # 排除自身（理论上 CREATED 不会命中，防御式过滤）
        if any(b.id != booking.id for b in dup):
            names = "、".join(f"{b.room_no}({b.guest_name})" for b in dup if b.id != booking.id)
            raise ValueError(f"房间 {room_no} 已有在住单（{names}），不可重复入住")
        room = await self._get_room(booking.tenant_id, room_no)
        if room.room_type_id != booking.room_type_id:
            raise ValueError("入住房号房型与预订房型不一致")
        rs = RoomService(self.session)
        await rs.transition(room, RoomTrigger.CHECK_IN, operator=operator)
        await self._change_status(booking, BookingStatus.CHECKED_IN, operator)
        booking.room_no = room_no
        if booking.stay_type == "hourly":
            # M32.17b：钟点房记录到店时刻（HH:MM），离店时刻=该时刻+hourly_hours
            booking.hourly_start_time = datetime.now().strftime("%H:%M")
        # M3-5：入住即自动生成公安 PSB 住客登记上报任务
        psb = PsbService(self.session)
        await psb.enqueue_from_booking(booking)
        # M3-7 联动：入住即自动开账（该预订尚无在开账单时才创建，幂等）
        # 夜审房费过账（night_audit_service）依赖此 OPEN 账单存在
        existing = await self.session.execute(
            select(Bill).where(
                Bill.tenant_id == booking.tenant_id,
                Bill.booking_id == booking.id,
                Bill.status == "OPEN",
            )
        )
        if existing.scalar_one_or_none() is None:
            cashier = CashierService(self.session)
            await cashier.open_bill(
                tenant_id=booking.tenant_id,
                hotel_id=booking.hotel_id,
                guest_name=booking.guest_name,
                room_no=room_no,
                booking_id=booking.id,
                source="BOOKING",
            )
        # M14（FR-GUEST）：入住即累计客史（散客/会员统一档案），异常安全不阻断入住主流程
        try:
            gs = GuestService(self.session)
            await gs.record_stay(
                booking.tenant_id,
                booking.hotel_id,
                booking.guest_name,
                booking.guest_phone,
                amount_cents=booking.total_price or 0,
            )
        except Exception:  # noqa: BLE001 - 客史写入失败不应影响入住
            pass
        await self.session.commit()
        await self.session.refresh(booking)
        await self._invalidate_dashboard_cache(booking.tenant_id)
        return booking

    async def check_out(self, booking: Booking, operator: str = "front_desk") -> Booking:
        if booking.status != BookingStatus.CHECKED_IN.value or not booking.room_no:
            raise ValueError("仅 CHECKED_IN 且有房号可退房")
        room = await self._get_room(booking.tenant_id, booking.room_no)
        rs = RoomService(self.session)
        await rs.transition(room, RoomTrigger.CHECK_OUT, operator=operator)
        # DND 清除已在房态状态机层统一处理（离开 occupied 即清除）
        await self._change_status(booking, BookingStatus.CHECKED_OUT, operator)
        # M10-3（FR-APP-03/FR-FT-04）：退房自动派清扫工单
        hk = HousekeepingService(self.session)
        await hk.create_from_checkout(
            booking.tenant_id, booking.hotel_id, room.room_no, operator=operator
        )
        await self.session.commit()
        await self.session.refresh(booking)
        await self._invalidate_dashboard_cache(booking.tenant_id)
        return booking

    async def extend_stay(
        self, booking: Booking, new_check_out_date: str, operator: str = "front_desk"
    ) -> Booking:
        """续住（延住）：在住房间延长离店日期，按增量晚重算房量与房费（绿云在住操作台-续住）。"""
        if booking.status != BookingStatus.CHECKED_IN.value:
            raise ValueError(f"仅 CHECKED_IN 状态可续住，当前 {booking.status}")
        if new_check_out_date <= booking.check_out_date:
            raise ValueError("续住离店日期必须晚于当前离店日期")
        added_nights = _nights(booking.check_out_date, new_check_out_date)
        # 批量校验房量（M30 B4：原逐晚 → 固定 2 次查询）
        if added_nights:
            avail_map = await self.price.batch_availability(
                booking.tenant_id, booking.room_type_id, list(added_nights)
            )
            for nd in added_nights:
                a = avail_map[nd]
                if a["available"] <= 0:
                    raise ValueError(f"日期 {nd} 房量不足（可售 {a['available']}）")
        # 批量解析房价（M30 B4：原逐晚 → 固定 3 次查询；added_nights 空则 sum({})=0）
        price_map = await self.price.batch_resolve(
            booking.room_type_id, list(added_nights), channel=booking.channel
        )
        added_total = sum(price_map.values())
        old_check_out = booking.check_out_date
        booking.check_out_date = new_check_out_date
        booking.total_price = (booking.total_price or 0) + added_total
        self.session.add(
            AuditLog(
                tenant_id=booking.tenant_id,
                actor=operator,
                action="booking.extend_stay",
                resource_type="booking",
                resource_id=str(booking.id),
                detail={
                    "from": old_check_out,
                    "to": new_check_out_date,
                    "added_nights": len(added_nights),
                },
            )
        )
        # M37-③：落续住 WORM 记录 + 加收房费入账（若存在 OPEN 账单）
        open_bill = (
            await self.session.execute(
                select(Bill).where(
                    Bill.tenant_id == booking.tenant_id,
                    Bill.booking_id == booking.id,
                    Bill.status == "OPEN",
                )
            )
        ).scalar_one_or_none()
        if added_total > 0:
            se = StayExtension(
                tenant_id=booking.tenant_id,
                hotel_id=booking.hotel_id,
                booking_id=booking.id,
                room_no=booking.room_no,
                bill_id=open_bill.id if open_bill is not None else None,
                business_date=date.today().isoformat(),
                start_date=old_check_out,
                end_date=new_check_out_date,
                nights=len(added_nights),
                added_amount_cents=added_total,
                is_valid=True,
                operator=operator,
            )
            self.session.add(se)
            if open_bill is not None:
                open_bill.balance = (open_bill.balance or 0) + added_total
                self.session.add(open_bill)
                self.session.add(
                    BillItem(
                        tenant_id=booking.tenant_id,
                        bill_id=open_bill.id,
                        type="ROOM_CHARGE",
                        amount=added_total,
                        description=f"续住加收 {len(added_nights)} 晚",
                        business_date=se.business_date,
                        created_by=operator,
                    )
                )
        await self.session.commit()
        await self.session.refresh(booking)
        await event_bus.publish(
            BookingStateChanged(
                tenant_id=booking.tenant_id,
                booking_id=booking.id,
                room_type_id=booking.room_type_id,
                from_status=BookingStatus.CHECKED_IN.value,
                to_status=BookingStatus.CHECKED_IN.value,
                channel=booking.channel,
            )
        )
        return booking

    async def change_room(
        self,
        booking: Booking,
        new_room_no: str,
        operator: str = "front_desk",
        reason: str = "",
    ) -> Booking:
        """换房：在住房客从原房换至同房型空净房，原房转空脏待清扫（绿云在住操作台-换房）。

        M37-③ 增：必传 ``reason``（审计刚需）；落 ``RoomChange`` WORM 记录；
        若有房价差价（to_price - from_price > 0）则写 ``BillItem(ROOM_CHARGE, +diff)``。
        """
        if booking.status != BookingStatus.CHECKED_IN.value or not booking.room_no:
            raise ValueError("仅 CHECKED_IN 且有房号可换房")
        if not reason or not reason.strip():
            raise ValueError("换房原因 reason 必填")
        if new_room_no == booking.room_no:
            raise ValueError("换房目标房号不能与原房相同")
        old_room = await self._get_room(booking.tenant_id, booking.room_no)
        new_room = await self._get_room(booking.tenant_id, new_room_no)
        if RoomState(new_room.state) != RoomState.VACANT_CLEAN:
            raise ValueError("目标房须为空净（vacant_clean）方可换入")
        if new_room.room_type_id != booking.room_type_id:
            raise ValueError("换房目标房房型须与原预订房型一致")
        rs = RoomService(self.session)
        # 新房入住（空净→在住，发布 RoomStateChanged 即时刷新房态图）
        await rs.transition(new_room, RoomTrigger.CHECK_IN, operator=operator)
        # 原房腾退（在住→空脏，订单仍 CHECKED_IN）
        await rs.transition(old_room, RoomTrigger.ROOM_SWAP, operator=operator)
        # DND 清除已在房态状态机层统一处理
        old_room_no = booking.room_no
        booking.room_no = new_room_no
        # 同步在开账单房号（收银台定位一致）
        open_bill = await self.session.execute(
            select(Bill).where(
                Bill.tenant_id == booking.tenant_id,
                Bill.booking_id == booking.id,
                Bill.status == "OPEN",
            )
        )
        bill = open_bill.scalar_one_or_none()
        if bill is not None:
            bill.room_no = new_room_no
            self.session.add(bill)
        self.session.add(
            AuditLog(
                tenant_id=booking.tenant_id,
                actor=operator,
                action="booking.change_room",
                resource_type="booking",
                resource_id=str(booking.id),
                detail={"from": old_room_no, "to": new_room_no, "reason": reason},
            )
        )
        # M37-③：落换房 WORM 记录 + 差价入账（price_diff > 0 时）
        from app.core.snowflake import next_id  # noqa: PLC0415

        # Room 无 room_type 关系；用 booking.room_type_id 反查（既有换房校验已保证
        # old/new 同房型，故 from_price == to_price，diff 通常为 0；保留字段为未来跨型升级预留）
        rt = await self.session.get(RoomType, booking.room_type_id)
        rt_price = rt.base_price if rt else None
        rc = RoomChange(
            tenant_id=booking.tenant_id,
            hotel_id=booking.hotel_id,
            change_no=f"RC{next_id()}",
            booking_id=booking.id,
            bill_id=bill.id if bill is not None else None,
            from_room_no=old_room_no,
            to_room_no=new_room_no,
            from_room_type_id=old_room.room_type_id,
            to_room_type_id=new_room.room_type_id,
            from_price_cents=rt_price,
            to_price_cents=rt_price,
            price_diff_cents=0,
            reason=reason,
            business_date=date.today().isoformat(),
            operator=operator,
        )
        self.session.add(rc)
        if rc.price_diff_cents > 0 and bill is not None:
            bill.balance = (bill.balance or 0) + rc.price_diff_cents
            self.session.add(
                BillItem(
                    tenant_id=booking.tenant_id,
                    bill_id=bill.id,
                    type="ROOM_CHARGE",
                    amount=rc.price_diff_cents,
                    description=f"换房差价 {old_room_no}→{new_room_no}",
                    business_date=rc.business_date,
                    created_by=operator,
                )
            )
            self.session.add(bill)
        await self.session.commit()
        await self.session.refresh(booking)
        await event_bus.publish(
            BookingStateChanged(
                tenant_id=booking.tenant_id,
                booking_id=booking.id,
                room_type_id=booking.room_type_id,
                from_status=BookingStatus.CHECKED_IN.value,
                to_status=BookingStatus.CHECKED_IN.value,
                channel=booking.channel,
            )
        )
        return booking

    async def update_stay_extras(
        self,
        booking: Booking,
        extra_bed_count: int | None = None,
        companion_names: list[str] | None = None,
        operator: str = "front_desk",
    ) -> Booking:
        """在住附加服务（绿云-加床 / 同住人）：仅 CREATED/CHECKED_IN 可维护。"""
        if booking.status not in (
            BookingStatus.CREATED.value,
            BookingStatus.CHECKED_IN.value,
        ):
            raise ValueError(f"仅 CREATED/CHECKED_IN 可维护附加服务，当前 {booking.status}")
        if extra_bed_count is not None:
            if extra_bed_count < 0:
                raise ValueError("加床数不能为负")
            booking.extra_bed_count = extra_bed_count
        if companion_names is not None:
            booking.set_companions(companion_names)
        self.session.add(booking)
        self.session.add(
            AuditLog(
                tenant_id=booking.tenant_id,
                actor=operator,
                action="booking.update_stay_extras",
                resource_type="booking",
                resource_id=str(booking.id),
                detail={
                    "extra_bed_count": booking.extra_bed_count,
                    "companion_count": len(booking.companion_list),
                },
            )
        )
        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    async def cancel(self, booking: Booking, operator: str = "front_desk") -> Booking:
        if booking.status != BookingStatus.CREATED.value:
            raise ValueError(f"仅 CREATED 状态可取消，当前 {booking.status}")
        # 释放预分配房
        if booking.room_no:
            room = await self._get_room(booking.tenant_id, booking.room_no)
            if RoomState(room.state) == RoomState.ARRIVAL_LOCKED:
                rs = RoomService(self.session)
                await rs.transition(room, RoomTrigger.RELEASE_ARRIVAL, operator=operator)
        await self._change_status(booking, BookingStatus.CANCELLED, operator)
        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    async def mark_noshow(
        self, booking: Booking, reason: str | None = None, operator: str = "front_desk"
    ) -> Booking:
        """前台手动标记 NoShow（验收清单#3）：仅 CREATED（应到未到）可标记。

        与取消的区别：NoShow 保留预订事实与原因留痕（用于客史/渠道考核），
        同样释放预分配锁房。
        """
        if booking.status != BookingStatus.CREATED.value:
            raise ValueError(f"仅 CREATED 状态可标记 NoShow，当前 {booking.status}")
        booking.noshow_reason = reason or f"前台手动标记 NoShow（操作人 {operator}）"
        # 释放预分配房
        if booking.room_no:
            room = await self._get_room(booking.tenant_id, booking.room_no)
            if RoomState(room.state) == RoomState.ARRIVAL_LOCKED:
                rs = RoomService(self.session)
                await rs.transition(room, RoomTrigger.RELEASE_ARRIVAL, operator=operator)
        await self._change_status(booking, BookingStatus.NOSHOW, operator)
        await self.session.commit()
        await self.session.refresh(booking)
        return booking

    # ---- 内部辅助 ----
    async def _get_room(self, tenant_id: str, room_no: str) -> Room:
        room = await self.session.execute(
            select(Room).where(Room.tenant_id == tenant_id, Room.room_no == room_no)
        )
        r = room.scalar_one_or_none()
        if not r:
            raise ValueError("房间不存在")
        return r

    async def _change_status(
        self, booking: Booking, to: BookingStatus, operator: str
    ) -> None:
        from_status = booking.status
        booking.status = to.value
        self.session.add(
            AuditLog(
                tenant_id=booking.tenant_id,
                actor=operator,
                action=f"booking.{to.value}",
                resource_type="booking",
                resource_id=str(booking.id),
                detail={"from_status": from_status, "to_status": to.value},
            )
        )
        await self.session.commit()
        await event_bus.publish(
            BookingStateChanged(
                tenant_id=booking.tenant_id,
                booking_id=booking.id,
                room_type_id=booking.room_type_id,
                from_status=from_status,
                to_status=to.value,
                channel=booking.channel,
            )
        )
