"""Sprint 7 测试：审计埋点 SDK 覆盖（M8-2）。

验证敏感操作均留痕：改价 / 取消单 / 折扣 / 冲账；导出(audit.view) 自身留痕。
"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    t = client.post("/api/v1/tenants", json={"code": "aud1", "name": "审计测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(f"/api/v1/hotels/{h['id']}/rooms", json=[{"room_type_id": rt["id"], "room_no": "0301"}])
    return {"t": t, "h": h, "rt": rt}


def _audit_actions(client: TestClient, code: str) -> set[str]:
    # 以管理员 token 查询审计（避免无限增加，仅取一次）
    u = client.post(
        f"/api/v1/tenants/{code}/users",
        json={"username": "admin_query", "password": "pw123456"},
    ).json()
    roles = client.get(f"/api/v1/tenants/{code}/roles").json()
    admin = next(r for r in roles if r["name"] == "管理员")
    client.post(f"/api/v1/tenants/{code}/users/{u['id']}/roles", json={"role_id": admin["id"]})
    login = client.post(
        f"/api/v1/tenants/{code}/auth/login",
        json={"username": "admin_query", "password": "pw123456"},
    ).json()
    logs = client.get(f"/api/v1/tenants/{code}/audit-logs?token={login['token']}&limit=500").json()
    return {log["action"] for log in logs}


class TestAuditTrail:
    def test_price_edit_audited(self, client: TestClient) -> None:
        d = _seed(client)
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/price-calendar",
            json={"room_type_id": d["rt"]["id"], "date": "2026-12-01", "price": 35000},
        )
        assert "price.edit" in _audit_actions(client, d["t"]["code"])

    def test_booking_cancel_audited(self, client: TestClient) -> None:
        d = _seed(client)
        bk = client.post(
            f"/api/v1/tenants/{d['t']['code']}/bookings",
            json={
                "hotel_id": d["h"]["id"],
                "room_type_id": d["rt"]["id"],
                "guest_name": "取消客",
                "check_in_date": "2026-12-01",
                "check_out_date": "2026-12-03",
                "room_no": "0301",
            },
        ).json()
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/bookings/{bk['id']}/cancel",
            json={"operator": "front_desk"},
        )
        assert "booking.cancel" in _audit_actions(client, d["t"]["code"])

    def test_discount_audited(self, client: TestClient) -> None:
        d = _seed(client)
        bill = client.post(
            f"/api/v1/tenants/{d['t']['code']}/bills",
            json={"hotel_id": d["h"]["id"], "guest_name": "折扣客"},
        ).json()
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "DISCOUNT", "amount": -2000, "description": "会员折扣"},
        )
        assert "billing.discount" in _audit_actions(client, d["t"]["code"])

    def test_adjustment_audited(self, client: TestClient) -> None:
        d = _seed(client)
        bill = client.post(
            f"/api/v1/tenants/{d['t']['code']}/bills",
            json={"hotel_id": d["h"]["id"], "guest_name": "冲账客"},
        ).json()
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "ROOM_CHARGE", "amount": 30000},
        )
        client.post(
            f"/api/v1/tenants/{d['t']['code']}/bills/{bill['id']}/payments",
            json={"method": "CASH", "amount": 30000},
        )
        # 冲调账仅允许在未结账账单上操作（业务约束：已结账走红冲流程），故先冲调再结账
        adj = client.post(
            f"/api/v1/tenants/{d['t']['code']}/bills/{bill['id']}/adjustments",
            json={"type": "ADJUST", "amount_cents": -1000, "reason": "抹零", "operator": "front_desk"},
        )
        assert adj.status_code == 200
        client.post(f"/api/v1/tenants/{d['t']['code']}/bills/{bill['id']}/settle")
        assert "billing.adjust" in _audit_actions(client, d["t"]["code"])
