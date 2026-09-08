"""集团多店管控服务（M17，R18）：总部驾驶舱 / 价格策略下发与改价拦截 / 两级分账。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.base import GroupPolicyApplied
from app.events.bus import event_bus
from app.models import Bill, DailyReport, GroupPricePolicy, Hotel, Payment, Room, RoomType
from app.services.audit_service import record as audit_record

PAY_NOW_METHODS = ("CASH", "PREAUTH", "UNIONPAY")  # 现付口径
PREPAID_METHODS = ("WECHAT", "ALIPAY", "STORE_VALUE")  # 预付口径


class GroupService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- M17-2 中央房价下发 + 改价拦截 ----

    async def set_price_policy(
        self,
        tenant_id: str,
        price_floor_cents: int,
        price_ceiling_cents: int | None,
        hotel_id: int | None = None,
        room_type_id: int | None = None,
        issued_by: str = "hq_admin",
        note: str = "",
    ) -> GroupPricePolicy:
        """中央下发价格策略（同维度幂等覆盖，<1 分钟全店生效语义由即时校验承载）。"""
        stmt = select(GroupPricePolicy).where(
            GroupPricePolicy.tenant_id == tenant_id,
            GroupPricePolicy.status == "ACTIVE",
            GroupPricePolicy.hotel_id == hotel_id,
            GroupPricePolicy.room_type_id == room_type_id,
        )
        row = await self.session.execute(stmt)
        policy = row.scalar_one_or_none()
        if policy:
            policy.price_floor_cents = price_floor_cents
            policy.price_ceiling_cents = price_ceiling_cents
            policy.issued_by = issued_by
            policy.note = note
        else:
            policy = GroupPricePolicy(
                tenant_id=tenant_id,
                hotel_id=hotel_id,
                room_type_id=room_type_id,
                price_floor_cents=price_floor_cents,
                price_ceiling_cents=price_ceiling_cents,
                issued_by=issued_by,
                note=note,
            )
        self.session.add(policy)
        await self.session.flush()
        await audit_record(
            self.session,
            tenant_id,
            "group.policy_issue",
            actor=issued_by,
            resource_type="group_price_policy",
            resource_id=policy.id,
            detail={
                "hotel_id": hotel_id,
                "room_type_id": room_type_id,
                "floor": price_floor_cents,
                "ceiling": price_ceiling_cents,
            },
        )
        await event_bus.publish(
            GroupPolicyApplied(
                tenant_id=tenant_id,
                policy_id=policy.id,
                room_type_id=room_type_id,
                price_floor_cents=price_floor_cents,
                price_ceiling_cents=price_ceiling_cents,
            )
        )
        return policy

    async def list_policies(self, tenant_id: str) -> list[GroupPricePolicy]:
        rows = await self.session.execute(
            select(GroupPricePolicy)
            .where(GroupPricePolicy.tenant_id == tenant_id)
            .order_by(GroupPricePolicy.id.desc())
        )
        return list(rows.scalars())

    async def assert_price_allowed(
        self, tenant_id: str, room_type_id: int, price: int
    ) -> None:
        """改价拦截（FR-JG-05）：命中 ACTIVE 策略且越界 → ValueError（API 转 403）。"""
        stmt = select(GroupPricePolicy).where(
            GroupPricePolicy.tenant_id == tenant_id,
            GroupPricePolicy.status == "ACTIVE",
            (GroupPricePolicy.room_type_id.is_(None))
            | (GroupPricePolicy.room_type_id == room_type_id),
        )
        rows = await self.session.execute(stmt)
        for p in rows.scalars():
            if price < p.price_floor_cents or (
                p.price_ceiling_cents is not None and price > p.price_ceiling_cents
            ):
                raise ValueError(
                    f"集团价格策略拦截：{price} 分超出允许区间 "
                    f"[{p.price_floor_cents}, {p.price_ceiling_cents if p.price_ceiling_cents is not None else '∞'}]"
                )

    async def record_price_block(
        self, tenant_id: str, room_type_id: int, price: int, reason: str
    ) -> None:
        await audit_record(
            self.session,
            tenant_id,
            "group.price_block",
            actor="front_desk",
            resource_type="price_calendar",
            result="failure",
            detail={"room_type_id": room_type_id, "price": price, "reason": reason},
        )

    # ---- M17-1/3 总部驾驶舱 + 门店横向对比 ----

    async def hq_dashboard(self, tenant_id: str) -> dict[str, Any]:
        """总部驾驶舱：各店最新日报聚合，按 RevPAR 降序横向对比。

        M30 #6 (B5) 批量化：1 次 hotels + 1 次 GROUP BY 取每店 total_rooms + 2 次取每
        店最新 DailyReport；1+2N ≈ 201 → 4 次往返。
        M30 #6 (C7)：5min ranking 缓存（夜审后失效）。
        """
        # M30 #6 (C7)：ranking 缓存命中走 5min 兜底；key = ranking:{tenant_id}:hq
        try:  # noqa: BLE001 - 缓存失败不影响主流程
            from app.infra.cache import get_cache  # noqa: PLC0415

            cache = get_cache()
            cache_key = f"ranking:{tenant_id}:hq"
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
                "total_revenue": 0,
                "total_room_revenue": 0,
            }
            if cache is not None and cache_key:
                await cache.set(cache_key, result, ttl=300)
            return result

        hotel_ids = [h.id for h in hotels]

        # 1) 每店 total_rooms 批量（GROUP BY hotel_id COUNT）
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
        for hid in hotel_ids:
            rt_counts.setdefault(hid, 0)

        # 2) 每店最新 DailyReport（subquery max(id) + join）
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

        rows: list[dict[str, Any]] = []
        for h in hotels:
            r = rep_map.get(h.id)
            total_rooms = rt_counts[h.id]
            revpar = (r.room_revenue // total_rooms) if r and total_rooms else 0
            rows.append(
                {
                    "hotel_id": h.id,
                    "name": h.name,
                    "business_date": r.business_date if r else None,
                    "occ_pct": r.occ_pct if r else None,
                    "adr": r.adr if r else None,
                    "revpar": revpar,
                    "room_revenue": r.room_revenue if r else 0,
                    "total_revenue": r.total_revenue if r else 0,
                }
            )
        rows.sort(key=lambda x: x["revpar"], reverse=True)
        result = {
            "hotels": rows,
            "hotel_count": len(rows),
            "total_revenue": sum(r["total_revenue"] for r in rows),
            "total_room_revenue": sum(r["room_revenue"] for r in rows),
        }
        if cache is not None and cache_key:
            await cache.set(cache_key, result, ttl=300)
        return result

    async def _total_rooms(self, hotel_id: int) -> int:
        row = await self.session.execute(
            select(func.count()).select_from(Room).where(Room.hotel_id == hotel_id)
        )
        return int(row.scalar() or 0)

    # ---- M17 两级分账汇总（v1.1 增） ----

    async def settlement(self, tenant_id: str) -> dict[str, Any]:
        """集团/分店两级现付预付分账汇总（双口径一致）。"""
        hotels = await self.session.execute(
            select(Hotel).where(Hotel.tenant_id == tenant_id).order_by(Hotel.id)
        )
        # 按酒店聚合正额收款（退款负额不计入分账口径）
        rows = await self.session.execute(
            select(Bill.hotel_id, Payment.method, func.sum(Payment.amount))
            .join(Payment, Payment.bill_id == Bill.id)
            .where(Bill.tenant_id == tenant_id, Payment.amount > 0)
            .group_by(Bill.hotel_id, Payment.method)
        )
        agg: dict[int, dict[str, int]] = {}
        for hotel_id, method, total in rows.all():
            bucket = agg.setdefault(int(hotel_id), {"pay_now": 0, "prepaid": 0})
            if method in PAY_NOW_METHODS:
                bucket["pay_now"] += int(total or 0)
            elif method in PREPAID_METHODS:
                bucket["prepaid"] += int(total or 0)
        out_rows: list[dict[str, Any]] = []
        for h in hotels.scalars():
            b = agg.get(h.id, {"pay_now": 0, "prepaid": 0})
            out_rows.append(
                {
                    "hotel_id": h.id,
                    "name": h.name,
                    "pay_now_cents": b["pay_now"],
                    "prepaid_cents": b["prepaid"],
                    "total_cents": b["pay_now"] + b["prepaid"],
                }
            )
        group = {
            "pay_now_cents": sum(r["pay_now_cents"] for r in out_rows),
            "prepaid_cents": sum(r["prepaid_cents"] for r in out_rows),
            "total_cents": sum(r["total_cents"] for r in out_rows),
        }
        return {"hotels": out_rows, "group": group}
