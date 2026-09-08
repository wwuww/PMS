"""冲调账（M4-5）集成测试：余额重算 / 已结账拒收 / 零金额拒收。"""

from fastapi.testclient import TestClient


def _open_bill(client: TestClient, t: dict, h: dict) -> dict:
    return client.post(
        f"/api/v1/tenants/{t['code']}/bills",
        json={"hotel_id": h["id"], "guest_name": "G"},
    ).json()


def _seed(client: TestClient) -> tuple[dict, dict]:
    t = client.post("/api/v1/tenants", json={"code": "adj", "name": "冲调测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    return t, h


class TestAdjustment:
    def test_adjustment_recomputes_balance(self, client: TestClient) -> None:
        t, h = _seed(client)
        bill = _open_bill(client, t, h)
        bid = bill["id"]

        client.post(f"/api/v1/tenants/{t['code']}/bills/{bid}/charges",
                    json={"charge_type": "ROOM_CHARGE", "amount": 30000})
        client.post(f"/api/v1/tenants/{t['code']}/bills/{bid}/payments",
                    json={"method": "CASH", "amount": 20000})
        # 余额应为 10000；开调账凭证冲减 5000（多收更正）
        r = client.post(f"/api/v1/tenants/{t['code']}/bills/{bid}/adjustments",
                        json={"type": "ADJUST", "amount_cents": -5000, "reason": "多收更正"})
        assert r.status_code == 200
        assert r.json()["balance"] == 5000  # 10000 - 5000
        assert len(r.json()["adjustments"]) == 1
        assert r.json()["adjustments"][0]["type"] == "ADJUST"

        # 补收尾款后平账结账
        client.post(f"/api/v1/tenants/{t['code']}/bills/{bid}/payments",
                    json={"method": "CASH", "amount": 5000})
        settled = client.post(f"/api/v1/tenants/{t['code']}/bills/{bid}/settle").json()
        assert settled["status"] == "SETTLED"
        assert settled["balance"] == 0

    def test_adjustment_rejected_on_settled(self, client: TestClient) -> None:
        t, h = _seed(client)
        bill = _open_bill(client, t, h)
        bid = bill["id"]
        client.post(f"/api/v1/tenants/{t['code']}/bills/{bid}/charges",
                    json={"charge_type": "ROOM_CHARGE", "amount": 10000})
        client.post(f"/api/v1/tenants/{t['code']}/bills/{bid}/payments",
                    json={"method": "CASH", "amount": 10000})
        client.post(f"/api/v1/tenants/{t['code']}/bills/{bid}/settle")
        r = client.post(f"/api/v1/tenants/{t['code']}/bills/{bid}/adjustments",
                        json={"type": "VOID", "amount_cents": -1000, "reason": "x"})
        assert r.status_code == 400  # 已结账不可直接冲调

    def test_adjustment_zero_rejected(self, client: TestClient) -> None:
        t, h = _seed(client)
        bill = _open_bill(client, t, h)
        bid = bill["id"]
        r = client.post(f"/api/v1/tenants/{t['code']}/bills/{bid}/adjustments",
                        json={"type": "ADJUST", "amount_cents": 0, "reason": "x"})
        assert r.status_code == 400
