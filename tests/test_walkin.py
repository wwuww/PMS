"""Sprint 6 测试：街客账（M3-7，Bill.source=WALK_IN）。

验证：无预订直接开单→来源 WALK_IN；可按来源过滤；散客账可正常加账/收款/结账。
"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    t = client.post("/api/v1/tenants", json={"code": "wk1", "name": "街客测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    return {"t": t, "h": h}


class TestWalkInBill:
    def test_walk_in_bill_source(self, client: TestClient) -> None:
        d = _seed(client)
        bill = client.post(
            f"/api/v1/tenants/{d['t']['code']}/bills",
            json={"hotel_id": d["h"]["id"], "guest_name": "路人甲"},
        ).json()
        assert bill["source"] == "WALK_IN"
        assert bill["status"] == "OPEN"

    def test_list_filter_by_source(self, client: TestClient) -> None:
        d = _seed(client)
        # 散客账
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/bills",
            json={"hotel_id": d["h"]["id"], "guest_name": "路人乙"},
        )
        # 预订账（绑定一个 CREATED 预订，需先建房型+房间以保证房量）
        rt = client.post(
            f"/api/v1/tenants/{d['t']['id']}/room-types",
            json={"code": "STD", "name": "标间", "base_price": 30000},
        ).json()
        client.post(
            f"/api/v1/hotels/{d['h']['id']}/rooms",
            json=[{"room_type_id": rt["id"], "room_no": "0109"}],
        )
        bk = client.post(
            f"/api/v1/tenants/{d['t']['code']}/bookings",
            json={
                "hotel_id": d["h"]["id"],
                "room_type_id": rt["id"],
                "guest_name": "预订客",
                "check_in_date": "2026-12-01",
                "check_out_date": "2026-12-03",
            },
        ).json()
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/bills",
            json={"hotel_id": d["h"]["id"], "guest_name": "预订客", "booking_id": bk["id"]},
        )
        walk_ins = client.get(f"/api/v1/tenants/{d['t']['code']}/bills?source=WALK_IN").json()
        bookings = client.get(f"/api/v1/tenants/{d['t']['code']}/bills?source=BOOKING").json()
        assert len(walk_ins) == 1 and walk_ins[0]["source"] == "WALK_IN"
        assert len(bookings) == 1 and bookings[0]["source"] == "BOOKING"

    def test_walk_in_settle(self, client: TestClient) -> None:
        d = _seed(client)
        bill = client.post(
            f"/api/v1/tenants/{d['t']['code']}/bills",
            json={"hotel_id": d["h"]["id"], "guest_name": "路人丙"},
        ).json()
        bid = bill["id"]
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/bills/{bid}/charges",
            json={"charge_type": "MISC", "amount": 8000, "description": "咖啡"},
        )
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/bills/{bid}/payments",
            json={"method": "CASH", "amount": 8000, "operator": "alice"},
        )
        settled = client.post(f"/api/v1/tenants/{d['t']['code']}/bills/{bid}/settle").json()
        assert settled["status"] == "SETTLED"
        assert settled["balance"] == 0
