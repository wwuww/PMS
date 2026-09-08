"""Sprint 9 测试：店长 App（M10）——清扫工单（M10-3，FR-APP-03 / FR-FT-04）。

验证：退房自动建 CLEANUP 工单（AUTO_CHECKOUT）；派单 → 完成联动房态 空脏→空净。
"""

from fastapi.testclient import TestClient


def _seed_and_checkout(client: TestClient) -> dict:
    t = client.post("/api/v1/tenants", json={"code": "hk1", "name": "工单测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(f"/api/v1/hotels/{h['id']}/rooms", json=[{"room_type_id": rt["id"], "room_no": "0601"}])
    bk = client.post(
        f"/api/v1/tenants/{t['code']}/bookings",
        json={
            "hotel_id": h["id"],
            "room_type_id": rt["id"],
            "guest_name": "退房客",
            "check_in_date": "2026-12-01",
            "check_out_date": "2026-12-02",
            "room_no": "0601",
        },
    ).json()
    client.post(f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-in", json={"room_no": "0601"})
    client.post(f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-out", json={})
    return {"t": t, "h": h, "rt": rt, "bk": bk}


class TestHousekeeping:
    def test_checkout_auto_creates_cleanup(self, client: TestClient) -> None:
        d = _seed_and_checkout(client)
        tasks = client.get(
            f"/api/v1/tenants/{d['t']['code']}/housekeeping-tasks?hotel_id={d['h']['id']}"
        ).json()
        assert len(tasks) == 1
        task = tasks[0]
        assert task["task_type"] == "CLEANUP"
        assert task["status"] == "PENDING"
        assert task["source"] == "AUTO_CHECKOUT"
        assert task["room_no"] == "0601"
        # 退房后房态为空脏
        rooms = client.get(f"/api/v1/tenants/{d['t']['code']}/rooms?state=vacant_dirty").json()
        assert any(r["room_no"] == "0601" for r in rooms)

    def test_assign_and_done_restores_clean(self, client: TestClient) -> None:
        d = _seed_and_checkout(client)
        code = d["t"]["code"]
        tasks = client.get(f"/api/v1/tenants/{code}/housekeeping-tasks").json()
        task_id = tasks[0]["id"]
        assigned = client.post(
            f"/api/v1/tenants/{code}/housekeeping-tasks/{task_id}/assign",
            json={"assignee": "保洁王姐"},
        ).json()
        assert assigned["status"] == "ASSIGNED"
        assert assigned["assignee"] == "保洁王姐"
        # M32：保洁完成 → 待检查（房态仍空脏，不直接可售），并通知主管
        done = client.post(f"/api/v1/tenants/{code}/housekeeping-tasks/{task_id}/done").json()
        assert done["status"] == "PENDING_INSPECT"
        rooms = client.get(f"/api/v1/tenants/{code}/rooms?state=vacant_clean").json()
        assert not any(r["room_no"] == "0601" for r in rooms)
        notifs = client.get(f"/api/v1/tenants/{code}/notifications").json()
        assert any("待检查" in n["title"] for n in notifs)
        # 主管检查通过 → DONE + 空净可售（验收 #39）
        ins = client.post(
            f"/api/v1/tenants/{code}/housekeeping-tasks/{task_id}/inspect",
            json={"passed": True, "operator": "主管老李"},
        )
        assert ins.status_code == 200, ins.text
        assert ins.json()["status"] == "DONE" and ins.json()["done_at"]
        rooms = client.get(f"/api/v1/tenants/{code}/rooms?state=vacant_clean").json()
        assert any(r["room_no"] == "0601" for r in rooms)

    def test_checkout_pushes_task_notification(self, client: TestClient) -> None:
        """② 退房自动建清扫工单即向通知中心推送（点击深链直达工单）。"""
        d = _seed_and_checkout(client)
        code = d["t"]["code"]
        task_id = client.get(f"/api/v1/tenants/{code}/housekeeping-tasks").json()[0]["id"]
        notifs = client.get(f"/api/v1/tenants/{code}/notifications").json()
        tasks = [n for n in notifs if n["ref_type"] == "task"]
        assert len(tasks) == 1
        n = tasks[0]
        assert n["ref_id"] == str(task_id)
        assert n["link"] == f"/housekeeping?task={task_id}"
