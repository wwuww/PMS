"""M30 B4 批量化回归验证（建单 availability/resolve 5 晚批量化）。

设计意图
--------
M30 B4 优化把 booking_service.create/extend_stay 与 mp_service.room_type_offers
从「逐晚 N+1」改为「批量固定查询」，但**必须**保证语义与原逐晚版本完全一致。

本测试作为长期回归门禁（不进 perf 套件，跑默认 CI）：
- 5 晚建单：total_price = 5 * base_price（无 RateCode）
- 5 晚建单：availability 每晚 booked 各 +1
- 续住 2 晚：added_total = 2 * base_price；total_price 累加正确
- RateCode 折扣：batch_resolve 等价于逐晚 resolve 之和
- 售罄校验：所有房被订满后第 6 单应被拒绝

任何一项失败都意味着 B4 优化造成语义漂移，必须修复后再合。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.session import get_engine
from app.models import Booking, BookingStatus, PriceCalendar, RateCode, RoomType


def _seed_basic(client: TestClient) -> dict:
    """最小可订：3 房型同类型房 / 1 个租户 / 1 个酒店。"""
    tenant = client.post(
        "/api/v1/tenants", json={"code": "t-m30-b4", "name": "B4 验证"}
    ).json()
    hotel = client.post(
        f"/api/v1/tenants/{tenant['id']}/hotels", json={"code": "H1", "name": "店"}
    ).json()
    rt = client.post(
        f"/api/v1/tenants/{tenant['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{hotel['id']}/rooms",
        json=[
            {"room_type_id": rt["id"], "room_no": "0101"},
            {"room_type_id": rt["id"], "room_no": "0102"},
            {"room_type_id": rt["id"], "room_no": "0103"},
        ],
    )
    return {"tenant": tenant, "hotel": hotel, "room_type": rt}


class TestM30B4Batch:
    """M30 B4：建单 availability/resolve 批量化语义等价。"""

    def test_5_night_booking_total_price(self, client: TestClient) -> None:
        """5 晚建单 total_price = 5 * base_price；availability 每晚 booked +1。"""
        s = _seed_basic(client)
        rt_id = s["room_type"]["id"]
        code = s["tenant"]["code"]
        base = s["room_type"]["base_price"]

        # 5 晚建单
        resp = client.post(
            f"/api/v1/tenants/{code}/bookings",
            json={
                "hotel_id": s["hotel"]["id"],
                "room_type_id": rt_id,
                "guest_name": "B4-5夜客",
                "check_in_date": "2026-11-01",
                "check_out_date": "2026-11-06",  # 5 晚
                "channel": "direct",
            },
        )
        assert resp.status_code == 201, resp.text
        b = resp.json()
        assert b["nights"] == 5
        assert b["total_price"] == base * 5  # 30000 * 5 = 150000

        # 房量占用：5 晚每晚 booked = 1；total = 3 → available = 2
        for d in ("2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"):
            avail = client.get(
                f"/api/v1/tenants/{code}/room-types/{rt_id}/availability",
                params={"date": d},
            ).json()
            assert avail["total"] == 3
            assert avail["booked"] == 1
            assert avail["available"] == 2

        # 离店次日 11-06 不应有占用
        avail = client.get(
            f"/api/v1/tenants/{code}/room-types/{rt_id}/availability",
            params={"date": "2026-11-06"},
        ).json()
        assert avail["booked"] == 0

    def test_overbooking_rejected_after_b4_batch(
        self, client: TestClient
    ) -> None:
        """3 房全被 5 晚预订后，第 4 单应被 409 拒绝（房量不足语义保留）。"""
        s = _seed_basic(client)
        rt_id = s["room_type"]["id"]
        code = s["tenant"]["code"]

        # 3 间房全部建 5 晚单
        for i in range(3):
            r = client.post(
                f"/api/v1/tenants/{code}/bookings",
                json={
                    "hotel_id": s["hotel"]["id"],
                    "room_type_id": rt_id,
                    "guest_name": f"占房{i}",
                    "check_in_date": "2026-11-01",
                    "check_out_date": "2026-11-06",
                    "channel": "direct",
                },
            )
            assert r.status_code == 201, r.text

        # 第 4 单同 5 晚应被拒绝
        r = client.post(
            f"/api/v1/tenants/{code}/bookings",
            json={
                "hotel_id": s["hotel"]["id"],
                "room_type_id": rt_id,
                "guest_name": "第4单",
                "check_in_date": "2026-11-01",
                "check_out_date": "2026-11-06",
                "channel": "direct",
            },
        )
        assert r.status_code == 409
        assert "房量不足" in r.json()["detail"]

    def test_extend_stay_2_nights(self, client: TestClient) -> None:
        """续住 2 晚：total_price 在原 3 晚基础上 +2 晚 × base_price。"""
        s = _seed_basic(client)
        rt_id = s["room_type"]["id"]
        code = s["tenant"]["code"]
        base = s["room_type"]["base_price"]

        # 入住 3 晚（11-01 至 11-04）
        booking = client.post(
            f"/api/v1/tenants/{code}/bookings",
            json={
                "hotel_id": s["hotel"]["id"],
                "room_type_id": rt_id,
                "guest_name": "续住客",
                "check_in_date": "2026-11-01",
                "check_out_date": "2026-11-04",
                "channel": "direct",
            },
        ).json()
        assert booking["total_price"] == base * 3

        client.post(
            f"/api/v1/tenants/{code}/bookings/{booking['id']}/check-in",
            json={"room_no": "0101"},
        )

        # 续住至 11-06（+2 晚）
        r = client.post(
            f"/api/v1/tenants/{code}/bookings/{booking['id']}/extend-stay",
            json={"new_check_out_date": "2026-11-06"},
        )
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["check_out_date"] == "2026-11-06"
        assert b["nights"] == 5
        assert b["total_price"] == base * 5  # 3 + 2 晚

    @pytest.mark.asyncio
    async def test_batch_resolve_equivalent_to_per_night(
        self, client: TestClient
    ) -> None:
        """batch_resolve(date_list) ≡ Σ resolve(date_i) —— 核心语义不变（无 RateCode）。"""
        s = _seed_basic(client)
        rt_id = s["room_type"]["id"]
        dates = ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"]

        # 用独立会话直接调 PriceService，避免走 HTTP 路径（HTTP 路径会受业务路由影响）
        from app.services.price_service import PriceService

        sm = async_sessionmaker(get_engine(), expire_on_commit=False)
        async with sm() as session:
            price = PriceService(session)
            batch_map = await price.batch_resolve(rt_id, dates, channel="direct")
            per_night_sum = 0
            for d in dates:
                per_night_sum += await price.resolve(rt_id, d, channel="direct")

        assert sum(batch_map.values()) == per_night_sum
        # 全部用 base_price（无 RateCode 无日历覆盖）
        assert all(v == 30000 for v in batch_map.values())

    @pytest.mark.asyncio
    async def test_batch_resolve_with_rate_code_and_calendar(
        self, client: TestClient
    ) -> None:
        """batch_resolve 叠加 RateCode 折扣 + PriceCalendar 覆盖：与逐晚结果严格一致。"""
        s = _seed_basic(client)
        # Booking/RateCode 的 tenant_id 列是 String(32) = Tenant.code（不是 BigInteger PK）
        tenant_code = s["tenant"]["code"]
        # RoomType/PriceCalendar.room_type_id 是 BigInteger，需要 int 而非 str
        rt_id = int(s["room_type"]["id"])
        dates = ["2026-12-01", "2026-12-02", "2026-12-03"]

        # 直接种 RateCode（90% 折扣）+ PriceCalendar 覆盖（节假日 +5000）
        sm = async_sessionmaker(get_engine(), expire_on_commit=False)
        async with sm() as session:
            session.add(
                RateCode(
                    tenant_id=tenant_code,
                    code="RC9",
                    name="9折",
                    channel="direct",
                    member_level="none",
                    agreement_type="none",
                    room_type_id=rt_id,
                    discount_pct=9000,
                )
            )
            for d in dates:
                session.add(
                    PriceCalendar(
                        tenant_id=tenant_code,
                        room_type_id=rt_id,
                        date=d,
                        price=35000,  # 节假日 +5000
                    )
                )
            await session.commit()

        # 用独立会话验证
        from app.services.price_service import PriceService

        sm2 = async_sessionmaker(get_engine(), expire_on_commit=False)
        async with sm2() as session:
            price = PriceService(session)
            # 按 code 路径
            batch_with_code = await price.batch_resolve(
                rt_id, dates, channel="direct", rate_code_code="RC9"
            )
            # 五维路径（也会命中这个 RateCode，因 channel/member/agreement 匹配 + room_type 匹配）
            batch_5d = await price.batch_resolve(
                rt_id, dates, channel="direct", member_level="none", agreement_type="none"
            )
            per_night_sum = 0
            for d in dates:
                per_night_sum += await price.resolve(
                    rt_id, d, channel="direct", rate_code_code="RC9"
                )

        # 35000 * 0.9 = 31500 / 晚；3 晚 = 94500
        assert sum(batch_with_code.values()) == 31500 * 3
        assert sum(batch_5d.values()) == 31500 * 3  # 五维路径同样命中专属 RateCode
        assert sum(batch_with_code.values()) == per_night_sum  # 与逐晚完全一致

    @pytest.mark.asyncio
    async def test_batch_availability_equivalent_to_per_night(
        self, client: TestClient
    ) -> None:
        """batch_availability ≡ {d: availability(d) for d in dates}（含多笔重叠占用）。"""
        s = _seed_basic(client)
        # Booking.tenant_id 列是 String(32) = Tenant.code，不是 BigInteger PK
        tenant_code = s["tenant"]["code"]
        # Booking.room_type_id 是 BigInteger FK，需要 int 而非 str
        rt_id = int(s["room_type"]["id"])
        dates = ["2027-01-01", "2027-01-02", "2027-01-03", "2027-01-04"]

        # 先建一笔 11-30 至 01-03 的预订（覆盖前 3 晚）
        client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/bookings",
            json={
                "hotel_id": s["hotel"]["id"],
                "room_type_id": rt_id,
                "guest_name": "前置占房",
                "check_in_date": "2026-12-30",
                "check_out_date": "2027-01-03",
                "channel": "direct",
            },
        )

        from app.services.price_service import PriceService

        sm = async_sessionmaker(get_engine(), expire_on_commit=False)
        async with sm() as session:
            price = PriceService(session)
            batch_map = await price.batch_availability(tenant_code, rt_id, dates)
            per_night = {d: await price.availability(tenant_code, rt_id, d) for d in dates}

        # 逐字段一致
        for d in dates:
            assert batch_map[d]["total"] == per_night[d]["total"]
            assert batch_map[d]["booked"] == per_night[d]["booked"]
            assert batch_map[d]["available"] == per_night[d]["available"]

        # 11-30 至 01-03 占用 → 01-01/01-02 各 booked=1，01-03 booked=0（不重叠）
        # 3 间房 total=3 → available=2 / 2 / 3
        assert batch_map["2027-01-01"]["booked"] == 1
        assert batch_map["2027-01-02"]["booked"] == 1
        assert batch_map["2027-01-03"]["booked"] == 0
        assert batch_map["2027-01-04"]["booked"] == 0

    def test_mp_offers_5_night_quotes(self, client: TestClient) -> None:
        """mp_service.room_type_offers：5 晚报价 = 5 × base_price（批量化路径）。"""
        s = _seed_basic(client)
        code = s["tenant"]["code"]

        offers = client.get(
            f"/api/v1/tenants/{code}/mp/offers",
            params={
                "hotel_id": s["hotel"]["id"],
                "check_in": "2027-02-01",
                "check_out": "2027-02-06",  # 5 晚
            },
        ).json()
        assert len(offers) == 1
        o = offers[0]
        assert o["nights"] == 5
        assert o["total_price"] == 30000 * 5
        assert [n["price"] for n in o["price_per_night"]] == [30000] * 5
        assert o["available"] == 3
        assert o["bookable"] is True
        assert o["sold_out_dates"] == []
