"""佣金对账（M4-4）集成测试：规则设定 / 夜审计提 / 查询。"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[dict, dict, dict]:
    t = client.post("/api/v1/tenants", json={"code": "comm", "name": "佣金测试"}).json()
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


def _check_in_ota(client: TestClient, t: dict, rt: dict, h: dict, phone: str) -> None:
    bk = client.post(
        f"/api/v1/tenants/{t['code']}/bookings",
        json={
            "hotel_id": h["id"],
            "room_type_id": rt["id"],
            "guest_name": "G",
            "guest_phone": phone,
            "check_in_date": "2026-10-01",
            "check_out_date": "2026-10-03",
            "room_no": "0101",
            "channel": "ota_ctrip",
        },
    ).json()
    client.post(
        f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-in",
        json={"room_no": "0101"},
    )


class TestCommission:
    def test_set_and_list_rule(self, client: TestClient) -> None:
        t, h, rt = _seed(client)
        rule = client.post(
            f"/api/v1/tenants/{t['code']}/commission-rules",
            json={"channel": "ota_ctrip", "rate_bps": 1000, "note": "携程10%"},
        ).json()
        assert rule["rate_bps"] == 1000
        rules = client.get(f"/api/v1/tenants/{t['code']}/commission-rules").json()
        assert len(rules) == 1
        assert rules[0]["channel"] == "ota_ctrip"

    def test_night_audit_accrues_commission(self, client: TestClient) -> None:
        t, h, rt = _seed(client)
        client.post(
            f"/api/v1/tenants/{t['code']}/commission-rules",
            json={"channel": "ota_ctrip", "rate_bps": 1000},
        )
        _check_in_ota(client, t, rt, h, "13700000011")

        client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-01"},
        )
        recs = client.get(
            f"/api/v1/tenants/{t['code']}/commission-reconciliations"
        ).json()
        assert len(recs) == 1
        assert recs[0]["channel"] == "ota_ctrip"
        assert recs[0]["room_revenue_cents"] == 30000
        assert recs[0]["commission_rate_bps"] == 1000
        assert recs[0]["commission_cents"] == 3000  # 30000 * 10%
        assert recs[0]["status"] == "PENDING"

    def test_no_rule_no_commission(self, client: TestClient) -> None:
        t, h, rt = _seed(client)
        # 不设任何佣金规则
        _check_in_ota(client, t, rt, h, "13700000012")
        client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-01"},
        )
        recs = client.get(
            f"/api/v1/tenants/{t['code']}/commission-reconciliations"
        ).json()
        assert recs == []  # 无规则不计提
