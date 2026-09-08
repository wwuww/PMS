"""前台收银（M3）集成测试：开单 → 加账 → 收款 → 结账 / 押金 → 退款。"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[dict, dict]:
    t = client.post("/api/v1/tenants", json={"code": "cash", "name": "收银测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    return t, h


class TestCashier:
    def test_open_charge_pay_settle(self, client: TestClient) -> None:
        t, h = _seed(client)
        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills",
            json={"hotel_id": h["id"], "guest_name": "张三"},
        ).json()
        assert bill["status"] == "OPEN"
        assert bill["balance"] == 0

        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "ROOM_CHARGE", "amount": 30000, "description": "房租"},
        ).json()
        assert bill["balance"] == 30000

        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "MISC", "amount": 5000, "description": "迷你吧"},
        ).json()
        assert bill["balance"] == 35000

        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/payments",
            json={"method": "CASH", "amount": 35000},
        ).json()
        assert bill["balance"] == 0

        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/settle"
        ).json()
        assert bill["status"] == "SETTLED"

    def test_settle_blocked_when_unbalanced(self, client: TestClient) -> None:
        t, h = _seed(client)
        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills",
            json={"hotel_id": h["id"], "guest_name": "李四"},
        ).json()
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "MISC", "amount": 10000},
        )
        resp = client.post(f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/settle")
        assert resp.status_code == 409  # 余额未平不能结账

    def test_deposit_and_refund(self, client: TestClient) -> None:
        t, h = _seed(client)
        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills",
            json={"hotel_id": h["id"], "guest_name": "王五"},
        ).json()

        # 收押金 10000（多收，余额变负表示顾客已多付）
        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/payments",
            json={"method": "CASH", "amount": 10000, "is_deposit": True},
        ).json()
        assert bill["balance"] == -10000

        # 退押金 8000 → 还应退 2000
        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/refund",
            json={"method": "CASH", "amount": 8000},
        ).json()
        assert bill["balance"] == -2000
