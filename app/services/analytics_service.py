"""经营分析/数据中台服务（M16，FR-RP）。

核心指标均基于 DailyReport 与 Booking/Payment 计算；生产环境可切换为
ClickHouse 分析库，本服务保持聚合语义不变。
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Bill,
    BillItem,
    Booking,
    DailyReport,
    Hotel,
    Payment,
    ReportSnapshot,
    Room,
    RoomType,
)
from app.models.booking import BookingStatus
from app.models.fnb import PosOrder
from app.domain.room_state import RoomState


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- 私有辅助 ----

    async def _total_rooms(self, hotel_id: int) -> int:
        row = await self.session.execute(
            select(func.count()).select_from(Room).where(Room.hotel_id == hotel_id)
        )
        return int(row.scalar() or 0)

    async def _hotel_name(self, hotel_id: int) -> str:
        hotel = await self.session.get(Hotel, hotel_id)
        return hotel.name if hotel else ""

    async def _room_type_name(self, room_type_id: int) -> str:
        rt = await self.session.get(RoomType, room_type_id)
        return rt.name if rt else ""

    def _date_filter(self, stmt: Any, start_date: str | None, end_date: str | None, date_col: Any) -> Any:
        if start_date:
            stmt = stmt.where(date_col >= start_date)
        if end_date:
            stmt = stmt.where(date_col <= end_date)
        return stmt

    # ---- M16 核心看板（KPI 时序聚合） ----

    async def dashboard(
        self,
        tenant_id: str,
        hotel_id: int,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """单店经营看板：基于日报快照聚合 RevPAR/OCC/ADR/收入。"""
        total_rooms = await self._total_rooms(hotel_id)
        stmt = select(DailyReport).where(
            DailyReport.tenant_id == tenant_id, DailyReport.hotel_id == hotel_id
        )
        stmt = self._date_filter(stmt, start_date, end_date, DailyReport.business_date)
        result = await self.session.execute(stmt)
        rows = list(result.scalars())

        total_rooms_sum = sum(r.total_rooms for r in rows) or total_rooms * len(rows) or 1
        occupied_sum = sum(r.occupied_rooms for r in rows)
        room_revenue = sum(r.room_revenue for r in rows)
        other_revenue = sum(r.other_revenue for r in rows)
        total_revenue = sum(r.total_revenue for r in rows)

        occ_pct = (occupied_sum * 10000 // total_rooms_sum) if total_rooms_sum else 0
        adr = (room_revenue // occupied_sum) if occupied_sum else 0
        revpar = (room_revenue // total_rooms_sum) if total_rooms_sum else 0

        return {
            "hotel_id": hotel_id,
            "hotel_name": await self._hotel_name(hotel_id),
            "start_date": start_date or (rows[0].business_date if rows else None),
            "end_date": end_date or (rows[-1].business_date if rows else None),
            "days": len(rows),
            "total_rooms": total_rooms,
            "occupied_room_nights": occupied_sum,
            "room_revenue_cents": room_revenue,
            "other_revenue_cents": other_revenue,
            "total_revenue_cents": total_revenue,
            "revpar_cents": revpar,
            "adr_cents": adr,
            "occ_pct_bps": occ_pct,  # 基点，50.00% = 5000
            "daily_series": [
                {
                    "business_date": r.business_date,
                    "occupied_rooms": r.occupied_rooms,
                    "room_revenue_cents": r.room_revenue,
                    "total_revenue_cents": r.total_revenue,
                    "adr_cents": (r.room_revenue // r.occupied_rooms) if r.occupied_rooms else 0,
                    "occ_pct_bps": (r.occupied_rooms * 10000 // r.total_rooms) if r.total_rooms else 0,
                }
                for r in rows
            ],
        }

    # ---- M16 门店横向排名 ----

    async def hotel_ranking(
        self,
        tenant_id: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """多店横向排名：按日期范围聚合后按 RevPAR 降序。

        M30 #6 (B5) 批量化：1 次 hotels + 1 次 GROUP BY hotel_id 取每店 total_rooms +
        1 次 GROUP BY hotel_id 取每店 DailyReport 聚合；1+2N ≈ 201 → 3 次往返。
        M30 #6 (C7)：5min ranking 缓存（夜审后失效）。
        """
        # M30 #6 (C7)：ranking 缓存（key 含日期区间，空日期用空串占位确保 key 稳定）
        try:  # noqa: BLE001 - 缓存失败不影响主流程
            from app.infra.cache import get_cache  # noqa: PLC0415

            cache = get_cache()
            cache_key = (
                f"ranking:{tenant_id}:{start_date or ''}:{end_date or ''}"
            )
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
            ).scalars()
        )
        if not hotels:
            result = {
                "hotels": [],
                "hotel_count": 0,
                "total_room_revenue_cents": 0,
                "total_revenue_cents": 0,
            }
            if cache is not None and cache_key:
                await cache.set(cache_key, result, ttl=300)
            return result

        hotel_ids = [h.id for h in hotels]

        # 1) 每店 total_rooms 批量（一次 GROUP BY hotel_id COUNT）
        rt_counts: dict[int, int] = dict(
            (hid, int(c))
            for hid, c in (
                await self.session.execute(
                    select(Room.hotel_id, func.count())
                    .where(Room.tenant_id == tenant_id, Room.hotel_id.in_(hotel_ids))
                    .group_by(Room.hotel_id)
                )
            ).all()
        )
        # 兜底：若某店无房（极端或种子场景），仍补 0 占位便于后续 rooms_sum 推导
        for hid in hotel_ids:
            rt_counts.setdefault(hid, 0)

        # 2) 每店 DailyReport 聚合（一次 GROUP BY hotel_id + 日期范围）
        stmt = select(
            DailyReport.hotel_id.label("hotel_id"),
            func.count().label("days"),
            func.coalesce(func.sum(DailyReport.total_rooms), 0).label("rooms_sum"),
            func.coalesce(func.sum(DailyReport.occupied_rooms), 0).label("occupied_sum"),
            func.coalesce(func.sum(DailyReport.room_revenue), 0).label("room_revenue"),
            func.coalesce(func.sum(DailyReport.total_revenue), 0).label("total_revenue"),
        ).where(
            DailyReport.tenant_id == tenant_id,
            DailyReport.hotel_id.in_(hotel_ids),
        )
        stmt = self._date_filter(stmt, start_date, end_date, DailyReport.business_date)
        stmt = stmt.group_by(DailyReport.hotel_id)
        rep_rows = (await self.session.execute(stmt)).all()
        rep_map: dict[int, dict[str, int]] = {
            hid: {
                "days": int(days or 0),
                "rooms_sum": int(rooms_sum or 0),
                "occupied_sum": int(occupied_sum or 0),
                "room_revenue": int(room_revenue or 0),
                "total_revenue": int(total_revenue or 0),
            }
            for hid, days, rooms_sum, occupied_sum, room_revenue, total_revenue in rep_rows
        }

        rows: list[dict[str, Any]] = []
        for h in hotels:
            agg = rep_map.get(
                h.id,
                {"days": 0, "rooms_sum": 0, "occupied_sum": 0, "room_revenue": 0, "total_revenue": 0},
            )
            rooms_sum = agg["rooms_sum"] or rt_counts[h.id] * agg["days"] or 1
            occupied_sum = agg["occupied_sum"]
            room_revenue = agg["room_revenue"]
            total_revenue = agg["total_revenue"]
            rows.append(
                {
                    "hotel_id": h.id,
                    "name": h.name,
                    "days": agg["days"],
                    "room_revenue_cents": room_revenue,
                    "total_revenue_cents": total_revenue,
                    "revpar_cents": (room_revenue // rooms_sum) if rooms_sum else 0,
                    "adr_cents": (room_revenue // occupied_sum) if occupied_sum else 0,
                    "occ_pct_bps": (occupied_sum * 10000 // rooms_sum) if rooms_sum else 0,
                }
            )
        rows.sort(key=lambda x: x["revpar_cents"], reverse=True)
        result = {
            "hotels": rows,
            "hotel_count": len(rows),
            "total_room_revenue_cents": sum(r["room_revenue_cents"] for r in rows),
            "total_revenue_cents": sum(r["total_revenue_cents"] for r in rows),
        }
        if cache is not None and cache_key:
            await cache.set(cache_key, result, ttl=300)
        return result

    # ---- M16 渠道收入分析 ----

    async def channel_revenue(
        self,
        tenant_id: str,
        hotel_id: int,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """按预订渠道统计间夜与收入（基于 Booking.total_price）。"""
        stmt = (
            select(Booking.channel, func.count(Booking.id), func.sum(Booking.total_price))
            .where(Booking.tenant_id == tenant_id, Booking.hotel_id == hotel_id)
            .group_by(Booking.channel)
        )
        stmt = self._date_filter(stmt, start_date, end_date, Booking.check_in_date)
        result = await self.session.execute(stmt)
        rows = []
        total_nights = 0
        total_revenue = 0
        for channel, count, revenue in result.all():
            nights = int(count or 0)
            rev = int(revenue or 0)
            total_nights += nights
            total_revenue += rev
            rows.append({
                "channel": channel,
                "booking_count": nights,
                "room_revenue_cents": rev,
            })
        rows.sort(key=lambda x: x["room_revenue_cents"], reverse=True)
        return {
            "hotel_id": hotel_id,
            "hotel_name": await self._hotel_name(hotel_id),
            "start_date": start_date,
            "end_date": end_date,
            "channels": rows,
            "total_bookings": total_nights,
            "total_room_revenue_cents": total_revenue,
        }

    # ---- M16 房型收入分析 ----

    async def room_type_revenue(
        self,
        tenant_id: str,
        hotel_id: int,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """按房型统计间夜与收入（基于 Booking.total_price）。"""
        stmt = (
            select(Booking.room_type_id, func.count(Booking.id), func.sum(Booking.total_price))
            .where(Booking.tenant_id == tenant_id, Booking.hotel_id == hotel_id)
            .group_by(Booking.room_type_id)
        )
        stmt = self._date_filter(stmt, start_date, end_date, Booking.check_in_date)
        result = await self.session.execute(stmt)
        rows = []
        total_nights = 0
        total_revenue = 0
        for room_type_id, count, revenue in result.all():
            nights = int(count or 0)
            rev = int(revenue or 0)
            total_nights += nights
            total_revenue += rev
            rows.append({
                "room_type_id": room_type_id,
                "room_type_name": await self._room_type_name(int(room_type_id)),
                "booking_count": nights,
                "room_revenue_cents": rev,
            })
        rows.sort(key=lambda x: x["room_revenue_cents"], reverse=True)
        return {
            "hotel_id": hotel_id,
            "hotel_name": await self._hotel_name(hotel_id),
            "start_date": start_date,
            "end_date": end_date,
            "room_types": rows,
            "total_bookings": total_nights,
            "total_room_revenue_cents": total_revenue,
        }

    # ---- M16 导出数据（JSON/CSV 语义） ----

    async def export_data(
        self,
        report_type: str,
        tenant_id: str,
        hotel_id: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """统一导出入口，返回结构化数据（CSV 由 API 层序列化）。"""
        if report_type == "dashboard":
            if hotel_id is None:
                raise ValueError("dashboard 导出需指定 hotel_id")
            return await self.dashboard(tenant_id, hotel_id, start_date, end_date)
        if report_type == "hotel_ranking":
            return await self.hotel_ranking(tenant_id, start_date, end_date)
        if report_type == "channel_revenue":
            if hotel_id is None:
                raise ValueError("channel_revenue 导出需指定 hotel_id")
            return await self.channel_revenue(tenant_id, hotel_id, start_date, end_date)
        if report_type == "room_type_revenue":
            if hotel_id is None:
                raise ValueError("room_type_revenue 导出需指定 hotel_id")
            return await self.room_type_revenue(tenant_id, hotel_id, start_date, end_date)
        raise ValueError(f"未知报表类型: {report_type}")

    # ---- M16 账单实收明细（用于对账/审计） ----

    async def payment_summary(
        self,
        tenant_id: str,
        hotel_id: int,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """按支付方式汇总实收金额。"""
        stmt = (
            select(Payment.method, func.sum(Payment.amount))
            .join(Bill, Bill.id == Payment.bill_id)
            .where(Bill.tenant_id == tenant_id, Bill.hotel_id == hotel_id, Payment.amount > 0)
            .group_by(Payment.method)
        )
        if start_date:
            stmt = stmt.where(Payment.created_at >= f"{start_date}T00:00:00+00:00")
        if end_date:
            stmt = stmt.where(Payment.created_at <= f"{end_date}T23:59:59+00:00")
        result = await self.session.execute(stmt)
        rows = []
        total = 0
        for method, amount in result.all():
            amt = int(amount or 0)
            total += amt
            rows.append({"method": method, "amount_cents": amt})
        rows.sort(key=lambda x: x["amount_cents"], reverse=True)
        return {
            "hotel_id": hotel_id,
            "hotel_name": await self._hotel_name(hotel_id),
            "start_date": start_date,
            "end_date": end_date,
            "methods": rows,
            "total_cents": total,
        }

    # ---- M25 店总 BI：超卖预警 / 在手预测 / 自定义报表 ----

    async def _sellable_rooms(self, hotel_id: int) -> int:
        """可售房量 = 总房数 − 维修 − 停用。"""
        row = await self.session.execute(
            select(func.count()).select_from(Room).where(
                Room.hotel_id == hotel_id,
                Room.state.in_(
                    [RoomState.VACANT_CLEAN.value, RoomState.VACANT_DIRTY.value,
                     RoomState.OCCUPIED.value, RoomState.ARRIVAL_LOCKED.value]
                ),
            )
        )
        return int(row.scalar() or 0)

    async def _demand_by_date(
        self, tenant_id: str, hotel_id: int, dates: list[str]
    ) -> dict[str, int]:
        """逐日在手需求：status∈{created,checked_in} 且住期覆盖该日（时租计入入住当日）。"""
        if not dates:
            return {}
        stmt = select(Booking.check_in_date, Booking.check_out_date, Booking.stay_type).where(
            Booking.tenant_id == tenant_id,
            Booking.hotel_id == hotel_id,
            Booking.status.in_(
                [BookingStatus.CREATED.value, BookingStatus.CHECKED_IN.value]
            ),
            Booking.check_in_date <= max(dates),
            Booking.check_out_date >= min(dates),
        )
        r = await self.session.execute(stmt)
        demand: dict[str, int] = {d: 0 for d in dates}
        dset = set(dates)
        for ci, co, stay_type in r.all():
            if stay_type == "hourly":
                if ci in dset:
                    demand[ci] += 1
                continue
            # 字符串日期可直接比较（ISO 格式）
            for d in dates:
                if ci <= d < co:
                    demand[d] += 1
        return demand

    async def oversell_warnings(
        self,
        tenant_id: str,
        hotel_id: int,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """超卖预警（验收 #19）：逐日 在手预订量 vs 可售房量。"""
        y, m, d = map(int, start_date.split("-"))
        y2, m2, d2 = map(int, end_date.split("-"))
        cur, end = date(y, m, d), date(y2, m2, d2)
        dates: list[str] = []
        while cur <= end:
            dates.append(cur.isoformat())
            cur += timedelta(days=1)

        sellable = await self._sellable_rooms(hotel_id)
        demand = await self._demand_by_date(tenant_id, hotel_id, dates)
        warnings = []
        for dd in dates:
            gap = sellable - demand[dd]
            if gap < 0:
                level = "OVERSELL"
            elif gap == 0:
                level = "CRITICAL"
            else:
                continue
            warnings.append({
                "date": dd,
                "on_hand_bookings": demand[dd],
                "sellable_rooms": sellable,
                "gap": gap,
                "level": level,
            })
        return {
            "hotel_id": hotel_id,
            "hotel_name": await self._hotel_name(hotel_id),
            "start_date": start_date,
            "end_date": end_date,
            "sellable_rooms": sellable,
            "warnings": warnings,
            "warning_count": len(warnings),
        }

    async def occupancy_forecast(
        self,
        tenant_id: str,
        hotel_id: int,
        days: int = 14,
    ) -> dict[str, Any]:
        """远期在手入住率（OTB，验收 #16）：未来 N 天逐日确定入住率 + 预订增速。

        口径说明：这是「在手（on-the-books）」确定性口径，非统计预测。
        """
        days = max(1, min(days, 90))
        today = date.today()
        dates = [(today + timedelta(days=i)).isoformat() for i in range(days)]
        sellable = await self._sellable_rooms(hotel_id)
        demand = await self._demand_by_date(tenant_id, hotel_id, dates)
        forecast = [
            {
                "date": dd,
                "on_hand_bookings": demand[dd],
                "sellable_rooms": sellable,
                "occupancy_rate": round(demand[dd] / sellable, 4) if sellable else 0.0,
            }
            for dd in dates
        ]
        # 预订增速：近 14 天每日新建预订数（booking pace）
        pace_start = (today - timedelta(days=13)).isoformat()
        pr = await self.session.execute(
            select(func.date(Booking.created_at), func.count(Booking.id))
            .where(
                Booking.tenant_id == tenant_id,
                Booking.hotel_id == hotel_id,
                func.date(Booking.created_at) >= pace_start,
            )
            .group_by(func.date(Booking.created_at))
            .order_by(func.date(Booking.created_at))
        )
        pace = [{"date": str(d), "bookings": int(c or 0)} for d, c in pr.all()]
        return {
            "hotel_id": hotel_id,
            "hotel_name": await self._hotel_name(hotel_id),
            "days": days,
            "sellable_rooms": sellable,
            "forecast": forecast,
            "booking_pace": pace,
        }

    async def custom_report(
        self,
        tenant_id: str,
        hotel_id: int,
        group_by: str = "day",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        """自定义报表（验收 #15）：按房型/渠道/入住日聚合预订数与收入。"""
        if group_by not in ("room_type", "channel", "day"):
            raise ValueError("group_by 须为 room_type|channel|day")
        col = {
            "room_type": Booking.room_type_id,
            "channel": Booking.channel,
            "day": Booking.check_in_date,
        }[group_by]
        stmt = (
            select(col, func.count(Booking.id), func.sum(Booking.total_price))
            .where(
                Booking.tenant_id == tenant_id,
                Booking.hotel_id == hotel_id,
                Booking.status.in_(
                    [BookingStatus.CREATED.value, BookingStatus.CHECKED_IN.value,
                     BookingStatus.CHECKED_OUT.value]
                ),
            )
            .group_by(col)
        )
        stmt = self._date_filter(stmt, start_date, end_date, Booking.check_in_date)
        result = await self.session.execute(stmt)
        rows = []
        total_bookings = 0
        total_revenue = 0
        for key, count, revenue in result.all():
            nights = int(count or 0)
            rev = int(revenue or 0)
            total_bookings += nights
            total_revenue += rev
            row: dict[str, Any] = {"group": str(key), "booking_count": nights, "room_revenue_cents": rev}
            if group_by == "room_type":
                row["label"] = await self._room_type_name(int(key))
            rows.append(row)
        rows.sort(key=lambda x: x["group"])
        return {
            "hotel_id": hotel_id,
            "hotel_name": await self._hotel_name(hotel_id),
            "group_by": group_by,
            "start_date": start_date,
            "end_date": end_date,
            "rows": rows,
            "total_bookings": total_bookings,
            "total_room_revenue_cents": total_revenue,
        }

    # ---------- M28：历史数据留存导出 ----------

    EXPORT_HEADERS = {
        "bookings": ["id", "channel", "guest_name", "guest_phone", "check_in_date", "check_out_date", "status", "total_price_cents", "created_at"],
        "bills": ["id", "bill_no", "source", "guest_name", "room_no", "status", "balance_cents", "created_at"],
        "fnb_orders": ["id", "table_id", "guest_name", "status", "settle_type", "total_cents", "discount_cents", "created_at"],
    }

    async def export_rows(
        self,
        tenant_id: str,
        entity: str,
        start_date: str | None = None,
        end_date: str | None = None,
        batch_size: int = 500,
    ):
        """按实体的留存放大器：逐批产出行列表，内存占用与批量大小一致。"""
        from datetime import datetime as _dt

        def _created_col(model):
            return model.created_at

        def _apply_range(stmt, col):
            if start_date:
                stmt = stmt.where(col >= _dt.fromisoformat(start_date + "T00:00:00+00:00"))
            if end_date:
                stmt = stmt.where(col <= _dt.fromisoformat(end_date + "T23:59:59+00:00"))
            return stmt

        if entity == "bookings":
            col = _created_col(Booking)
            stmt = _apply_range(select(Booking).where(Booking.tenant_id == tenant_id).order_by(Booking.id), col)
            headers = self.EXPORT_HEADERS["bookings"]
            last_id = 0
            while True:
                page = (
                    await self.session.execute(stmt.where(Booking.id > last_id).limit(batch_size))
                ).scalars().all()
                if not page:
                    break
                for b in page:
                    last_id = b.id
                    yield headers, [b.id, b.channel, b.guest_name, b.guest_phone, b.check_in_date, b.check_out_date, b.status, b.total_price, str(b.created_at)]
        elif entity == "bills":
            col = _created_col(Bill)
            stmt = _apply_range(select(Bill).where(Bill.tenant_id == tenant_id).order_by(Bill.id), col)
            headers = self.EXPORT_HEADERS["bills"]
            last_id = 0
            while True:
                page = (await self.session.execute(stmt.where(Bill.id > last_id).limit(batch_size))).scalars().all()
                if not page:
                    break
                for x in page:
                    last_id = x.id
                    yield headers, [x.id, x.bill_no, x.source, x.guest_name, x.room_no, x.status, x.balance, str(x.created_at)]
        elif entity == "fnb_orders":
            col = _created_col(PosOrder)
            stmt = _apply_range(select(PosOrder).where(PosOrder.tenant_id == tenant_id).order_by(PosOrder.id), col)
            headers = self.EXPORT_HEADERS["fnb_orders"]
            last_id = 0
            while True:
                page = (await self.session.execute(stmt.where(PosOrder.id > last_id).limit(batch_size))).scalars().all()
                if not page:
                    break
                for x in page:
                    last_id = x.id
                    yield headers, [x.id, x.table_id, x.guest_name, x.status, x.settle_type, x.total_cents, x.discount_cents, str(x.created_at)]
        else:
            raise ValueError(f"不支持的导出实体：{entity}")

    # ---------- M32：周报/月报快照（验收 #14） ----------

    async def generate_snapshot(
        self,
        tenant_id: str,
        hotel_id: int,
        period_type: str,
        start_date: str,
        end_date: str,
        source: str = "MANUAL",
    ) -> ReportSnapshot:
        """固化周期报表：复用 dashboard 聚合，结果 JSON 落库（同周期幂等覆盖）。"""
        if period_type not in ("WEEKLY", "MONTHLY"):
            raise ValueError(f"不支持的周期类型：{period_type}")
        metrics = await self.dashboard(tenant_id, hotel_id, start_date=start_date, end_date=end_date)
        # 幂等：同租户同店同周期同起点覆盖
        existing = (
            await self.session.execute(
                select(ReportSnapshot).where(
                    ReportSnapshot.tenant_id == tenant_id,
                    ReportSnapshot.hotel_id == hotel_id,
                    ReportSnapshot.period_type == period_type,
                    ReportSnapshot.period_start == date.fromisoformat(start_date),
                )
            )
        ).scalars().first()
        if existing is not None:
            existing.period_end = date.fromisoformat(end_date)
            existing.metrics = json.dumps(metrics, ensure_ascii=False, default=str)
            existing.source = source
            self.session.add(existing)
            await self.session.flush()
            return existing
        snap = ReportSnapshot(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            period_type=period_type,
            period_start=date.fromisoformat(start_date),
            period_end=date.fromisoformat(end_date),
            metrics=json.dumps(metrics, ensure_ascii=False, default=str),
            source=source,
        )
        self.session.add(snap)
        await self.session.flush()
        return snap

    async def list_snapshots(
        self,
        tenant_id: str,
        hotel_id: int,
        period_type: str | None = None,
        limit: int = 50,
    ) -> list[ReportSnapshot]:
        stmt = (
            select(ReportSnapshot)
            .where(ReportSnapshot.tenant_id == tenant_id, ReportSnapshot.hotel_id == hotel_id)
            .order_by(ReportSnapshot.period_start.desc())
            .limit(max(limit, 1))
        )
        if period_type:
            stmt = stmt.where(ReportSnapshot.period_type == period_type)
        return list((await self.session.execute(stmt)).scalars())

    async def maybe_auto_snapshot(self, tenant_id: str, hotel_id: int, business_date: str) -> list[ReportSnapshot]:
        """夜审周期切换钩子：周一固化上周周报，月初 1 号固化上月月报。幂等。"""
        bd = date.fromisoformat(business_date)
        made: list[ReportSnapshot] = []
        if bd.weekday() == 0:  # Monday → 上周一~上周日
            ws, we = bd - timedelta(days=7), bd - timedelta(days=1)
            made.append(
                await self.generate_snapshot(
                    tenant_id, hotel_id, "WEEKLY", ws.isoformat(), we.isoformat(), source="AUTO"
                )
            )
        if bd.day == 1:  # 月初 → 上月自然月
            first_this = bd.replace(day=1)
            last_month_end = first_this - timedelta(days=1)
            last_month_start = last_month_end.replace(day=1)
            made.append(
                await self.generate_snapshot(
                    tenant_id, hotel_id, "MONTHLY", last_month_start.isoformat(), last_month_end.isoformat(), source="AUTO"
                )
            )
        return made
