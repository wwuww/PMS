"""Sprint 9 测试：店长 App（M10）——经营看板（M10-1）与日报推送（M10-4）。

验证：房态盘汇总/在住/预抵/OCC；夜审后自动推送日报（未读→已读）；
看板待办提醒（超时工单/待审批/未读推送）。
"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    t = client.post("/api/v1/tenants", json={"code": "mgr1", "name": "看板测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[
            {"room_type_id": rt["id"], "room_no": "0701"},
            {"room_type_id": rt["id"], "room_no": "0702"},
        ],
    )
    # 1 间在住（今日应离 → 预离）
    bk = client.post(
        f"/api/v1/tenants/{t['code']}/bookings",
        json={
            "hotel_id": h["id"],
            "room_type_id": rt["id"],
            "guest_name": "在住客",
            "check_in_date": "2026-12-01",
            "check_out_date": "2026-12-02",
            "room_no": "0701",
        },
    ).json()
    client.post(f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-in", json={"room_no": "0701"})
    # 1 个预抵（created，12-02 到店）
    client.post(
        f"/api/v1/tenants/{t['code']}/bookings",
        json={
            "hotel_id": h["id"],
            "room_type_id": rt["id"],
            "guest_name": "预抵客",
            "check_in_date": "2026-12-02",
            "check_out_date": "2026-12-03",
        },
    )
    return {"t": t, "h": h, "rt": rt}


class TestDashboard:
    def test_dashboard_counts_and_lists(self, client: TestClient) -> None:
        d = _seed(client)
        dash = client.get(
            f"/api/v1/tenants/{d['t']['code']}/manager/dashboard",
            params={"hotel_id": d["h"]["id"], "business_date": "2026-12-01"},
        ).json()
        assert dash["rooms"]["total"] == 2
        assert dash["rooms"]["by_state"]["occupied"] == 1
        assert dash["occupancy_pct"] == 50
        assert dash["in_house"] == 1
        assert dash["latest_report"] is None  # 未夜审
        assert dash["alerts"] == {
            "overdue_tasks": 0,
            "pending_approvals": 0,
            "unread_notifications": 0,
        }
        # 预抵（12-02）
        dash2 = client.get(
            f"/api/v1/tenants/{d['t']['code']}/manager/dashboard",
            params={"hotel_id": d["h"]["id"], "business_date": "2026-12-02"},
        ).json()
        assert any(b["guest_name"] == "预抵客" for b in dash2["arrivals"])

    def test_dashboard_latest_report_and_alerts(self, client: TestClient) -> None:
        d = _seed(client)
        code = d["t"]["code"]
        # 超时工单（due_at 已过）+ 待审批
        client.post(
            f"/api/v1/tenants/{code}/housekeeping-tasks",
            json={"hotel_id": d["h"]["id"], "room_no": "0702", "due_at": "2026-01-01T00:00"},
        )
        client.post(
            f"/api/v1/tenants/{code}/approvals",
            json={
                "hotel_id": d["h"]["id"],
                "type": "OVERBOOK",
                "payload": {},
                "reason": "旺季超售申请",
                "applicant": "front_desk",
            },
        )
        # 夜审 → 日报 + 自动推送
        client.post(
            f"/api/v1/tenants/{code}/night-audit",
            json={"hotel_id": d["h"]["id"], "business_date": "2026-12-01"},
        )
        dash = client.get(
            f"/api/v1/tenants/{code}/manager/dashboard",
            params={"hotel_id": d["h"]["id"], "business_date": "2026-12-01"},
        ).json()
        assert dash["latest_report"] is not None
        assert dash["latest_report"]["business_date"] == "2026-12-01"
        assert dash["alerts"]["overdue_tasks"] == 1
        assert dash["alerts"]["pending_approvals"] == 1
        # ② 之后未读通知 = 日报 + 清扫工单 + 待审批 共 3 条（均经通知中心推送）
        assert dash["alerts"]["unread_notifications"] == 3


class TestNotification:
    def test_night_audit_pushes_report_and_mark_read(self, client: TestClient) -> None:
        d = _seed(client)
        code = d["t"]["code"]
        client.post(
            f"/api/v1/tenants/{code}/night-audit",
            json={"hotel_id": d["h"]["id"], "business_date": "2026-12-01"},
        )
        unread = client.get(
            f"/api/v1/tenants/{code}/notifications?hotel_id={d['h']['id']}&unread_only=true"
        ).json()
        assert len(unread) == 1
        n = unread[0]
        assert n["title"] == "营业日报 2026-12-01"
        assert n["ref_type"] == "daily_report"
        assert n["channel"] == "APP"
        assert "总营收" in n["body"]
        # 已读后不再出现在未读列表
        read = client.post(f"/api/v1/tenants/{code}/notifications/{n['id']}/read").json()
        assert read["read_at"] is not None
        unread_after = client.get(
            f"/api/v1/tenants/{code}/notifications?hotel_id={d['h']['id']}&unread_only=true"
        ).json()
        assert len(unread_after) == 0
        all_n = client.get(f"/api/v1/tenants/{code}/notifications").json()
        assert len(all_n) == 1

    def test_no_push_before_audit(self, client: TestClient) -> None:
        d = _seed(client)
        ns = client.get(f"/api/v1/tenants/{d['t']['code']}/notifications").json()
        assert ns == []
