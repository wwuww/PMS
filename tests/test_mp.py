"""Sprint 8 测试：移动端直订小程序（M7-1）。

验证：房型报价（逐晚价格/可售量/售罄判定）；下单建 wechat_mp 预订 + 待支付订单；订单详情查询。
"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    t = client.post("/api/v1/tenants", json={"code": "mp1", "name": "小程序测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[
            {"room_type_id": rt["id"], "room_no": "0301"},
            {"room_type_id": rt["id"], "room_no": "0302"},
        ],
    )
    return {"t": t, "h": h, "rt": rt}


class TestMpOrdering:
    def test_offers_quote_and_availability(self, client: TestClient) -> None:
        d = _seed(client)
        offers = client.get(
            f"/api/v1/tenants/{d['t']['code']}/mp/offers",
            params={"hotel_id": d["h"]["id"], "check_in": "2026-12-01", "check_out": "2026-12-03"},
        ).json()
        assert len(offers) == 1
        o = offers[0]
        assert o["room_type_id"] == d["rt"]["id"]
        assert o["nights"] == 2
        assert [n["price"] for n in o["price_per_night"]] == [30000, 30000]
        assert o["total_price"] == 60000
        assert o["available"] == 2
        assert o["bookable"] is True
        assert o["sold_out_dates"] == []

    def test_place_order_creates_booking_and_payorder(self, client: TestClient) -> None:
        d = _seed(client)
        r = client.post(
            f"/api/v1/tenants/{d['t']['code']}/mp/orders",
            json={
                "hotel_id": d["h"]["id"],
                "room_type_id": d["rt"]["id"],
                "guest_name": "小程序客",
                "check_in_date": "2026-12-01",
                "check_out_date": "2026-12-03",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["booking"]["channel"] == "wechat_mp"
        assert body["booking"]["status"] == "created"
        assert body["booking"]["total_price"] == 60000
        po = body["pay_order"]
        assert po["status"] == "CREATED"
        assert po["amount_cents"] == 60000
        assert po["booking_id"] == body["booking"]["id"]
        assert po["prepay_id"]  # 统一下单已返回 prepay
        assert po["paid_at"] is None

    def test_order_detail_query(self, client: TestClient) -> None:
        d = _seed(client)
        body = client.post(
            f"/api/v1/tenants/{d['t']['code']}/mp/orders",
            json={
                "hotel_id": d["h"]["id"],
                "room_type_id": d["rt"]["id"],
                "guest_name": "查询客",
                "check_in_date": "2026-12-01",
                "check_out_date": "2026-12-02",
            },
        ).json()
        r = client.get(
            f"/api/v1/tenants/{d['t']['code']}/mp/orders/{body['pay_order']['out_trade_no']}"
        )
        assert r.status_code == 200
        assert r.json()["pay_order"]["status"] == "CREATED"
        assert r.json()["booking"]["guest_name"] == "查询客"

    def test_sold_out_offer_not_bookable(self, client: TestClient) -> None:
        d = _seed(client)
        # 2 间房全部订满（2026-12-01 至 12-03）
        for i in range(2):
            client.post(
                f"/api/v1/tenants/{d['t']['code']}/bookings",
                json={
                    "hotel_id": d["h"]["id"],
                    "room_type_id": d["rt"]["id"],
                    "guest_name": f"占房{i}",
                    "check_in_date": "2026-12-01",
                    "check_out_date": "2026-12-03",
                },
            )
        offers = client.get(
            f"/api/v1/tenants/{d['t']['code']}/mp/offers",
            params={"hotel_id": d["h"]["id"], "check_in": "2026-12-01", "check_out": "2026-12-03"},
        ).json()
        o = offers[0]
        assert o["available"] == 0
        assert o["bookable"] is False
        assert o["sold_out_dates"] == ["2026-12-01", "2026-12-02"]
