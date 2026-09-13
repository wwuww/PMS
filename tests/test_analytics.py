"""Sprint 12：数据中台/经营分析 M16（FR-RP）测试。"""

import uuid

import pytest


@pytest.fixture
def analytics_tenant(client):
    """创建一个含两店、两种房型、若干房间的租户，并产生营业数据。"""
    code = f"anlz{uuid.uuid4().hex[:8]}"
    t = client.post("/api/v1/tenants", json={"code": code, "name": "分析测试租户"}).json()
    h1 = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H1", "name": "深圳店"}).json()
    h2 = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H2", "name": "广州店"}).json()
    # D1（M0 多店）：房型显式归属门店
    rt1 = client.post(f"/api/v1/tenants/{t['id']}/room-types", json={"code": "STD", "name": "标准间", "base_price": 30000, "hotel_id": h1["id"]}).json()
    rt2 = client.post(f"/api/v1/tenants/{t['id']}/room-types", json={"code": "DLX", "name": "豪华间", "base_price": 40000, "hotel_id": h2["id"]}).json()
    client.post(f"/api/v1/hotels/{h1['id']}/rooms", json=[
        {"room_type_id": rt1["id"], "room_no": "0101"},
        {"room_type_id": rt1["id"], "room_no": "0102"},
    ])
    client.post(f"/api/v1/hotels/{h2['id']}/rooms", json=[
        {"room_type_id": rt2["id"], "room_no": "0201"},
    ])

    # 深圳店：标准间 1 间夜
    bk1 = client.post(f"/api/v1/tenants/{code}/bookings", json={
        "hotel_id": h1["id"],
        "room_type_id": rt1["id"],
        "guest_name": "A",
        "check_in_date": "2026-12-01",
        "check_out_date": "2026-12-02",
        "channel": "direct",
        "room_no": "0101",
    }).json()
    client.post(f"/api/v1/tenants/{code}/bookings/{bk1['id']}/check-in", json={"room_no": "0101"})
    client.post(f"/api/v1/tenants/{code}/night-audit", json={"hotel_id": h1["id"], "business_date": "2026-12-01"})

    # 广州店：豪华间 1 间夜，渠道携程
    bk2 = client.post(f"/api/v1/tenants/{code}/bookings", json={
        "hotel_id": h2["id"],
        "room_type_id": rt2["id"],
        "guest_name": "B",
        "check_in_date": "2026-12-01",
        "check_out_date": "2026-12-02",
        "channel": "ctrip",
        "room_no": "0201",
    }).json()
    client.post(f"/api/v1/tenants/{code}/bookings/{bk2['id']}/check-in", json={"room_no": "0201"})
    client.post(f"/api/v1/tenants/{code}/night-audit", json={"hotel_id": h2["id"], "business_date": "2026-12-01"})

    return {"t": t, "h1": h1, "h2": h2, "rt1": rt1, "rt2": rt2, "code": code}


class TestAnalyticsDashboard:
    def test_dashboard_kpis(self, client, analytics_tenant):
        d = analytics_tenant
        r = client.get(f"/api/v1/tenants/{d['code']}/analytics/dashboard", params={
            "hotel_id": d["h1"]["id"],
            "start_date": "2026-12-01",
            "end_date": "2026-12-01",
        }).json()
        assert r["hotel_id"] == d["h1"]["id"]
        assert r["total_rooms"] == 2
        assert r["occupied_room_nights"] == 1
        assert r["room_revenue_cents"] > 0
        assert r["revpar_cents"] == r["room_revenue_cents"] // 2
        assert r["adr_cents"] == r["room_revenue_cents"]
        assert r["occ_pct_bps"] == 5000  # 1/2 = 50.00%
        assert len(r["daily_series"]) == 1

    def test_dashboard_empty_range(self, client, analytics_tenant):
        d = analytics_tenant
        r = client.get(f"/api/v1/tenants/{d['code']}/analytics/dashboard", params={
            "hotel_id": d["h1"]["id"],
            "start_date": "2026-11-01",
            "end_date": "2026-11-30",
        }).json()
        assert r["days"] == 0
        assert r["total_revenue_cents"] == 0


