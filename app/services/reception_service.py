"""统一接待办理服务（M14-3，FR-RECEPTION）：绿云前台散客/预订双模式入住。

将「到店办理」从分散的建预订/建档/入住 API 收敛为一站式入口：
- 预订模式：确认预订 →（可选）前台证件登记 → 指定房号入住；
- 散客模式：自动建档（关联会员）→ 建预订（锁房）→ 指定房号入住。

两类模式最终都走 ``BookingService.check_in``，从而复用其全部副作用：
房态转在住、公安 PSB 住客登记上报、自动开账、入住累计客史（客档联动会员）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.reception_flow import (
    ALLOWED_ACTIONS,
    InvalidReceptionTransition,
    ReceptionAction,
    ReceptionFlowState,
    can_advance,
    derive_flow_state,
)
from app.models import AuditLog, Bill, Booking, BookingStatus, Guest, Member, Room
from app.services.booking_service import BookingService
from app.services.cashier_service import CashierService
from app.services.guest_service import GuestService
from app.services.member_service import MemberService


class ReceptionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def unified_check_in(
        self,
        tenant_id: str,
        hotel_id: int,
        operator: str,
        *,
        booking_id: int | None = None,
        room_no: str,
        room_type_id: int | None = None,
        guest_name: str | None = None,
        guest_phone: str | None = None,
        id_type: str | None = None,
        id_no: str | None = None,
        check_in_date: str | None = None,
        check_out_date: str | None = None,
        stay_type: str = "daily",
        hourly_hours: int | None = None,
        gender: str | None = None,
        birthday: str | None = None,
        email: str | None = None,
        address: str | None = None,
        nationality: str | None = None,
        ethnicity: str | None = None,
        note: str | None = None,
        # 批次② 核心实体字段补全：登记页 6 个 checkbox + 客源/会员号/担保
        guest_source_type: str | None = None,
        member_no: str | None = None,
        is_vip: bool = False,
        is_secret: bool = False,
        is_quick_depart: bool = False,
        is_print_real_price: bool = True,
        is_add_point: bool = True,
        is_guarantee: bool = False,
        guarantee_hold_until: str | None = None,
    ) -> Booking:
        bs = BookingService(self.session)
        gs = GuestService(self.session)

        if booking_id is not None:
            # ---- 预订模式 ----
            booking = await self.session.get(Booking, booking_id)
            if booking is None or booking.tenant_id != tenant_id:
                raise ValueError("预订不存在")
            if booking.status != BookingStatus.CREATED.value:
                raise ValueError(f"仅 CREATED 预订可办理入住，当前 {booking.status}")
            # 前台证件登记：确保客档（含会员关联）+ 回写预订证件号
            if guest_phone:
                await gs.create(
                    tenant_id,
                    booking.hotel_id,
                    booking.guest_name,
                    guest_phone,
                    id_type=id_type,
                    id_no=id_no,
                    gender=gender,
                    birthday=birthday,
                    email=email,
                    address=address,
                    tags=[t for t in (f"国籍:{nationality}" if nationality else None, f"民族:{ethnicity}" if ethnicity else None) if t],
                    notes=note,
                )
                booking.guest_phone = guest_phone
            if id_no:
                booking.id_doc_no = id_no
                self.session.add(booking)
            # 批次②：登记页接线字段回写既有预订
            # guest_source_type 为 NOT NULL（默认 "WI"），页面未填时前端传 null，
            # 此时保留原值而非写入 null（否则触发 NOT NULL 约束）。
            if guest_source_type is not None:
                booking.guest_source_type = guest_source_type
            booking.member_no = member_no
            booking.is_vip = is_vip
            booking.is_secret = is_secret
            booking.is_quick_depart = is_quick_depart
            booking.is_print_real_price = is_print_real_price
            booking.is_add_point = is_add_point
            booking.is_guarantee = is_guarantee
            booking.guarantee_hold_until = guarantee_hold_until
            self.session.add(booking)
            await self.session.flush()
            checked = await bs.check_in(booking, room_no, operator=operator)
            # M37-④ D1：黑名单仅提醒不阻断（写入审计，前台提示层消费）
            await self._warn_blacklist(checked, operator)
            return checked

        # ---- 散客模式 ----
        if not (room_type_id and guest_name and check_in_date and check_out_date):
            raise ValueError("散客办理需提供 room_type_id / guest_name / check_in_date / check_out_date")
        # M32.17：钟点房——强制同日入住退房（不占过夜可售房量），须有正数时长
        if stay_type == "hourly":
            if hourly_hours is None or hourly_hours <= 0:
                raise ValueError("钟点房须提供正数时长 hourly_hours（小时）")
            check_out_date = check_in_date
        # 自动建档（同手机号不重复建档，命中会员自动关联 member_id）
        if guest_phone:
            await gs.create(
                tenant_id,
                hotel_id,
                guest_name,
                guest_phone,
                id_type=id_type,
                id_no=id_no,
                gender=gender,
                birthday=birthday,
                email=email,
                address=address,
                tags=[t for t in (f"国籍:{nationality}" if nationality else None, f"民族:{ethnicity}" if ethnicity else None) if t],
                notes=note,
            )
        # 建预订并预锁房（channel=walk_in），随后入住
        booking = await bs.create(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            room_type_id=room_type_id,
            guest_name=guest_name,
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            channel="walk_in",
            guest_phone=guest_phone,
            id_doc_no=id_no,
            room_no=room_no,
            operator=operator,
            stay_type=stay_type,
            hourly_hours=hourly_hours if stay_type == "hourly" else None,
            # 批次②：登记页接线字段
            guest_source_type=guest_source_type,
            member_no=member_no,
            is_vip=is_vip,
            is_secret=is_secret,
            is_quick_depart=is_quick_depart,
            is_print_real_price=is_print_real_price,
            is_add_point=is_add_point,
            is_guarantee=is_guarantee,
            guarantee_hold_until=guarantee_hold_until,
        )
        return await bs.check_in(booking, room_no, operator=operator)

    async def _warn_blacklist(self, booking: Booking, operator: str) -> None:
        """黑名单命中提醒（M37-④ D1：**仅提醒，不硬阻断**）。

        入住路径（预订模式）在建单期不会触发 ``BookingService.create``，故在此补一次；
        散客模式由 ``BookingService.create`` 内部已触发，重复调用无副作用（幂等审计）。
        任何异常都吞掉，绝不阻断入住主流程。
        """
        try:
            await BookingService(self.session)._warn_blacklist(booking, operator)  # noqa: SLF001
        except Exception:  # noqa: BLE001 - 提醒失败绝不阻断入住
            pass

    # ---------- R1 · 单客上下文只读聚合 ----------

    async def get_context(
        self,
        tenant_id: str,
        *,
        guest_phone: str | None = None,
        booking_id: int | None = None,
        room_no: str | None = None,
        hotel_id: int | None = None,  # 预留：未来按门店隔离客档检索
    ) -> dict:
        """R1 单客上下文（只读聚合，零写）：客档/会员/预订/房态/账单/审计。

        定位优先级：``booking_id`` → ``room_no``（在住房最新预订）→ ``guest_phone``（最新预订）。
        返回结构即 API ``ReceptionContext``；``flow_state`` 由域派生、``can_advance`` 为可继续动作。
        """
        booking = await self._resolve_booking(
            tenant_id, booking_id=booking_id, room_no=room_no, guest_phone=guest_phone
        )

        # 客档：显式手机号优先；否则从预订手机号反查（单客视图天然含客档）
        lookup_phone = guest_phone or (booking.guest_phone if booking else None)
        guest = None
        if lookup_phone:
            guest = await GuestService(self.session).get_by_phone(tenant_id, lookup_phone)

        # 会员（客档联动会员，FR-GUEST-LINK）— 可选聚合，降级保护
        membership = None
        degradation_notes: list[str] = []
        try:
            if guest and guest.member_id:
                member = await self.session.get(Member, guest.member_id)
                if member and member.tenant_id == tenant_id:
                    membership = {
                        "member_id": member.id,
                        "name": member.name,
                        "phone": member.phone,
                        "level": member.level,
                        "stored_value": member.stored_value,
                        "points": member.points,
                        "stays": member.stays,
                    }
        except Exception:  # noqa: BLE001 — Q4 断网降级：会员主数据暂不可用时降级，不阻断主流程
            membership = None
            degradation_notes.append("会员信息暂不可用")

        # 房态（取预订房号或显式房号）
        resolved_room_no = (booking.room_no if booking else None) or room_no
        room_state = await self._resolve_room_state(tenant_id, resolved_room_no)

        # 在开账单（folio）— 可选聚合，降级保护
        folio = None
        try:
            if booking:
                bill = (
                    await self.session.execute(
                        select(Bill).where(
                            Bill.tenant_id == tenant_id,
                            Bill.booking_id == booking.id,
                            Bill.status == "OPEN",
                        )
                    )
                ).scalar_one_or_none()
                if bill:
                    folio = {
                        "bill_id": bill.id,
                        "bill_no": bill.bill_no,
                        "status": bill.status,
                        "balance": bill.balance,
                        "item_count": len(bill.items),
                        "payment_count": len(bill.payments),
                    }
        except Exception:  # noqa: BLE001 — Q4 断网降级
            folio = None
            degradation_notes.append("账单信息暂不可用")

        # 审计（该预订最近 10 条）— 可选聚合，降级保护
        audit_log: list[dict] = []
        try:
            if booking:
                audit_log = await self._load_audit_log(tenant_id, booking)
        except Exception:  # noqa: BLE001 — Q4 断网降级
            audit_log = []
            degradation_notes.append("审计轨迹暂不可用")

        flow_state = derive_flow_state(
            booking_status=booking.status if booking else None,
        )
        guest_out = self._guest_out(guest) if guest else None
        if guest_out and membership:
            guest_out["member_level"] = membership["level"]
        insights = self._derive_insights(guest, membership)
        return {
            "flow_state": flow_state.value,
            "can_advance": can_advance(flow_state),
            "guest": guest_out,
            "membership": membership,
            "booking": self._booking_out(booking) if booking else None,
            "room_no": resolved_room_no,
            "room_state": room_state,
            "folio": folio,
            "audit_log": audit_log,
            "insights": insights,
            "degraded": bool(degradation_notes),
            "degradation_notes": degradation_notes,
        }

    # ---------- R2 · 编排层状态机驱动 ----------

    async def advance(
        self,
        tenant_id: str,
        action: str,
        *,
        guest_phone: str | None = None,
        booking_id: int | None = None,
        room_no: str | None = None,
        hotel_id: int | None = None,
        guest_name: str | None = None,
        room_type_id: int | None = None,
        id_type: str | None = None,
        id_no: str | None = None,
        check_in_date: str | None = None,
        check_out_date: str | None = None,
        operator: str = "front_desk",
    ) -> dict:
        """R2 编排层：依据当前办理流状态执行合法动作，回写各域并返回新上下文。

        动作（仅 4 个有副作用）：
        - ``register``    ：建档（GuestService.create，同手机号幂等）；
        - ``check_in``    ：排房 + 入住，复用 unified_check_in（预订/散客双模式）；
        - ``open_folio``  ：确认在开账单（幂等，无则开账）；
        - ``check_out``   ：退房，复用 BookingService.check_out。
        非法流转抛 ``InvalidReceptionTransition``；缺参抛 ValueError（API 转 409）。
        """
        current = await self.get_context(
            tenant_id,
            guest_phone=guest_phone,
            booking_id=booking_id,
            room_no=room_no,
        )
        state = ReceptionFlowState(current["flow_state"])
        try:
            act = ReceptionAction(action)
        except ValueError as exc:
            raise ValueError(f"未知办理流动作: {action}") from exc
        if act not in ALLOWED_ACTIONS.get(state, frozenset()):
            raise InvalidReceptionTransition(state, act)

        if act == ReceptionAction.REGISTER:
            if not (hotel_id and guest_name):
                raise ValueError("建档（register）需提供 hotel_id 与 guest_name")
            await GuestService(self.session).create(
                tenant_id,
                hotel_id,
                guest_name,
                guest_phone,
                id_type=id_type,
                id_no=id_no,
            )
        elif act == ReceptionAction.CHECK_IN:
            # 散客模式需由房号反查归属门店（与 reception_check_in 路由一致）
            effective_hotel_id = hotel_id
            if not effective_hotel_id:
                if booking_id is not None:
                    bk = await self.session.get(Booking, booking_id)
                    if bk and bk.tenant_id == tenant_id:
                        effective_hotel_id = bk.hotel_id
                if not effective_hotel_id and room_no:
                    room = (
                        await self.session.execute(
                            select(Room).where(
                                Room.tenant_id == tenant_id, Room.room_no == room_no
                            )
                        )
                    ).scalar_one_or_none()
                    if room:
                        effective_hotel_id = room.hotel_id
            if not effective_hotel_id:
                raise ValueError("入住（check_in）无法解析归属门店，请提供 hotel_id")
            await self.unified_check_in(
                tenant_id,
                effective_hotel_id,
                operator,
                booking_id=booking_id,
                room_no=room_no or "",
                room_type_id=room_type_id,
                guest_name=guest_name,
                guest_phone=guest_phone,
                id_type=id_type,
                id_no=id_no,
                check_in_date=check_in_date,
                check_out_date=check_out_date,
            )
        elif act == ReceptionAction.OPEN_FOLIO:
            bk = await self._resolve_booking(
                tenant_id, booking_id=booking_id, room_no=room_no, guest_phone=guest_phone
            )
            if bk is None:
                raise ValueError("无在住房预订，无法确认账单")
            existing = (
                await self.session.execute(
                    select(Bill).where(
                        Bill.tenant_id == tenant_id,
                        Bill.booking_id == bk.id,
                        Bill.status == "OPEN",
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                await CashierService(self.session).open_bill(
                    tenant_id=tenant_id,
                    hotel_id=bk.hotel_id,
                    guest_name=bk.guest_name,
                    room_no=bk.room_no,
                    booking_id=bk.id,
                    source="BOOKING",
                )
        elif act == ReceptionAction.CHECK_OUT:
            bk = await self._resolve_booking(
                tenant_id, booking_id=booking_id, room_no=room_no, guest_phone=guest_phone
            )
            if bk is None:
                raise ValueError("无预订可退房")
            await BookingService(self.session).check_out(bk, operator=operator)
        elif act == ReceptionAction.ENROLL_MEMBER:
            # ① 客档联动会员·深度联动：现场办会员并关联客档（幂等：同手机号命中既有会员直接关联）
            if not guest_phone:
                raise ValueError("办会员需提供 guest_phone")
            guest = await GuestService(self.session).get_by_phone(tenant_id, guest_phone)
            if guest is None:
                raise ValueError("请先建档（提供该手机号客档）后再办会员")
            # 解析归属门店：动作显式 > 在住预订 > 房号反查
            eff_hotel = hotel_id
            if not eff_hotel and booking:
                eff_hotel = booking.hotel_id
            if not eff_hotel and room_no:
                room = (
                    await self.session.execute(
                        select(Room).where(
                            Room.tenant_id == tenant_id, Room.room_no == room_no
                        )
                    )
                ).scalar_one_or_none()
                if room:
                    eff_hotel = room.hotel_id
            if not eff_hotel:
                raise ValueError("办会员需提供 hotel_id（归属门店）")
            member = await MemberService(self.session).register(
                tenant_id, eff_hotel, guest.name, guest.phone
            )
            if guest.member_id != member.id:
                guest.member_id = member.id
                self.session.add(guest)
            await self.session.flush()

        await self.session.flush()
        # 动作后重新定位上下文（booking_id/room_no/phone 可能变化）
        return await self.get_context(
            tenant_id,
            guest_phone=guest_phone,
            booking_id=booking_id,
            room_no=room_no,
        )

    # ---- 内部辅助 ----

    # ---- 在住联房（M32.15）----
    # 业务约定：联房 = 在住单之间建立账务关联（合并结算到主房场景）；
    # 各单保留自己的来离店日期/房价，联房不触碰任何入住信息，只写 link_group_id / is_link_master。

    async def link_rooms(
        self,
        tenant_id: str,
        room_nos: list[str],
        master_room_no: str,
        operator: str = "front_desk",
    ) -> list[Booking]:
        """把多间在住房联为一组；主房标记 master_room_no。

        规则：房号需存在对应的在住单（checked_in 且已分房）；至少两间；
        master 必须在 room_nos 内；重复联房视为换组（自动脱离旧组）。
        """
        unique_nos = list(dict.fromkeys(room_nos))
        if len(unique_nos) < 2:
            raise ValueError("联房至少需要两间在住房")
        if master_room_no not in unique_nos:
            raise ValueError("主房必须在联房房号列表内")

        bookings = await self._checked_in_by_rooms(tenant_id, unique_nos)
        if len(bookings) != len(unique_nos):
            missing = sorted(set(unique_nos) - {b.room_no for b in bookings})
            raise ValueError(f"以下房间没有在住单：{', '.join(missing)}")

        import uuid

        group_id = uuid.uuid4().hex[:16]
        for b in bookings:
            b.link_group_id = group_id
            b.is_link_master = b.room_no == master_room_no
        await self.session.flush()
        await self._audit_link(tenant_id, operator, unique_nos, master_room_no, group_id)
        return sorted(bookings, key=lambda b: b.room_no or "")

    async def unlink_rooms(self, tenant_id: str, room_nos: list[str], operator: str = "front_desk") -> list[Booking]:
        """把房号移出联房组；若移出的是主房，组内剩余房号字典序第一间自动接管主房。"""
        unique_nos = list(dict.fromkeys(room_nos))
        bookings = await self._checked_in_by_rooms(tenant_id, unique_nos)
        if len(bookings) != len(unique_nos):
            missing = sorted(set(unique_nos) - {b.room_no for b in bookings})
            raise ValueError(f"以下房间没有在住单：{', '.join(missing)}")

        group_ids = {b.link_group_id for b in bookings if b.link_group_id}
        if not group_ids:
            raise ValueError("所选房间没有联房关系")
        for b in bookings:
            b.link_group_id = None
            b.is_link_master = False
        # 主房移出后移交标记（仅处理本次未移出的同组成员）
        for gid in group_ids:
            rest = (
                await self.session.execute(
                    select(Booking).where(
                        Booking.tenant_id == tenant_id,
                        Booking.link_group_id == gid,
                        Booking.is_link_master.is_(True),
                    )
                )
            ).scalars().all()
            if not rest:
                remain = (
                    await self.session.execute(
                        select(Booking)
                        .where(Booking.tenant_id == tenant_id, Booking.link_group_id == gid)
                        .order_by(Booking.room_no)
                    )
                ).scalars().all()
                if remain:
                    remain[0].is_link_master = True
        await self.session.flush()
        await self._audit_link(tenant_id, operator, unique_nos, None, None, unlink=True)
        return sorted(bookings, key=lambda b: b.room_no or "")

    async def _checked_in_by_rooms(self, tenant_id: str, room_nos: list[str]) -> list[Booking]:
        result = await self.session.execute(
            select(Booking).where(
                Booking.tenant_id == tenant_id,
                Booking.status == BookingStatus.CHECKED_IN,
                Booking.room_no.in_(room_nos),
            )
        )
        return list(result.scalars())

    async def _audit_link(
        self,
        tenant_id: str,
        operator: str,
        room_nos: list[str],
        master_room_no: str | None,
        group_id: str | None,
        *,
        unlink: bool = False,
    ) -> None:
        action = "unlink_rooms" if unlink else "link_rooms"
        detail = (
            f"取消联房：{', '.join(room_nos)}" if unlink else f"联房：{', '.join(room_nos)}（主房 {master_room_no}）"
        )
        self.session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor=operator,
                action=action,
                resource_type="booking_link",
                resource_id=group_id,
                detail={"rooms": room_nos, "master": master_room_no},
            )
        )

    async def _resolve_booking(
        self,
        tenant_id: str,
        *,
        booking_id: int | None = None,
        room_no: str | None = None,
        guest_phone: str | None = None,
    ) -> Booking | None:
        booking = None
        if booking_id is not None:
            booking = await self.session.get(Booking, booking_id)
            if booking is None or booking.tenant_id != tenant_id:
                booking = None
        if booking is None and room_no:
            res = await self.session.execute(
                select(Booking)
                .where(Booking.tenant_id == tenant_id, Booking.room_no == room_no)
                .order_by(Booking.id.desc())
                .limit(1)
            )
            booking = res.scalar_one_or_none()
        if booking is None and guest_phone:
            res = await self.session.execute(
                select(Booking)
                .where(Booking.tenant_id == tenant_id, Booking.guest_phone == guest_phone)
                .order_by(Booking.id.desc())
                .limit(1)
            )
            booking = res.scalar_one_or_none()
        return booking

    async def _resolve_room_state(
        self, tenant_id: str, room_no: str | None
    ) -> str | None:
        if not room_no:
            return None
        room = (
            await self.session.execute(
                select(Room).where(
                    Room.tenant_id == tenant_id, Room.room_no == room_no
                )
            )
        ).scalar_one_or_none()
        return room.state if room else None

    async def _load_audit_log(self, tenant_id: str, booking: "Booking") -> list[dict]:
        """加载该预订最近 10 条审计（Q4 断网降级：由调用方包裹，失败仅降级不阻断）。"""
        res = await self.session.execute(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.resource_type == "booking",
                AuditLog.resource_id == str(booking.id),
            )
            .order_by(AuditLog.id.desc())
            .limit(10)
        )
        return [
            {
                "id": a.id,
                "action": a.action,
                "actor": a.actor,
                "resource_type": a.resource_type,
                "resource_id": a.resource_id,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in res.scalars().all()
        ]

    @staticmethod
    def _derive_insights(
        guest: "Guest | None", membership: dict | None
    ) -> list[str]:
        """R7 客史洞察：基于客档/会员派生前台可读提示（只读，无副作用）。"""
        out: list[str] = []
        if guest is None:
            return out
        if guest.stay_count and guest.stay_count >= 3:
            out.append(f"常客 · 第 {guest.stay_count} 次入住")
        if guest.vip_level and guest.vip_level != "NORMAL":
            out.append(f"VIP 等级：{guest.vip_level}")
        if membership:
            out.append(f"会员等级：{membership['level']}（储值 {membership['stored_value'] / 100:.2f} 元 / {membership['points']} 积分）")
        elif guest.member_id:
            out.append("已关联会员（CRM 主数据缺失）")
        if guest.total_spend and guest.total_spend >= 100000:  # 1000 元起
            out.append(f"高价值客户 · 累计消费 {guest.total_spend / 100:.2f} 元")
        for t in guest.tag_list or []:
            out.append(f"标签：{t}")
        if guest.notes:
            out.append(f"客史备注：{guest.notes}")
        return out

    @staticmethod
    def _guest_out(guest: "Guest") -> dict:
        return {
            "id": guest.id,
            "name": guest.name,
            "phone": guest.phone,
            "id_type": guest.id_type,
            "id_no": guest.id_no,
            "vip_level": guest.vip_level,
            "gender": guest.gender,
            "email": guest.email,
            "tags": guest.tag_list,
            "notes": guest.notes,
            "stay_count": guest.stay_count,
            "total_spend": guest.total_spend,
            "member_id": guest.member_id,
            "member_level": None,
        }

    @staticmethod
    def _booking_out(booking: "Booking") -> dict:
        return {
            "id": booking.id,
            "guest_name": booking.guest_name,
            "guest_phone": booking.guest_phone,
            "room_type_id": booking.room_type_id,
            "room_no": booking.room_no,
            "channel": booking.channel,
            "status": booking.status,
            "check_in_date": booking.check_in_date,
            "check_out_date": booking.check_out_date,
            "total_price": booking.total_price,
            "extra_bed_count": booking.extra_bed_count,
            "companion_names": booking.companion_list,
            "nights": booking.nights,
        }
