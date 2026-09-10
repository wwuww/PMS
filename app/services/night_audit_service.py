"""夜审引擎（M4，FR-YS）。DEC-03 营业日与自然日解耦。

run_night_audit 流程（验收：夜审≤5分钟，单店可秒级）：
1. 取/建 OPEN 营业日（已 CLOSED 则拒绝重复夜审）；
2. 统计当日到店/离店；
3. 遍历在住房：按价格库存中心解析当日房租并过账至账单（去重防重复过账），
   会员房按房租累积积分；在住房一律保持 OCCUPIED，房态只在真实退房时流转；
4. 汇总杂费收入，生成不可变营业日报 DailyReport；
5. 营业日置 CLOSED，发布 NightAuditCompleted 事件。
"""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.room_state import RoomState, RoomTrigger
from app.events.base import AnomalyDetected, NightAuditCompleted, utc_now
from app.events.bus import event_bus
from app.models import (
    Bill,
    BillItem,
    Booking,
    BookingStatus,
    BusinessDay,
    DailyReport,
    Hotel,
    PriceCalendar,
    RateCode,
    Room,
    RoomType,
    Tenant,
)
from app.services.analytics_service import AnalyticsService
from app.services.anomaly_service import AnomalyService
from app.services.audit_service import record as audit_record
from app.services.cashier_service import CashierService
from app.services.commission_service import CommissionService
from app.services.member_service import MemberService
from app.services.notification_service import NotificationService
from app.services.price_service import PriceService
from app.services.room_service import RoomService