class TestAnalyticsRanking:
    def test_hotel_ranking_revpar(self, client, analytics_tenant):
        d = analytics_tenant
        r = client.get(f"/api/v1/tenants/{d['code']}/analytics/hotel-ranking", params={
            "start_date": "2026-12-01",
            "end_date": "2026-12-01",
        }).json()
        assert r["hotel_count"] == 2
        revpars = [h["revpar_cents"] for h in r["hotels"]]
        assert revpars == sorted(revpars, reverse=True)
        # 广州店只有 1 间房，豪华间房价高，RevPAR 应高于深圳店
        assert r["hotels"][0]["name"] == "广州店"


class TestAnalyticsChannelRevenue:
    def test_channel_revenue_split(self, client, analytics_tenant):
        d = analytics_tenant
        r = client.get(f"/api/v1/tenants/{d['code']}/analytics/channel-revenue", params={
            "hotel_id": d["h1"]["id"],
            "start_date": "2026-12-01",
            "end_date": "2026-12-01",
        }).json()
        assert r["total_bookings"] == 1
        channels = {c["channel"]: c for c in r["channels"]}
        assert "direct" in channels
        assert channels["direct"]["booking_count"] == 1
        assert channels["direct"]["room_revenue_cents"] > 0


class TestAnalyticsRoomTypeRevenue:
    def test_room_type_revenue(self, client, analytics_tenant):
        d = analytics_tenant
        r = client.get(f"/api/v1/tenants/{d['code']}/analytics/room-type-revenue", params={
            "hotel_id": d["h1"]["id"],
            "start_date": "2026-12-01",
            "end_date": "2026-12-01",
        }).json()
        assert r["total_bookings"] == 1
        assert len(r["room_types"]) == 1
        assert r["room_types"][0]["room_type_name"] == "标准间"
        assert r["room_types"][0]["room_revenue_cents"] > 0


class TestAnalyticsPaymentSummary:
    def test_payment_summary_by_method(self, client, analytics_tenant):
        d = analytics_tenant
        bill = client.post(f"/api/v1/tenants/{d['code']}/bills", json={
            "hotel_id": d["h1"]["id"],
            "guest_name": "收银客",
        }).json()
        client.post(f"/api/v1/tenants/{d['code']}/bills/{bill['id']}/charges", json={
            "charge_type": "ROOM_CHARGE", "amount": 30000,
        })
        client.post(f"/api/v1/tenants/{d['code']}/bills/{bill['id']}/payments", json={
            "method": "CASH", "amount": 10000,
        })
        client.post(f"/api/v1/tenants/{d['code']}/bills/{bill['id']}/payments", json={
            "method": "WECHAT", "amount": 20000,
        })
        r = client.get(f"/api/v1/tenants/{d['code']}/analytics/payment-summary", params={
            "hotel_id": d["h1"]["id"],
        }).json()
        methods = {m["method"]: m["amount_cents"] for m in r["methods"]}
        assert methods.get("CASH") == 10000
        assert methods.get("WECHAT") == 20000
        assert r["total_cents"] == 30000


class TestAnalyticsExport:
    def test_export_json_hotel_ranking(self, client, analytics_tenant):
        d = analytics_tenant
        r = client.get(f"/api/v1/tenants/{d['code']}/analytics/export", params={
            "report_type": "hotel_ranking",
            "start_date": "2026-12-01",
            "end_date": "2026-12-01",
            "format": "json",
        }).json()
        assert "hotels" in r
        assert len(r["hotels"]) == 2

    def test_export_csv_channel_revenue(self, client, analytics_tenant):
        d = analytics_tenant
        r = client.get(f"/api/v1/tenants/{d['code']}/analytics/export", params={
            "report_type": "channel_revenue",
            "hotel_id": d["h1"]["id"],
            "start_date": "2026-12-01",
            "end_date": "2026-12-01",
            "format": "csv",
        }).json()
        assert r["format"] == "csv"
        assert r["header"] == ["channel", "booking_count", "room_revenue_cents"]
        assert len(r["rows"]) == 1
