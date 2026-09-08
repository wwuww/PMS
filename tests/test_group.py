"""Sprint 10：集团多店管控 M17（FR-R18 / FR-JG-05）测试。"""

import uuid

import pytest


@pytest.fixture
def multi_hotel_tenant(client):
    """创建一个含两店、两种房型、若干房间的租户。"""
    code = f"grp{uuid.uuid4().hex[:8]}"
    t = client.post("/api/v1/tenants", json={"code": code, "name": "集团测试租户"}).json()
    h1 = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H1", "name": "深圳店"}).json()
    h2 = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H2", "name": "广州店"}).json()
    rt1 = client.post(f"/api/v1/tenants/{t['id']}/room-types", json={"code": "STD", "name": "标准间", "base_price": 20000}).json()
    rt2 = client.post(f"/api/v1/tenants/{t['id']}/room-types", json={"code": "DLX", "name": "豪华间", "base_price": 30000}).json()
    client.post(f"/api/v1/hotels/{h1['id']}/rooms", json=[
        {"room_type_id": rt1["id"], "room_no": "0101"},
        {"room_type_id": rt1["id"], "room_no": "0102"},
    ])
    client.post(f"/api/v1/hotels/{h2['id']}/rooms", json=[
        {"room_type_id": rt2["id"], "room_no": "0201"},
    ])
    return {"t": t, "h1": h1, "h2": h2, "rt1": rt1, "rt2": rt2}


class TestGroupPricePolicy:
    def test_set_price_policy_overrides(self, client, multi_hotel_tenant):
        d = multi_hotel_tenant
        r1 = client.post(f"/api/v1/tenants/{d['t']['code']}/group/price-policies", json={
            "price_floor_cents": 15000,
            "price_ceiling_cents": 50000,
            "room_type_id": d["rt1"]["id"],
            "note": "首次",
        }).json()
        assert r1["price_floor_cents"] == 15000
        assert r1["status"] == "ACTIVE"
        # 同维度幂等覆盖
        r2 = client.post(f"/api/v1/tenants/{d['t']['code']}/group/price-policies", json={
            "price_floor_cents": 18000,
            "price_ceiling_cents": 45000,
            "room_type_id": d["rt1"]["id"],
            "note": "第二次",
        }).json()
        assert r2["id"] == r1["id"]
        assert r2["price_floor_cents"] == 18000
        assert r2["price_ceiling_cents"] == 45000

    def test_price_below_floor_blocked_and_audited(self, client, multi_hotel_tenant):
        d = multi_hotel_tenant
        client.post(f"/api/v1/tenants/{d['t']['code']}/group/price-policies", json={
            "price_floor_cents": 20000,
            "price_ceiling_cents": 40000,
            "room_type_id": d["rt1"]["id"],
        })
        r = client.post(f"/api/v1/tenants/{d['t']['code']}/price-calendar", json={
            "room_type_id": d["rt1"]["id"],
            "date": "2026-12-01",
            "price": 15000,
        })
        assert r.status_code == 403
        logs = client.get(f"/api/v1/tenants/{d['t']['code']}/audit-logs", params={"action": "group.price_block"}).json()
        assert len(logs) == 1
        assert logs[0]["result"] == "failure"

    def test_price_within_policy_allowed(self, client, multi_hotel_tenant):
        d = multi_hotel_tenant
        client.post(f"/api/v1/tenants/{d['t']['code']}/group/price-policies", json={
            "price_floor_cents": 20000,
            "price_ceiling_cents": 40000,
            "room_type_id": d["rt1"]["id"],
        })
        r = client.post(f"/api/v1/tenants/{d['t']['code']}/price-calendar", json={
            "room_type_id": d["rt1"]["id"],
            "date": "2026-12-01",
            "price": 30000,
        })
        assert r.status_code == 201
        assert r.json()["price"] == 30000


class TestHqDashboardAndSettlement:
    def test_hq_dashboard_revpar_ranking(self, client, multi_hotel_tenant):
        d = multi_hotel_tenant
        # 深圳店：营业日报
        bk1 = client.post(f"/api/v1/tenants/{d['t']['code']}/bookings", json={
            "hotel_id": d["h1"]["id"],
            "room_type_id": d["rt1"]["id"],
            "guest_name": "A",
            "check_in_date": "2026-12-01",
            "check_out_date": "2026-12-02",
            "room_no": "0101",
        }).json()
        client.post(f"/api/v1/tenants/{d['t']['code']}/bookings/{bk1['id']}/check-in", json={"room_no": "0101"})
        client.post(f"/api/v1/tenants/{d['t']['code']}/night-audit", json={
            "hotel_id": d["h1"]["id"],
            "business_date": "2026-12-01",
        })
        # 广州店：一间房卖 40000，RevPAR 必然更高
        bk2 = client.post(f"/api/v1/tenants/{d['t']['code']}/bookings", json={
            "hotel_id": d["h2"]["id"],
            "room_type_id": d["rt2"]["id"],
            "guest_name": "B",
            "check_in_date": "2026-12-01",
            "check_out_date": "2026-12-02",
            "room_no": "0201",
        }).json()
        client.post(f"/api/v1/tenants/{d['t']['code']}/bookings/{bk2['id']}/check-in", json={"room_no": "0201"})
        client.post(f"/api/v1/tenants/{d['t']['code']}/night-audit", json={
            "hotel_id": d["h2"]["id"],
            "business_date": "2026-12-01",
        })
        dash = client.get(f"/api/v1/tenants/{d['t']['code']}/group/dashboard").json()
        assert dash["hotel_count"] == 2
        assert dash["total_revenue"] > 0
        revpars = [h["revpar"] for h in dash["hotels"]]
        assert revpars == sorted(revpars, reverse=True)

    def test_settlement_split_pay_now_vs_prepaid(self, client, multi_hotel_tenant):
        d = multi_hotel_tenant
        bill = client.post(f"/api/v1/tenants/{d['t']['code']}/bills", json={
            "hotel_id": d["h1"]["id"],
            "guest_name": "结算客",
        }).json()
        client.post(f"/api/v1/tenants/{d['t']['code']}/bills/{bill['id']}/charges", json={
            "charge_type": "ROOM_CHARGE", "amount": 30000,
        })
        client.post(f"/api/v1/tenants/{d['t']['code']}/bills/{bill['id']}/payments", json={
            "method": "CASH", "amount": 10000,
        })
        client.post(f"/api/v1/tenants/{d['t']['code']}/bills/{bill['id']}/payments", json={
            "method": "WECHAT", "amount": 20000,
        })
        settle = client.get(f"/api/v1/tenants/{d['t']['code']}/group/settlement").json()
        h1 = next(r for r in settle["hotels"] if r["hotel_id"] == d["h1"]["id"])
        assert h1["pay_now_cents"] == 10000
        assert h1["prepaid_cents"] == 20000
        assert h1["total_cents"] == 30000
        assert settle["group"]["total_cents"] == 30000


class TestGroupPolicyEvents:
    def test_policy_issue_event_audited(self, client, multi_hotel_tenant):
        d = multi_hotel_tenant
        client.post(f"/api/v1/tenants/{d['t']['code']}/group/price-policies", json={
            "price_floor_cents": 10000,
            "price_ceiling_cents": 50000,
            "room_type_id": d["rt1"]["id"],
        })
        logs = client.get(f"/api/v1/tenants/{d['t']['code']}/audit-logs", params={"action": "group.policy_issue"}).json()
        assert len(logs) == 1
        assert logs[0]["resource_type"] == "group_price_policy"
