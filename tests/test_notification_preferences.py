"""③ 通知分级 / 免打扰（M10-4 增强）。

覆盖：
1. 各业务推送点落正确的 level（审批=normal、收益建议=info、风险预警=critical）；
2. 免打扰开启且处于安静时段时，非 critical 通知被静音（muted=True）且不计入未读角标；
3. critical（风险预警）突破免打扰，仍非静音且计入未读角标；
4. 免打扰偏好 GET 默认 / PUT 写入 / GET 回读。
"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    t = client.post("/api/v1/tenants", json={"code": "dnd1", "name": "免打扰测试"}).json()
    h = client.post(
        f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}
    ).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(f"/api/v1/hotels/{h['id']}/rooms", json=[{"room_type_id": rt["id"], "room_no": "301"}])
    return {"t": t, "h": h, "rt": rt}


def _set_pref(client: TestClient, code: str, **body: object) -> None:
    client.put(f"/api/v1/tenants/{code}/notification-preferences", json=body)


class TestNotificationGradingDnd:
    def test_push_levels(self, client: TestClient) -> None:
        """② 各推送点 level 正确落库。"""
        d = _seed(client)
        code = d["t"]["code"]
        client.post(
            f"/api/v1/tenants/{code}/approvals",
            json={"hotel_id": d["h"]["id"], "type": "OVERBOOK", "payload": {},
                  "reason": "旺季超售", "applicant": "fd"},
        )
        client.post(
            f"/api/v1/tenants/{code}/yield/pricing/recommend",
            json={"hotel_id": d["h"]["id"], "business_date": "2026-09-10",
                  "base_price_cents": 30000},
        )
        notifs = client.get(f"/api/v1/tenants/{code}/notifications").json()
        levels = {n["ref_type"]: n["level"] for n in notifs}
        assert levels.get("approval") == "normal"
        assert levels.get("yield_recommendation") == "info"

    def test_dnd_mutes_non_critical(self, client: TestClient) -> None:
        """免打扰开启（时段覆盖全天）时，normal 通知被静音且不计入未读角标。"""
        d = _seed(client)
        code = d["t"]["code"]
        _set_pref(client, code, dnd_enabled=True, dnd_start="00:00", dnd_end="23:59")
        client.post(
            f"/api/v1/tenants/{code}/approvals",
            json={"hotel_id": d["h"]["id"], "type": "OVERBOOK", "payload": {},
                  "reason": "x", "applicant": "fd"},
        )
        notifs = client.get(f"/api/v1/tenants/{code}/notifications").json()
        approval = [n for n in notifs if n["ref_type"] == "approval"][0]
        assert approval["muted"] is True
        assert approval["level"] == "normal"
        # 未读角标应排除被静音项
        cnt = client.get(f"/api/v1/tenants/{code}/notifications/unread-count").json()["unread"]
        assert cnt == 0

    def test_critical_breaks_through_dnd(self, client: TestClient) -> None:
        """免打扰开启时，critical 风险预警仍触达（非静音且计入未读角标）。"""
        d = _seed(client)
        code = d["t"]["code"]
        _set_pref(client, code, dnd_enabled=True, dnd_start="00:00", dnd_end="23:59")
        # 制造金额异常 → 夜审扫描出 critical 预警
        bill = client.post(
            f"/api/v1/tenants/{code}/bills",
            json={"hotel_id": d["h"]["id"], "guest_name": "异常客"},
        ).json()
        client.post(
            f"/api/v1/tenants/{code}/bills/{bill['id']}/charges",
            json={"charge_type": "ROOM_CHARGE", "amount": -1000},
        )
        bk = client.post(f"/api/v1/tenants/{code}/bookings", json={
            "hotel_id": d["h"]["id"], "room_type_id": d["rt"]["id"], "guest_name": "住客",
            "check_in_date": "2026-12-01", "check_out_date": "2026-12-02", "room_no": "301",
        }).json()
        client.post(f"/api/v1/tenants/{code}/bookings/{bk['id']}/check-in", json={"room_no": "301"})
        client.post(f"/api/v1/tenants/{code}/night-audit", json={
            "hotel_id": d["h"]["id"], "business_date": "2026-12-01",
        })
        notifs = client.get(f"/api/v1/tenants/{code}/notifications").json()
        alerts = [n for n in notifs if n["ref_type"] == "alert"]
        assert alerts
        assert all(a["muted"] is False for a in alerts)
        assert all(a["level"] == "critical" for a in alerts)
        cnt = client.get(f"/api/v1/tenants/{code}/notifications/unread-count").json()["unread"]
        assert cnt >= 1  # 仅 critical 突破免打扰计入角标

    def test_preferences_default_and_put(self, client: TestClient) -> None:
        """无记录 GET 返回默认；PUT 写入后 GET 回读一致。"""
        d = _seed(client)
        code = d["t"]["code"]
        r = client.get(f"/api/v1/tenants/{code}/notification-preferences").json()
        assert r["dnd_enabled"] is False
        assert r["dnd_start"] == "22:00"
        assert r["dnd_end"] == "08:00"

        r2 = client.put(
            f"/api/v1/tenants/{code}/notification-preferences",
            json={"dnd_enabled": True, "dnd_start": "23:00", "dnd_end": "07:00"},
        ).json()
        assert r2["dnd_enabled"] is True
        assert r2["dnd_start"] == "23:00"
        assert r2["dnd_end"] == "07:00"

        r3 = client.get(f"/api/v1/tenants/{code}/notification-preferences").json()
        assert r3["dnd_enabled"] is True
        assert r3["dnd_end"] == "07:00"