class NightAuditService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _invalidate_tenant_caches(self, tenant_id: str) -> None:
        """M30 C4 + C7：夜审后失效店总 dashboard 与跨店 ranking 热点缓存（TTL 兜底 60s/300s）。

        dashboard: 单店看板（TTL 60s）；ranking: 跨店榜单（TTL 300s）。
        双重失效保证夜审后任何仪表盘都不会读到跨日旧值。
        """
        try:
            from app.infra.cache import get_cache  # noqa: PLC0415

            cache = get_cache()
            await cache.invalidate_prefix(f"dashboard:{tenant_id}")
            await cache.invalidate_prefix(f"ranking:{tenant_id}")
        except Exception:  # noqa: BLE001 - 缓存失效失败不阻断主流程
            pass

    async def _get_or_open_day(
        self, tenant_id: str, hotel_id: int, business_date: str, operator: str
    ) -> BusinessDay:
        r = await self.session.execute(
            select(BusinessDay).where(
                BusinessDay.hotel_id == hotel_id, BusinessDay.business_date == business_date
            )
        )
        bd = r.scalar_one_or_none()
        if bd and bd.status == "CLOSED":
            raise ValueError(f"营业日 {business_date} 已夜审关闭，不可重复")
        if bd and bd.status == "SUSPENDED":
            # 异常挂起的营业日允许重试：重开为 OPEN 后重新夜审
            bd.status = "OPEN"
            bd.suspended_reason = None
            self.session.add(bd)
            await self.session.flush()
            return bd
        if not bd:
            bd = BusinessDay(
                tenant_id=tenant_id, hotel_id=hotel_id, business_date=business_date, status="OPEN"
            )
            self.session.add(bd)
            await self.session.flush()
        return bd

    async def run_night_audit(
        self, tenant_id: str, hotel_id: int, business_date: str, operator: str = "night_audit"
    ) -> DailyReport:
        bd = await self._get_or_open_day(tenant_id, hotel_id, business_date, operator)

        arrived_n = await self._count(
            hotel_id, Booking.check_in_date == business_date, Booking.status == BookingStatus.CHECKED_IN.value
        )
        departed_n = await self._count(
            hotel_id, Booking.check_out_date == business_date, Booking.status == BookingStatus.CHECKED_OUT.value
        )

        rooms = await self.session.execute(
            select(Room).where(Room.hotel_id == hotel_id, Room.state == RoomState.OCCUPIED.value)
        )
        occupied_rooms = list(rooms.scalars())

        # 夜审快照（before）：过账前的房态分布、在住房、未结账单、房态差异
        dist_before = await self._room_state_distribution(hotel_id)
        unsettled = await self._unsettled_bills(hotel_id)
        anomalies_before = await self._occupied_without_booking(hotel_id, occupied_rooms, business_date)

        cs = CashierService(self.session)
        ms = MemberService(self.session)
        room_rev = 0
        room_rev_by_channel: dict[str, int] = {}

        # M30 性能优化（B1）：夜审主循环批量化。原逐房版本每间在住房约 14 次查询 +
        # 1 次提交（300 间房 ≈ 4200 次查询 + 300 次 COMMIT），改为循环前一次性批量
        # 取齐在住单 / 房价 / OPEN 账单 / 判重，循环体内仅查内存 map。
        room_nos = [r.room_no for r in occupied_rooms]
        bk_rows = list(
            (
                await self.session.execute(
                    select(Booking)
                    .where(
                        Booking.hotel_id == hotel_id,
                        Booking.status == BookingStatus.CHECKED_IN.value,
                        Booking.room_no.in_(room_nos),
                    )
                    .order_by(Booking.id.desc())
                )
            ).scalars()
        )
        # 同一房间可能残留多笔在住订单（重复入住 / 历史脏数据）。与逐房版 next(...)
        # 语义严格一致：优先「住期覆盖营业日」的最新一笔，否则取最新一笔。
        newest_by_room: dict[str, Booking] = {}
        covering_by_room: dict[str, Booking] = {}
        for b in bk_rows:
            newest_by_room.setdefault(b.room_no, b)
            if b.check_in_date <= business_date < b.check_out_date:
                covering_by_room.setdefault(b.room_no, b)
        booking_by_room: dict[str, Booking] = {}
        for room_no, b in newest_by_room.items():
            booking_by_room[room_no] = covering_by_room.get(room_no, b)

        # 批量解析房价：基准价（价格日历当日覆盖，否则 base_price）→ 五维 RateCode
        # 折扣（channel=direct / member=none / agreement=none，房型专属优先于通用），
        # 与 PriceService.resolve(room_type_id, date) 逐房结果完全一致。
        rt_ids = {r.room_type_id for r in occupied_rooms}
        rt_map = {
            rt.id: rt
            for rt in (
                await self.session.execute(
                    select(RoomType).where(RoomType.id.in_(rt_ids))
                )
            ).scalars()
        }
        cal_map = {
            (c.room_type_id, c.date): c.price
            for c in (
                await self.session.execute(
                    select(PriceCalendar).where(
                        PriceCalendar.tenant_id == tenant_id,
                        PriceCalendar.room_type_id.in_(rt_ids),
                        PriceCalendar.date == business_date,
                    )
                )
            ).scalars()
        }
        rc_map: dict[int, list[RateCode]] = {}
        for rc in (
            await self.session.execute(
                select(RateCode).where(
                    RateCode.tenant_id == tenant_id,
                    (RateCode.room_type_id.is_(None)) | (RateCode.room_type_id.in_(rt_ids)),
                    RateCode.channel == "direct",
                    RateCode.member_level == "none",
                    RateCode.agreement_type == "none",
                )
            )
        ).scalars():
            rc_map.setdefault(rc.room_type_id or 0, []).append(rc)
        price_by_rt: dict[int, int] = {}
        for rt_id in rt_ids:
            rt = rt_map.get(rt_id)
            if rt is None:
                raise ValueError("room_type 不存在")
            base = cal_map.get((rt_id, business_date), rt.base_price)
            codes = rc_map.get(rt_id) or rc_map.get(0) or []
            price_by_rt[rt_id] = codes[0].resolve_price(base) if codes else base

        # 批量取/建 OPEN 账单 + 批量判重（T1 新增 business_date 等值判重）。
        bk_ids = [b.id for b in booking_by_room.values()]
        bill_map: dict[int, Bill] = {
            b.booking_id: b
            for b in (
                await self.session.execute(
                    select(Bill).where(
                        Bill.booking_id.in_(bk_ids), Bill.status == "OPEN"
                    )
                )
            ).scalars()
        }
        for b in booking_by_room.values():
            if b.id not in bill_map:
                bill_map[b.id] = await cs.open_bill(
                    b.tenant_id, b.hotel_id, b.guest_name, b.room_no, b.id
                )
        charged_ids = {
            row[0]
            for row in (
                await self.session.execute(
                    select(BillItem.bill_id).where(
                        BillItem.bill_id.in_([bl.id for bl in bill_map.values()]),
                        BillItem.type == "ROOM_CHARGE",
                        BillItem.business_date == business_date,
                    )
                )
            ).all()
        }

        for room in occupied_rooms:
            booking = booking_by_room.get(room.room_no)
            price = price_by_rt[room.room_type_id]
            if booking and booking.stay_type == "hourly":
                # M24：时租房即住即结，夜审不过账房租（避免按整晚重复计费）
                continue
            if booking:
                bill = bill_map[booking.id]
                if bill.id not in charged_ids:
                    await cs.add_charge(
                        bill,
                        "ROOM_CHARGE",
                        price,
                        f"房租 {business_date}",
                        operator,
                        business_date=business_date,
                    )
                    charged_ids.add(bill.id)
                    if booking.guest_phone:
                        m = await ms.get_by_phone(tenant_id, booking.guest_phone)
                        if m:
                            await ms.earn_points(m, price, operator)
                # 按渠道累计佣金性房费收入（夜审佣金对账 M4-4 基数）
                ch = booking.channel or "direct"
                room_rev_by_channel[ch] = room_rev_by_channel.get(ch, 0) + price
            room_rev += price
            # 注意：此处**不得**再做「预离翻房」（OCCUPIED→VACANT_DIRTY）。在住房必须保持
            # OCCUPIED 直到真实退房（由 booking_service.check_out 负责 occupied→vacant_dirty
            # + 派清扫工单）。夜审提前翻脏会造成 rooms.state 与 bookings.status 不一致：
            # 房态盘显示空房（可被清扫后重卖 → 重房）、在住数少算，且真实退房时因源状态非
            # OCCUPIED 触发 InvalidTransition 而被卡死（见 TRANSITIONS[CHECK_OUT]）。

        other_rev = await self._other_revenue(hotel_id)
        total_n = await self._total_rooms(hotel_id)
        total_rev = room_rev + other_rev
        adr = (room_rev // arrived_n) if arrived_n else 0
        occ = (len(occupied_rooms) * 100 // total_n) if total_n else 0

        # M23（验收清单#3）：NoShow 自动处理——逾期应到未到 → 标记 + 释放预分配锁房
        noshow_ids = await self._auto_noshow(tenant_id, hotel_id, business_date, operator)

        # 夜审快照（after）：过账后的房态分布、过账房租
        dist_after = await self._room_state_distribution(hotel_id)
        snapshot = {
            "before": {
                "room_state_distribution": dist_before,
                "occupied_rooms": len(occupied_rooms),
                "unsettled_bills": unsettled,
                "anomalies": anomalies_before,
            },
            "after": {
                "room_state_distribution": dist_after,
                "posted_room_charge": room_rev,
                # 字段保留（历史日报 JSON 兼容，schema 不变）；夜审不再翻房，恒为空数组
                "flipped_rooms": [],
            },
            "diff": {
                "occupied_delta": len(occupied_rooms) - dist_after.get(RoomState.OCCUPIED.value, 0),
            },
            "noshow": {
                "booking_ids": noshow_ids,
                "count": len(noshow_ids),
            },
        }

        report = DailyReport(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            business_date=business_date,
            arrived_rooms=arrived_n,
            departed_rooms=departed_n,
            occupied_rooms=len(occupied_rooms),
            total_rooms=total_n,
            room_revenue=room_rev,
            other_revenue=other_rev,
            total_revenue=total_rev,
            adr=adr,
            occ_pct=occ,
            snapshot=json.dumps(snapshot, ensure_ascii=False),
        )
        self.session.add(report)

        # M32.18（验收 #14）：日切扫描超期预授权并自动释放（30 天规则，双保险之一；
        # 另一路为独立端点 /deposits/auto-release 供运维/cron 兜底）。释放记录进快照。
        from app.services.deposit_service import DepositService

        released = await DepositService(self.session).auto_release_expired(
            tenant_id, hotel_id=hotel_id, days=30, operator="night_audit"
        )
        if released["released"]:
            snapshot.setdefault("deposits", {}).update(
                {
                    "auto_released_preauth": released["released"],
                    "auto_released_ids": released["ids"],
                }
            )
            report.snapshot = json.dumps(snapshot, ensure_ascii=False)

        # 夜审佣金对账（M4-4）：按渠道计提佣金，沉淀不可变对账行
        if room_rev_by_channel:
            await CommissionService(self.session).reconcile(
                tenant_id, hotel_id, business_date, room_rev_by_channel
            )

        bd.status = "CLOSED"
        bd.audited_at = utc_now().isoformat()
        bd.audited_by = operator
        self.session.add(bd)
        await self.session.commit()
        await self.session.refresh(report)

        # M10-4（FR-APP-04）：夜审完成自动推送营业日报至店长端
        await NotificationService(self.session).push_daily_report(report)

        # M32（验收 #14）：周期切换自动固化周报/月报快照（周一/月初，幂等）
        await AnalyticsService(self.session).maybe_auto_snapshot(
            tenant_id, hotel_id, business_date
        )
        await self.session.commit()

        await event_bus.publish(
            NightAuditCompleted(
                tenant_id=tenant_id,
                hotel_id=hotel_id,
                business_date=business_date,
                total_revenue=total_rev,
                occupied_rooms=len(occupied_rooms),
            )
        )

        # M12 AI 自动对账：夜审后扫描异常交易并推送预警
        alerts = await AnomalyService(self.session).scan_after_night_audit(
            tenant_id, hotel_id, business_date
        )
        for alert in alerts:
            await event_bus.publish(
                AnomalyDetected(
                    tenant_id=tenant_id,
                    alert_id=alert.id,
                    alert_type=alert.alert_type,
                    severity=alert.severity,
                    hotel_id=hotel_id,
                )
            )
        await self.session.commit()
        await self._invalidate_tenant_caches(tenant_id)
        return report

    # ---- 内部辅助 ----
    async def night_audit_board(self, tenant_id: str) -> dict:
        """集团跨店夜审监控（M17-lite）：各店最新营业日状态 + 挂账数 + 最新日报摘要。

        纯只读聚合。M30 #6 (B5)：批量取每店最新 BusinessDay / SUSPENDED 计数 / 最新
        DailyReport，3 次往返替代原 1+3N；M30 #6 (C7)：5 分钟命中缓存（夜审后失效）。

        查询预算：
          1) hotels (1)
          2) latest BusinessDay subquery + join (1)
          3) SUSPENDED count GROUP BY hotel_id (1)
          4) latest DailyReport subquery + join (1)
        合计 4 次往返（vs 1+3N ≈ 301 次）。
        """
        # M30 #6 (C7)：ranking 缓存命中走 5min 兜底；key = ranking:{tenant_id}:board
        try:  # noqa: BLE001 - 缓存失败不影响主流程
            from app.infra.cache import get_cache  # noqa: PLC0415

            cache = get_cache()
            cache_key = f"ranking:{tenant_id}:board"
            cached = await cache.get(cache_key)
            if cached is not None:
                return cached
        except Exception:  # noqa: BLE001
            cache = None  # type: ignore[assignment]
            cache_key = None  # type: ignore[assignment]

        hotels = list(
            (
                await self.session.execute(
                    select(Hotel).where(Hotel.tenant_id == tenant_id).order_by(Hotel.id)
                )
            )
            .scalars()
            .all()
        )
        if not hotels:
            result = {"hotels": [], "hotel_count": 0, "total_suspended": 0}
            if cache is not None and cache_key:
                await cache.set(cache_key, result, ttl=300)
            return result

        hotel_ids = [h.id for h in hotels]

        # 1) 每店最新 BusinessDay（subquery max(business_date) + join）
        latest_bd = (
            select(
                BusinessDay.hotel_id.label("hotel_id"),
                func.max(BusinessDay.business_date).label("bd"),
            )
            .where(BusinessDay.tenant_id == tenant_id, BusinessDay.hotel_id.in_(hotel_ids))
            .group_by(BusinessDay.hotel_id)
        ).subquery()
        bd_rows = (
            await self.session.execute(
                select(BusinessDay).join(
                    latest_bd,
                    (BusinessDay.hotel_id == latest_bd.c.hotel_id)
                    & (BusinessDay.business_date == latest_bd.c.bd),
                )
            )
        ).scalars().all()
        bd_map: dict[int, BusinessDay] = {bd.hotel_id: bd for bd in bd_rows}

        # 2) 每店 SUSPENDED 计数（GROUP BY hotel_id COUNT）
        susp_map: dict[int, int] = dict(
            (
                await self.session.execute(
                    select(BusinessDay.hotel_id, func.count())
                    .where(
                        BusinessDay.tenant_id == tenant_id,
                        BusinessDay.hotel_id.in_(hotel_ids),
                        BusinessDay.status == "SUSPENDED",
                    )
                    .group_by(BusinessDay.hotel_id)
                )
            ).all()
        )

        # 3) 每店最新 DailyReport（subquery max(id) + join，等价于 max(business_date)
        # 但对同日多份快报告 id 排序更确定）
        latest_rep = (
            select(
                DailyReport.hotel_id.label("hotel_id"),
                func.max(DailyReport.id).label("max_id"),
            )
            .where(DailyReport.tenant_id == tenant_id, DailyReport.hotel_id.in_(hotel_ids))
            .group_by(DailyReport.hotel_id)
        ).subquery()
        rep_rows = (
            await self.session.execute(
                select(DailyReport).join(
                    latest_rep,
                    (DailyReport.hotel_id == latest_rep.c.hotel_id)
                    & (DailyReport.id == latest_rep.c.max_id),
                )
            )
        ).scalars().all()
        rep_map: dict[int, DailyReport] = {r.hotel_id: r for r in rep_rows}

        rows: list[dict] = []
        total_suspended = 0
        for h in hotels:
            bd = bd_map.get(h.id)
            rep = rep_map.get(h.id)
            susp = int(susp_map.get(h.id, 0))
            total_suspended += susp
            rows.append(
                {
                    "hotel_id": h.id,
                    "name": h.name,
                    "latest_business_date": bd.business_date if bd else None,
                    "latest_status": bd.status if bd else None,
                    "suspended_count": susp,
                    "latest_report": {
                        "business_date": rep.business_date if rep else None,
                        "occ_pct": rep.occ_pct if rep else None,
                        "room_revenue": rep.room_revenue if rep else 0,
                        "total_revenue": rep.total_revenue if rep else 0,
                    },
                }
            )
        result = {
            "hotels": rows,
            "hotel_count": len(rows),
            "total_suspended": total_suspended,
        }
        if cache is not None and cache_key:
            await cache.set(cache_key, result, ttl=300)
        return result

    async def _auto_noshow(
        self, tenant_id: str, hotel_id: int, business_date: str, operator: str
    ) -> list[int]:
        """NoShow 自动处理（验收清单#3 + M31 扣首晚房费）：

        扫描「逾期应到未到」预订（status=CREATED 且 check_in_date < 营业日），
        标记为 NOSHOW 并记录原因；若已为其预分配锁房(arrival_locked)则释放为空净房。
        若 Hotel.noshow_charge_first_night（酒店级覆盖）/ Tenant.noshow_charge_first_night
        （租户级默认）任一为 True，则按首晚价过账至账单（仅非时租；幂等防重）。
        """
        # M31：两层兜底读 NoShow 扣首晚配置（Hotel 覆盖 Tenant 默认；Hotel=None 继承 Tenant）
        # tenant_id 是租户 code（String），Tenant 表里主键是 BigInteger，但用 code 关联
        hotel_cfg = (
            await self.session.execute(
                select(Hotel.noshow_charge_first_night).where(Hotel.id == hotel_id)
            )
        ).scalar_one_or_none()
        tenant_cfg = (
            await self.session.execute(
                select(Tenant.noshow_charge_first_night).where(Tenant.code == tenant_id)
            )
        ).scalar_one_or_none()
        enabled = hotel_cfg if hotel_cfg is not None else bool(tenant_cfg)

        rows = await self.session.execute(
            select(Booking).where(
                Booking.hotel_id == hotel_id,
                Booking.status == BookingStatus.CREATED.value,
                Booking.check_in_date < business_date,
            )
        )
        marked: list[int] = []
        for bk in list(rows.scalars()):
            bk.status = BookingStatus.NOSHOW.value
            bk.noshow_reason = (
                f"逾期未到（应到 {bk.check_in_date}），夜审 {business_date} 自动标记"
            )
            self.session.add(bk)
            await self._release_noshow_room(hotel_id, bk.room_no, operator)
            # M31：标记 NOSHOW 后过账首晚房费（仅配置启用 + 非时租；异常隔离，不阻断 NoShow）
            if enabled and bk.stay_type != "hourly":
                try:
                    await self._charge_noshow_first_night(bk, operator)
                except Exception:  # noqa: BLE001 - 首晚扣款失败不阻断 NoShow 标记
                    pass
            marked.append(bk.id)
        if marked:
            await self.session.flush()
        return marked

    async def _charge_noshow_first_night(self, booking: Booking, operator: str) -> None:
        """M31：NoShow 过账首晚房费（幂等）。

        1) 取/建 OPEN 账单；2) 查同 (bill, ROOM_CHARGE, check_in_date) 是否已存在，有则跳过；
        3) 算首晚价（PriceService.batch_resolve，含 RateCode 五维匹配）；
        4) add_charge 写入 BillItem + 累 bill.balance（add_charge 只 flush 不 commit，由
           run_night_audit 末尾统一 commit）；5) 审计留痕 AuditLog。
        """
        # 1) 取/建 OPEN 账单
        bill_r = await self.session.execute(
            select(Bill).where(
                Bill.booking_id == booking.id, Bill.status == "OPEN"
            )
        )
        bill = bill_r.scalar_one_or_none()
        if bill is None:
            bill = await CashierService(self.session).open_bill(
                booking.tenant_id,
                booking.hotel_id,
                booking.guest_name,
                booking.room_no,
                booking.id,
            )

        # 2) 防重复：同 (bill, type, business_date) 已存在则跳过
        existing = await self.session.execute(
            select(BillItem.id).where(
                BillItem.bill_id == bill.id,
                BillItem.type == "ROOM_CHARGE",
                BillItem.business_date == booking.check_in_date,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return  # 已过账，幂等跳过

        # 3) 算首晚价（按 booking.rate_code_id 取 code，否则走五维 RateCode 匹配）
        rate_code_code: str | None = None
        if booking.rate_code_id is not None:
            rc = await self.session.get(RateCode, booking.rate_code_id)
            rate_code_code = rc.code if rc is not None else None

        price_map = await PriceService(self.session).batch_resolve(
            booking.room_type_id,
            [booking.check_in_date],
            channel=booking.channel,
            rate_code_code=rate_code_code,
        )
        first_night_price = price_map[booking.check_in_date]

        # 4) 过账
        await CashierService(self.session).add_charge(
            bill,
            "ROOM_CHARGE",
            first_night_price,
            f"NoShow首晚 {booking.check_in_date}",
            operator,
            business_date=booking.check_in_date,
        )

        # 5) 审计留痕
        await audit_record(
            self.session,
            tenant_id=booking.tenant_id,
            hotel_id=booking.hotel_id,
            actor=operator,
            action="noshow.first_night_charged",
            resource_type="booking",
            resource_id=str(booking.id),
            detail={
                "amount": first_night_price,
                "business_date": booking.check_in_date,
            },
        )

    async def _release_noshow_room(
        self, hotel_id: int, room_no: str | None, operator: str
    ) -> bool:
        """NoShow 后释放预分配锁房：仅 arrival_locked → vacant_clean，其余状态不动。"""
        if not room_no:
            return False
        r = await self.session.execute(
            select(Room).where(Room.hotel_id == hotel_id, Room.room_no == room_no)
        )
        room = r.scalar_one_or_none()
        if room is None or room.state != RoomState.ARRIVAL_LOCKED.value:
            return False
        await RoomService(self.session).transition(
            room, RoomTrigger.RELEASE_ARRIVAL, operator=operator
        )
        return True

    async def _room_state_distribution(self, hotel_id: int) -> dict[str, int]:
        """全量房态分布（含空净/空脏/在住/锁房/维修/停用）。"""
        rows = await self.session.execute(
            select(Room.state, func.count())
            .select_from(Room)
            .where(Room.hotel_id == hotel_id)
            .group_by(Room.state)
        )
        dist = {s.value: 0 for s in RoomState}
        for state, cnt in rows.all():
            dist[state] = int(cnt)
        return dist

    async def _unsettled_bills(self, hotel_id: int) -> dict[str, int]:
        """未结账单（OPEN）数量与未结金额（分，余额=应收-实收）。"""
        row = await self.session.execute(
            select(func.count(), func.coalesce(func.sum(Bill.balance), 0))
            .select_from(Bill)
            .where(Bill.hotel_id == hotel_id, Bill.status == "OPEN")
        )
        count, amount = row.one()
        return {"count": int(count or 0), "amount": int(amount or 0)}

    async def _occupied_without_booking(
        self, hotel_id: int, occupied_rooms: list[Room], business_date: str
    ) -> list[dict]:
        """房态差异检测：在住房但无覆盖营业日的在住预订（脏数据/重复入住）。"""
        anomalies: list[dict] = []
        for room in occupied_rooms:
            bk = await self.session.execute(
                select(Booking).where(
                    Booking.hotel_id == hotel_id,
                    Booking.room_no == room.room_no,
                    Booking.status == BookingStatus.CHECKED_IN.value,
                    Booking.check_in_date <= business_date,
                    business_date < Booking.check_out_date,
                )
            )
            if not bk.scalars().first():
                anomalies.append({"room_no": room.room_no, "type": "occupied_without_booking"})
        return anomalies

    async def _count(self, hotel_id: int, *where: object) -> int:
        row = await self.session.execute(
            select(func.count())
            .select_from(Booking)
            .where(Booking.hotel_id == hotel_id, *where)
        )
        return int(row.scalar() or 0)

    async def _total_rooms(self, hotel_id: int) -> int:
        row = await self.session.execute(
            select(func.count()).select_from(Room).where(Room.hotel_id == hotel_id)
        )
        return int(row.scalar() or 0)

    async def _bill_for_booking(self, booking: Booking, cs: CashierService) -> Bill:
        r = await self.session.execute(
            select(Bill).where(Bill.booking_id == booking.id, Bill.status == "OPEN")
        )
        b = r.scalar_one_or_none()
        if b:
            return b
        return await cs.open_bill(
            booking.tenant_id, booking.hotel_id, booking.guest_name, booking.room_no, booking.id
        )

    async def _has_room_charge_today(self, bill_id: int, business_date: str) -> bool:
        r = await self.session.execute(
            select(func.count())
            .select_from(BillItem)
            .where(
                BillItem.bill_id == bill_id,
                BillItem.type == "ROOM_CHARGE",
                BillItem.business_date == business_date,
            )
        )
        return int(r.scalar() or 0) > 0

    async def _other_revenue(self, hotel_id: int) -> int:
        r = await self.session.execute(
            select(func.coalesce(func.sum(BillItem.amount), 0))
            .select_from(BillItem)
            .join(Bill, Bill.id == BillItem.bill_id)
            .where(Bill.hotel_id == hotel_id, Bill.status == "SETTLED", BillItem.type == "MISC")
        )
        return int(r.scalar() or 0)
