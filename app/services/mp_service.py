"""移动端直订小程序服务（M7-1）：房型报价 + 一键下单 + 支付单联动。

报价复用价格库存中心（DEC-01 唯一房价房量源），channel=wechat_mp；
下单复用预订引擎建 Booking，并联动 PayService 生成待支付订单。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.base import MpOrderCreated
from app.events.bus import event_bus
from app.models import RoomType
from app.services.booking_service import BookingService, _nights
from app.services.pay_service import PayService
from app.services.price_service import PriceService

CHANNEL_WECHAT_MP = "wechat_mp"


class MpService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.price = PriceService(session)
        self.pay = PayService(session)

    # ---- M7-1 房型报价 ----

    async def room_type_offers(
        self, tenant_id: str, hotel_id: int, check_in_date: str, check_out_date: str
    ) -> list[dict[str, Any]]:
        """小程序房型列表：逐晚报价 + 最低可售量（任一晚无房即不可订）。

        M30 B4：原逐晚 ``price.availability`` + ``price.resolve`` → 固定
        ``1 batch_availability + 1 batch_resolve``（每房型 2 次查询替代 2*N 次）。
        """
        nights = _nights(check_in_date, check_out_date)
        rows = await self.session.execute(
            select(RoomType).where(RoomType.tenant_id == tenant_id)
        )
        room_types = list(rows.scalars())
        # 一次性批量解析所有房型 × 所有日期（M30 B4）
        avail_by_rt: dict[int, dict[str, dict[str, int]]] = {}
        price_by_rt: dict[int, dict[str, int]] = {}
        for rt in room_types:
            avail_by_rt[rt.id] = await self.price.batch_availability(
                tenant_id, rt.id, list(nights)
            )
            price_by_rt[rt.id] = await self.price.batch_resolve(
                rt.id, list(nights), channel=CHANNEL_WECHAT_MP
            )

        offers: list[dict[str, Any]] = []
        for rt in room_types:
            per_night: list[dict[str, Any]] = []
            min_avail: int | None = None
            sold_out: list[str] = []
            avail_map = avail_by_rt.get(rt.id, {})
            price_map = price_by_rt.get(rt.id, {})
            for nd in nights:
                a = avail_map.get(nd, {"available": 0})
                p = price_map.get(nd, rt.base_price)
                per_night.append({"date": nd, "price": p, "available": a["available"]})
                min_avail = (
                    a["available"] if min_avail is None else min(min_avail, a["available"])
                )
                if a["available"] <= 0:
                    sold_out.append(nd)
            offers.append(
                {
                    "room_type_id": rt.id,
                    "code": rt.code,
                    "name": rt.name,
                    "nights": len(nights),
                    "price_per_night": per_night,
                    "total_price": sum(x["price"] for x in per_night),
                    "available": max(min_avail or 0, 0),
                    "bookable": not sold_out,
                    "sold_out_dates": sold_out,
                }
            )
        return offers

    # ---- M7-1 一键下单 ----

    async def place_order(
        self,
        tenant_id: str,
        hotel_id: int,
        room_type_id: int,
        guest_name: str,
        check_in_date: str,
        check_out_date: str,
        guest_phone: str | None = None,
    ) -> dict[str, Any]:
        """小程序下单：建预订(channel=wechat_mp) + 生成支付单（待微信支付）。"""
        bs = BookingService(self.session)
        booking = await bs.create(
            tenant_id=tenant_id,
            hotel_id=hotel_id,
            room_type_id=room_type_id,
            guest_name=guest_name,
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            channel=CHANNEL_WECHAT_MP,
            guest_phone=guest_phone,
            operator="wechat_mp",
        )
        order = await self.pay.create_order(
            tenant_id,
            hotel_id,
            booking.total_price or 0,
            subject=f"{guest_name} 房费预订",
            booking_id=booking.id,
        )
        await event_bus.publish(
            MpOrderCreated(
                tenant_id=tenant_id,
                booking_id=booking.id,
                out_trade_no=order.out_trade_no,
                amount_cents=order.amount_cents,
            )
        )
        await self.session.commit()
        return {"booking": booking, "pay_order": order}
