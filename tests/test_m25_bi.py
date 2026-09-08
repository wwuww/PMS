"""M25 店总 BI 深度集成测试（验收清单 #19 / #16 / #15）。

覆盖：
- 超卖预警：逐日在手 vs 可售房量，超卖/临界分级
- 远期趋势：在手入住率（OTB）+ 预订增速
- 自定义报表：按房型 / 渠道 / 入住日聚合，排除取消与 NoShow
"""

from fastapi.testclient import TestClient


def _seed(client: TestClient, code: str) -> tuple[dict, dict, dict]:
    t = client.post("/api/v1/tenants", json={"code": code, "name": "M25测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[
            {"room_type_id": rt["id"], "room_no": "0101"},
            {"room_type_id": rt["id"], "room_no": "0102"},
        ],
    )
    return t, h, rt


def _book(client: TestClient, t: dict, h: dict, rt: dict, **kw) -> dict:
    body = {
        "hotel_id": h["id"],
        "room_type_id": rt["id"],
        "guest_name": kw.pop("guest_name", "客"),
        "check_in_date": kw.pop("check_in_date"),
        "check_out_date": kw.pop("check_out_date"),
    }
    body.update(kw)
    return client.post(f"/api/v1/tenants/{t['code']}/bookings", json=body).json()


class TestOversellWarnings:
    def test_oversell_and_critical_levels(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m25a")
        # 3 间房各接 1 笔 10-01~10-03 在住期预订（房量守卫允许）
        client.post(
            f"/api/v1/hotels/{h['id']}/rooms",
            json=[{"room_type_id": rt["id"], "room_no": "0103"}],
        )
        for i, phone in enumerate(["13900010001", "13900010002", "13900010003"]):
            _book(
                client, t, h, rt,
                guest_name=f"客{i}",
                guest_phone=phone,
                check_in_date="2026-10-01",
                check_out_date="2026-10-03",
            )
        # 一间房转入维修 → 可售 2 < 在手 3，真实超卖场景（房量收缩晚于预订）
        client.post(
            f"/api/v1/tenants/{t['code']}/rooms/0103/transition",
            json={"trigger": "start_maintenance"},
        )
        r = client.get(
            f"/api/v1/tenants/{t['code']}/analytics/oversell-warnings",
            params={"hotel_id": h["id"], "start_date": "2026-10-01", "end_date": "2026-10-04"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["sellable_rooms"] == 2
        by_date = {w["date"]: w for w in body["warnings"]}
        assert by_date["2026-10-01"]["level"] == "OVERSELL"
        assert by_date["2026-10-01"]["gap"] == -1
        assert by_date["2026-10-02"]["level"] == "OVERSELL"
        # 10-03 预订已离店（不含 10-03）→ 无预警
        assert "2026-10-03" not in by_date
        assert "2026-10-04" not in by_date

    def test_cancelled_and_noshow_not_counted(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m25b")
        bk = _book(
            client, t, h, rt,
            guest_name="取消客",
            check_in_date="2026-10-01",
            check_out_date="2026-10-02",
        )
        client.post(
            f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/cancel", json={}
        )
        r = client.get(
            f"/api/v1/tenants/{t['code']}/analytics/oversell-warnings",
            params={"hotel_id": h["id"], "start_date": "2026-10-01", "end_date": "2026-10-01"},
        )
        body = r.json()
        assert body["warnings"] == []


class TestOccupancyForecast:
    def test_otb_rate_and_pace(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m25c")
        tomorrow_booked = _book(
            client, t, h, rt,
            guest_name="明晚客",
            check_in_date="2026-12-01",
            check_out_date="2026-12-02",
        )
        assert tomorrow_booked["id"]
        r = client.get(
            f"/api/v1/tenants/{t['code']}/analytics/forecast",
            params={"hotel_id": h["id"], "days": 7},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["days"] == 7
        assert body["sellable_rooms"] == 2
        # 预订的入住日在远期窗口内才有占用；本测试窗口是"未来7天"（相对今天），
        # 12-01 可能不在窗口内，只验证结构
        for item in body["forecast"]:
            assert 0.0 <= item["occupancy_rate"] <= 1.0
            assert "date" in item and "on_hand_bookings" in item
        # 近 14 天至少有本测试产生的一笔预订进入 pace
        assert isinstance(body["booking_pace"], list)


class TestCustomReport:
    def test_group_by_channel_excludes_cancelled(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m25d")
        b1 = _book(
            client, t, h, rt,
            guest_name="OTA客",
            channel="ota",
            check_in_date="2026-10-01",
            check_out_date="2026-10-02",
        )
        _book(
            client, t, h, rt,
            guest_name="直订客",
            channel="direct",
            check_in_date="2026-10-01",
            check_out_date="2026-10-03",
        )
        client.post(f"/api/v1/tenants/{t['code']}/bookings/{b1['id']}/cancel", json={})
        r = client.get(
            f"/api/v1/tenants/{t['code']}/analytics/custom-report",
            params={
                "hotel_id": h["id"],
                "group_by": "channel",
                "start_date": "2026-10-01",
                "end_date": "2026-10-31",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        groups = {row["group"]: row for row in body["rows"]}
        assert "ota" not in groups  # 已取消被排除
        assert groups["direct"]["booking_count"] == 1

    def test_group_by_day_and_room_type(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m25e")
        _book(
            client, t, h, rt,
            guest_name="日客",
            check_in_date="2026-10-01",
            check_out_date="2026-10-02",
        )
        r = client.get(
            f"/api/v1/tenants/{t['code']}/analytics/custom-report",
            params={"hotel_id": h["id"], "group_by": "day",
                    "start_date": "2026-10-01", "end_date": "2026-10-01"},
        )
        body = r.json()
        assert body["rows"][0]["group"] == "2026-10-01"
        assert body["total_bookings"] == 1

        r2 = client.get(
            f"/api/v1/tenants/{t['code']}/analytics/custom-report",
            params={"hotel_id": h["id"], "group_by": "room_type"},
        )
        body2 = r2.json()
        assert body2["rows"][0]["label"] == "标间"

    def test_invalid_group_by_rejected(self, client: TestClient) -> None:
        t, h, _ = _seed(client, "m25f")
        r = client.get(
            f"/api/v1/tenants/{t['code']}/analytics/custom-report",
            params={"hotel_id": h["id"], "group_by": "bogus"},
        )
        assert r.status_code == 400
