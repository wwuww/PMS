"""会员 CRM（M13）集成测试：注册 / 充值 / 结账累积积分。"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[dict, dict, dict]:
    t = client.post("/api/v1/tenants", json={"code": "mb", "name": "会员测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[{"room_type_id": rt["id"], "room_no": "0101"}],
    )
    return t, h, rt


class TestMember:
    def test_register_and_recharge(self, client: TestClient) -> None:
        t, h, _ = _seed(client)
        m = client.post(
            f"/api/v1/tenants/{t['code']}/members",
            json={"hotel_id": h["id"], "name": "李雷", "phone": "13800000001"},
        ).json()
        assert m["points"] == 0 and m["stored_value"] == 0

        m = client.post(
            f"/api/v1/tenants/{t['code']}/members/13800000001/recharge",
            json={"amount": 50000},
        ).json()
        assert m["stored_value"] == 50000

    def test_points_accrue_on_settle(self, client: TestClient) -> None:
        t, h, rt = _seed(client)
        # 注册带手机号会员
        client.post(
            f"/api/v1/tenants/{t['code']}/members",
            json={"hotel_id": h["id"], "name": "韩梅", "phone": "13800000002"},
        )
        # 预订并入住（绑定手机号）
        bk = client.post(
            f"/api/v1/tenants/{t['code']}/bookings",
            json={
                "hotel_id": h["id"],
                "room_type_id": rt["id"],
                "guest_name": "韩梅",
                "guest_phone": "13800000002",
                "check_in_date": "2026-11-01",
                "check_out_date": "2026-11-02",
                "room_no": "0101",
            },
        ).json()
        client.post(
            f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-in",
            json={"room_no": "0101"},
        )

        # 开单（绑定 booking）→ 加房租 → 收款 → 结账
        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills",
            json={"hotel_id": h["id"], "guest_name": "韩梅", "booking_id": bk["id"]},
        ).json()
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "ROOM_CHARGE", "amount": 30000, "description": "房租 2026-11-01"},
        )
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/payments",
            json={"method": "WECHAT", "amount": 30000},
        )
        client.post(f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/settle")

        m = client.get(f"/api/v1/tenants/{t['code']}/members/13800000002").json()
        assert m["points"] >= 300  # 30000 分(=300元) → 300 积分
        assert m["total_spend"] == 30000
