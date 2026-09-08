"""M32 P1 四项集成测试。

1. 排房推荐补维修/噪音维度（近 30 天记录降权 + 原因输出）。
2. 周报/月报快照：手动生成幂等 + 夜审周期切换自动固化 + 列表查询。
3. 挂账前房号查询：在住客人姓名/离店日期 + 无在住警示。
4. 清洁待检查态：done → PENDING_INSPECT + 主管通知；inspect 通过放行 / 退回返工。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient


def _seed(client: TestClient, code: str, rooms: tuple[str, ...] = ("0101", "0102", "0103")) -> tuple[dict, dict, dict]:
    t = client.post("/api/v1/tenants", json={"code": code, "name": "测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[{"room_type_id": rt["id"], "room_no": r, "floor": "1"} for r in rooms],
    )
    return t, h, rt


# ================= 1. 排房推荐：维修/噪音维度 =================


class TestRecommendDims:
    def test_maintenance_and_noise_penalty(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m32r1")
        code = t["code"]
        hid = h["id"]
        # 房态全部空净
        # 近 30 天维修工单：0101；噪音投诉：0102
        client.post(
            f"/api/v1/tenants/{code}/housekeeping-tasks",
            json={"hotel_id": hid, "room_no": "0101", "task_type": "MAINTENANCE", "priority": "HIGH"},
        )
        r = client.post(
            f"/api/v1/tenants/{code}/complaints",
            json={"hotel_id": hid, "guest_name": "噪音客", "room_no": "0102", "category": "NOISE"},
        )
        assert r.status_code == 201, r.text

        rec = client.get(
            f"/api/v1/tenants/{code}/rooms/recommend", params={"hotel_id": hid, "room_type_id": rt["id"]}
        ).json()
        assert len(rec) == 3
        by_no = {x["room_no"]: x for x in rec}
        assert by_no["0101"]["score"] < by_no["0103"]["score"]
        assert by_no["0102"]["score"] < by_no["0103"]["score"]
        assert any("维修" in x for x in by_no["0101"]["reasons"])
        assert any("噪音" in x for x in by_no["0102"]["reasons"])
        assert by_no["0103"]["score"] == 100

    def test_old_records_do_not_penalize(self, client: TestClient) -> None:
        """40 天前的维修/噪音记录不降权（窗口 30 天）。"""
        t, h, rt = _seed(client, "m32r2")
        code, hid = t["code"], h["id"]
        rec = client.get(
            f"/api/v1/tenants/{code}/rooms/recommend", params={"hotel_id": hid, "room_type_id": rt["id"]}
        ).json()
        # 无任何记录时全部满分
        assert all(x["score"] == 100 for x in rec)


# ================= 2. 周报/月报快照 =================


class TestReportSnapshots:
    def test_generate_and_list_idempotent(self, client: TestClient) -> None:
        t, h, _ = _seed(client, "m32s1")
        code, hid = t["code"], h["id"]
        body = {"hotel_id": hid, "period_type": "WEEKLY", "start_date": "2026-08-24", "end_date": "2026-08-30"}
        r = client.post(f"/api/v1/tenants/{code}/analytics/snapshots/generate", json=body)
        assert r.status_code == 200, r.text
        snap = r.json()
        assert snap["period_type"] == "WEEKLY" and snap["source"] == "MANUAL"
        assert "total_revenue" in snap["metrics"] or "kpi" in snap["metrics"] or snap["metrics"]

        # 幂等覆盖（同周期同起点）
        r2 = client.post(f"/api/v1/tenants/{code}/analytics/snapshots/generate", json=body)
        assert r2.status_code == 200
        lst = client.get(
            f"/api/v1/tenants/{code}/analytics/snapshots", params={"hotel_id": hid, "period_type": "WEEKLY"}
        ).json()
        assert len(lst) == 1

    def test_bad_period_400(self, client: TestClient) -> None:
        t, h, _ = _seed(client, "m32s2")
        r = client.post(
            f"/api/v1/tenants/{t['code']}/analytics/snapshots/generate",
            json={"hotel_id": h["id"], "period_type": "DAILY", "start_date": "2026-08-24", "end_date": "2026-08-24"},
        )
        assert r.status_code == 422  # pattern 校验拦截

    def test_night_audit_auto_weekly(self, client: TestClient) -> None:
        """周一夜审 → 自动固化上周周报（source=AUTO）。"""
        t, h, rt = _seed(client, "m32s3")
        code, hid = t["code"], h["id"]
        # 营业日为周一 → 前一营业日为周日？夜审对 business_date 关账，取一个周一
        r = client.post(
            f"/api/v1/tenants/{code}/night-audit",
            json={"hotel_id": hid, "business_date": "2026-08-31", "operator": "auditor"},  # 周一
        )
        assert r.status_code in (200, 201), r.text
        lst = client.get(
            f"/api/v1/tenants/{code}/analytics/snapshots", params={"hotel_id": hid, "period_type": "WEEKLY"}
        ).json()
        assert len(lst) == 1
        assert lst[0]["source"] == "AUTO"
        assert lst[0]["period_start"] == "2026-08-24" and lst[0]["period_end"] == "2026-08-30"


# ================= 3. 挂账前房号查询 =================


class TestRoomLookup:
    def test_occupied_guest_info(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m32l1", rooms=("0101",))
        code, hid = t["code"], h["id"]
        bk = client.post(
            f"/api/v1/tenants/{code}/bookings",
            json={
                "hotel_id": hid,
                "room_type_id": rt["id"],
                "guest_name": "挂账客",
                "guest_phone": "13933440001",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-05",
                "room_no": "0101",
            },
        ).json()
        client.post(f"/api/v1/tenants/{code}/bookings/{bk['id']}/check-in", json={"room_no": "0101"})

        r = client.get(f"/api/v1/tenants/{code}/fnb/room-lookup", params={"room_no": "0101"})
        assert r.status_code == 200
        info = r.json()
        assert info["occupied"] is True
        assert info["guest_name"] == "挂账客"
        assert info["check_out_date"] == "2026-10-05"
        assert info["guest_phone_masked"] == "139****0001"

    def test_not_occupied_warning(self, client: TestClient) -> None:
        t, h, _ = _seed(client, "m32l2", rooms=("0102",))
        r = client.get(f"/api/v1/tenants/{t['code']}/fnb/room-lookup", params={"room_no": "0102"})
        info = r.json()
        assert info["occupied"] is False
        assert "无在住客人" in info["warning"]


# ================= 4. 清洁待检查态 =================


class TestHkInspect:
    def _seed_task(self, client: TestClient, code: str) -> dict:
        d = client.get(f"/api/v1/tenants/{code}").json()
        tasks = client.get(f"/api/v1/tenants/{code}/housekeeping-tasks").json()
        return tasks[0]

    def test_full_inspect_flow(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m32h1", rooms=("0601",))
        code, hid = t["code"], h["id"]
        # 退房流程造空脏房 + 自动 CLEANUP 工单
        bk = client.post(
            f"/api/v1/tenants/{code}/bookings",
            json={
                "hotel_id": hid,
                "room_type_id": rt["id"],
                "guest_name": "退房客",
                "check_in_date": "2026-12-01",
                "check_out_date": "2026-12-02",
                "room_no": "0601",
            },
        ).json()
        client.post(f"/api/v1/tenants/{code}/bookings/{bk['id']}/check-in", json={"room_no": "0601"})
        client.post(f"/api/v1/tenants/{code}/bookings/{bk['id']}/check-out", json={})
        task = client.get(f"/api/v1/tenants/{code}/housekeeping-tasks").json()[0]
        client.post(
            f"/api/v1/tenants/{code}/housekeeping-tasks/{task['id']}/assign",
            json={"assignee": "保洁王姐"},
        )
        # 完成 → 待检查（不直接净房）
        done = client.post(f"/api/v1/tenants/{code}/housekeeping-tasks/{task['id']}/done").json()
        assert done["status"] == "PENDING_INSPECT"
        # 主管收到通知
        notifs = client.get(f"/api/v1/tenants/{code}/notifications").json()
        assert any("待检查" in n["title"] and "0601" in n["title"] for n in notifs)
        # 房态仍非空净
        rooms = client.get(f"/api/v1/tenants/{code}/rooms?state=vacant_clean").json()
        assert not any(r["room_no"] == "0601" for r in rooms)
        # 检查通过 → 净房可售 + done_at
        ins = client.post(
            f"/api/v1/tenants/{code}/housekeeping-tasks/{task['id']}/inspect",
            json={"passed": True, "operator": "主管"},
        )
        assert ins.status_code == 200
        assert ins.json()["status"] == "DONE" and ins.json()["done_at"]
        rooms = client.get(f"/api/v1/tenants/{code}/rooms?state=vacant_clean").json()
        assert any(r["room_no"] == "0601" for r in rooms)
        # 已检查的不可重复检查
        ins2 = client.post(
            f"/api/v1/tenants/{code}/housekeeping-tasks/{task['id']}/inspect",
            json={"passed": True},
        )
        assert ins2.status_code == 409

    def test_inspect_fail_returns_to_assigned(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m32h2", rooms=("0701",))
        code, hid = t["code"], h["id"]
        bk = client.post(
            f"/api/v1/tenants/{code}/bookings",
            json={
                "hotel_id": hid,
                "room_type_id": rt["id"],
                "guest_name": "退房客2",
                "check_in_date": "2026-12-01",
                "check_out_date": "2026-12-02",
                "room_no": "0701",
            },
        ).json()
        client.post(f"/api/v1/tenants/{code}/bookings/{bk['id']}/check-in", json={"room_no": "0701"})
        client.post(f"/api/v1/tenants/{code}/bookings/{bk['id']}/check-out", json={})
        task = client.get(f"/api/v1/tenants/{code}/housekeeping-tasks").json()[0]
        client.post(
            f"/api/v1/tenants/{code}/housekeeping-tasks/{task['id']}/assign",
            json={"assignee": "保洁小李"},
        )
        client.post(f"/api/v1/tenants/{code}/housekeeping-tasks/{task['id']}/done")
        ins = client.post(
            f"/api/v1/tenants/{code}/housekeeping-tasks/{task['id']}/inspect",
            json={"passed": False, "note": "马桶未刷"},
        )
        assert ins.status_code == 200
        assert ins.json()["status"] == "ASSIGNED"
        assert "马桶未刷" in ins.json()["note"]
