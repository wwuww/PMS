"""前台收银交班（M3）集成测试：开班备用金 / 班内现金 / 交班差异。"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[dict, dict]:
    t = client.post("/api/v1/tenants", json={"code": "shift", "name": "交班测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    return t, h


def _open_bill(client: TestClient, t: dict, h: dict) -> dict:
    return client.post(
        f"/api/v1/tenants/{t['code']}/bills",
        json={"hotel_id": h["id"], "guest_name": "Z"},
    ).json()


class TestShift:
    def test_open_close_balanced(self, client: TestClient) -> None:
        t, h = _seed(client)
        shift = client.post(
            f"/api/v1/tenants/{t['code']}/shifts/open",
            json={"hotel_id": h["id"], "cashier": "alice", "opening_float_cents": 5000},
        ).json()
        assert shift["status"] == "OPEN"
        assert shift["opening_float_cents"] == 5000

        # 班内 alice 收现金 20000
        bill = _open_bill(client, t, h)
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "ROOM_CHARGE", "amount": 20000},
        )
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/payments",
            json={"method": "CASH", "amount": 20000, "operator": "alice"},
        )

        # 实点 25000（= 备用金5000 + 现金20000）
        closed = client.post(
            f"/api/v1/tenants/{t['code']}/shifts/{shift['id']}/close",
            json={"counted_cash_cents": 25000},
        ).json()
        assert closed["status"] == "CLOSED"
        assert closed["expected_cash_cents"] == 25000
        assert closed["discrepancy_cents"] == 0

    def test_discrepancy_when_short(self, client: TestClient) -> None:
        t, h = _seed(client)
        shift = client.post(
            f"/api/v1/tenants/{t['code']}/shifts/open",
            json={"hotel_id": h["id"], "cashier": "bob", "opening_float_cents": 0},
        ).json()
        bill = _open_bill(client, t, h)
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "MISC", "amount": 10000},
        )
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/payments",
            json={"method": "CASH", "amount": 10000, "operator": "bob"},
        )
        # 实点 8000 → 短款 2000
        closed = client.post(
            f"/api/v1/tenants/{t['code']}/shifts/{shift['id']}/close",
            json={"counted_cash_cents": 8000},
        ).json()
        assert closed["expected_cash_cents"] == 10000
        assert closed["discrepancy_cents"] == -2000

    def test_only_own_cashier_counted(self, client: TestClient) -> None:
        t, h = _seed(client)
        shift = client.post(
            f"/api/v1/tenants/{t['code']}/shifts/open",
            json={"hotel_id": h["id"], "cashier": "carol", "opening_float_cents": 0},
        ).json()
        # carol 收 10000
        b1 = _open_bill(client, t, h)
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{b1['id']}/charges",
            json={"charge_type": "ROOM_CHARGE", "amount": 10000},
        )
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{b1['id']}/payments",
            json={"method": "CASH", "amount": 10000, "operator": "carol"},
        )
        # 另一收银员 dave 收 5000（不应计入 carol 班次）
        b2 = _open_bill(client, t, h)
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{b2['id']}/charges",
            json={"charge_type": "ROOM_CHARGE", "amount": 5000},
        )
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{b2['id']}/payments",
            json={"method": "CASH", "amount": 5000, "operator": "dave"},
        )
        closed = client.post(
            f"/api/v1/tenants/{t['code']}/shifts/{shift['id']}/close",
            json={"counted_cash_cents": 10000},
        ).json()
        assert closed["expected_cash_cents"] == 10000  # 仅 carol 的现金
        assert closed["discrepancy_cents"] == 0
