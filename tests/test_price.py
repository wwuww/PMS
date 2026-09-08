"""价格库存中心测试（FR-JG 全量，DEC-01 唯一房价房量源）。"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    tenant = client.post(
        "/api/v1/tenants", json={"code": "t-price", "name": "价格测试"}
    ).json()
    hotel = client.post(
        f"/api/v1/tenants/{tenant['id']}/hotels", json={"code": "H1", "name": "店"}
    ).json()
    room_type = client.post(
        f"/api/v1/tenants/{tenant['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    # 建 3 间房
    client.post(
        f"/api/v1/hotels/{hotel['id']}/rooms",
        json=[
            {"room_type_id": room_type["id"], "room_no": f"0{i}01"} for i in range(1, 4)
        ],
    )
    return {"tenant": tenant, "hotel": hotel, "room_type": room_type}


class TestPriceCalendar:
    def test_availability_total_and_price(self, client: TestClient) -> None:
        s = _seed(client)
        rt = s["room_type"]
        resp = client.get(
            f"/api/v1/tenants/{s['tenant']['code']}/room-types/{rt['id']}/availability",
            params={"date": "2026-10-01"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert body["available"] == 3
        assert body["price"] == 30000  # 无覆盖无折扣 → 基准价

    def test_price_calendar_override(self, client: TestClient) -> None:
        s = _seed(client)
        rt = s["room_type"]
        # 节假日溢价到 50000
        resp = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/price-calendar",
            json={"room_type_id": rt["id"], "date": "2026-10-01", "price": 50000},
        )
        assert resp.status_code == 201
        body = client.get(
            f"/api/v1/tenants/{s['tenant']['code']}/room-types/{rt['id']}/availability",
            params={"date": "2026-10-01"},
        ).json()
        assert body["price"] == 50000

    def test_ratecode_discount_applied(self, client: TestClient) -> None:
        s = _seed(client)
        rt = s["room_type"]
        client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/rate-codes",
            json={
                "code": "MEM-GOLD",
                "name": "金牌会员价",
                "channel": "direct",
                "member_level": "gold",
                "discount_pct": 9000,
            },
        )
        body = client.get(
            f"/api/v1/tenants/{s['tenant']['code']}/room-types/{rt['id']}/availability",
            params={"date": "2026-10-01", "rate_code_code": "MEM-GOLD"},
        ).json()
        assert body["price"] == 27000  # 30000 * 0.9
