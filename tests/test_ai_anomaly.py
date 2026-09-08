"""Sprint 11：M12 AI 自动对账预警测试。"""

import pytest


@pytest.fixture
def env(client):
    t = client.post("/api/v1/tenants", json={"code": "ai12", "name": "AI 对账测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "HZ", "name": "杭州店"}).json()
    rt = client.post(f"/api/v1/tenants/{t['id']}/room-types", json={"code": "STD", "name": "标间", "base_price": 20000}).json()
    client.post(f"/api/v1/hotels/{h['id']}/rooms", json=[{"room_type_id": rt["id"], "room_no": "301"}])
    return {"t": t, "h": h, "rt": rt}


class TestAnomalyDetection:
    def test_zero_amount_charge_triggers_alert(self, client, env):
        bill = client.post(
            f"/api/v1/tenants/{env['t']['code']}/bills",
            json={"hotel_id": env["h"]["id"], "guest_name": "异常客"},
        ).json()
        client.post(
            f"/api/v1/tenants/{env['t']['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "ROOM_CHARGE", "amount": -1000},
        )
        # 入住触发夜审
        bk = client.post(f"/api/v1/tenants/{env['t']['code']}/bookings", json={
            "hotel_id": env["h"]["id"], "room_type_id": env["rt"]["id"], "guest_name": "住客",
            "check_in_date": "2026-12-01", "check_out_date": "2026-12-02", "room_no": "301",
        }).json()
        client.post(f"/api/v1/tenants/{env['t']['code']}/bookings/{bk['id']}/check-in", json={"room_no": "301"})
        client.post(f"/api/v1/tenants/{env['t']['code']}/night-audit", json={
            "hotel_id": env["h"]["id"], "business_date": "2026-12-01",
        })
        alerts = client.get(
            f"/api/v1/tenants/{env['t']['code']}/ai/alerts",
            params={"hotel_id": env["h"]["id"]},
        ).json()
        amount_alerts = [a for a in alerts if a["alert_type"] == "amount_anomaly"]
        assert len(amount_alerts) >= 1
        assert amount_alerts[0]["severity"] == "critical"

    def test_scan_pushes_alert_notification(self, client, env):
        """② 夜审扫描出预警即同步推送到通知中心（点击深链直达预警详情）。"""
        bill = client.post(
            f"/api/v1/tenants/{env['t']['code']}/bills",
            json={"hotel_id": env["h"]["id"], "guest_name": "异常客"},
        ).json()
        client.post(
            f"/api/v1/tenants/{env['t']['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "ROOM_CHARGE", "amount": -1000},
        )
        bk = client.post(f"/api/v1/tenants/{env['t']['code']}/bookings", json={
            "hotel_id": env["h"]["id"], "room_type_id": env["rt"]["id"], "guest_name": "住客",
            "check_in_date": "2026-12-01", "check_out_date": "2026-12-02", "room_no": "301",
        }).json()
        client.post(f"/api/v1/tenants/{env['t']['code']}/bookings/{bk['id']}/check-in", json={"room_no": "301"})
        client.post(f"/api/v1/tenants/{env['t']['code']}/night-audit", json={
            "hotel_id": env["h"]["id"], "business_date": "2026-12-01",
        })
        notifs = client.get(
            f"/api/v1/tenants/{env['t']['code']}/notifications"
        ).json()
        alert_notifs = [n for n in notifs if n["ref_type"] == "alert"]
        assert len(alert_notifs) >= 1
        assert alert_notifs[0]["link"].startswith("/alerts?alert=")

    def test_duplicate_payment_triggers_alert(self, client, env):
        bill = client.post(
            f"/api/v1/tenants/{env['t']['code']}/bills",
            json={"hotel_id": env["h"]["id"], "guest_name": "重复客"},
        ).json()
        client.post(f"/api/v1/tenants/{env['t']['code']}/bills/{bill['id']}/charges", json={"charge_type": "ROOM_CHARGE", "amount": 30000})
        client.post(f"/api/v1/tenants/{env['t']['code']}/bills/{bill['id']}/payments", json={"method": "CASH", "amount": 30000})
        client.post(f"/api/v1/tenants/{env['t']['code']}/bills/{bill['id']}/payments", json={"method": "CASH", "amount": 30000})
        bk = client.post(f"/api/v1/tenants/{env['t']['code']}/bookings", json={
            "hotel_id": env["h"]["id"], "room_type_id": env["rt"]["id"], "guest_name": "住客2",
            "check_in_date": "2026-12-01", "check_out_date": "2026-12-02", "room_no": "301",
        }).json()
        client.post(f"/api/v1/tenants/{env['t']['code']}/bookings/{bk['id']}/check-in", json={"room_no": "301"})
        client.post(f"/api/v1/tenants/{env['t']['code']}/night-audit", json={
            "hotel_id": env["h"]["id"], "business_date": "2026-12-01",
        })
        alerts = client.get(
            f"/api/v1/tenants/{env['t']['code']}/ai/alerts",
            params={"hotel_id": env["h"]["id"]},
        ).json()
        dup = [a for a in alerts if a["alert_type"] == "duplicate_payment"]
        assert len(dup) >= 1

    def test_acknowledge_and_resolve_alert(self, client, env):
        bill = client.post(
            f"/api/v1/tenants/{env['t']['code']}/bills",
            json={"hotel_id": env["h"]["id"], "guest_name": "异常客"},
        ).json()
        client.post(f"/api/v1/tenants/{env['t']['code']}/bills/{bill['id']}/charges", json={"charge_type": "ROOM_CHARGE", "amount": -1000})
        bk = client.post(f"/api/v1/tenants/{env['t']['code']}/bookings", json={
            "hotel_id": env["h"]["id"], "room_type_id": env["rt"]["id"], "guest_name": "住客",
            "check_in_date": "2026-12-01", "check_out_date": "2026-12-02", "room_no": "301",
        }).json()
        client.post(f"/api/v1/tenants/{env['t']['code']}/bookings/{bk['id']}/check-in", json={"room_no": "301"})
        client.post(f"/api/v1/tenants/{env['t']['code']}/night-audit", json={
            "hotel_id": env["h"]["id"], "business_date": "2026-12-01",
        })
        alerts = client.get(
            f"/api/v1/tenants/{env['t']['code']}/ai/alerts",
            params={"hotel_id": env["h"]["id"]},
        ).json()
        alert = [a for a in alerts if a["alert_type"] == "amount_anomaly"][0]
        ack = client.post(f"/api/v1/tenants/{env['t']['code']}/ai/alerts/{alert['id']}/acknowledge").json()
        assert ack["status"] == "acknowledged"
        resolved = client.post(f"/api/v1/tenants/{env['t']['code']}/ai/alerts/{alert['id']}/resolve").json()
        assert resolved["status"] == "resolved"
