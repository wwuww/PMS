"""钟点房入住测试（M32.17）：不占用当天过夜房可售房量。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    tenant = client.post(
        "/api/v1/tenants", json={"code": "t-hourly", "name": "钟点房测试"}
    ).json()
    hotel = client.post(
        f"/api/v1/tenants/{tenant['id']}/hotels", json={"code": "H1", "name": "店"}
    ).json()
    rt = client.post(
        f"/api/v1/tenants/{tenant['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000, "hourly_rate": 5000},
    ).json()
    client.post(
        f"/api/v1/hotels/{hotel['id']}/rooms",
        json=[
            {"room_type_id": rt["id"], "room_no": "0101"},
            {"room_type_id": rt["id"], "room_no": "0102"},
        ],
    )
    return {"tenant": tenant, "hotel": hotel, "rt": rt}


def _avail(client: TestClient, code: str, rtid: int, date: str) -> int:
    r = client.get(f"/api/v1/tenants/{code}/room-types/{rtid}/availability", params={"date": date})
    assert r.status_code == 200, r.text
    return r.json()["available"]


def _walk_in(client: TestClient, code: str, s: dict, room_no: str, guest: str, *, hourly: int | None = None) -> dict:
    today = "2026-10-01"
    body: dict = {
        "room_no": room_no,
        "room_type_id": int(s["rt"]["id"]),
        "guest_name": guest,
        "check_in_date": today,
        "check_out_date": today if hourly else "2026-10-02",
        "operator": "front_desk",
    }
    if hourly:
        body["stay_type"] = "hourly"
        body["hourly_hours"] = hourly
    r = client.post(f"/api/v1/tenants/{code}/reception/check-in", json=body)
    assert r.status_code == 200, r.text
    return r.json()


class TestHourlyCheckIn:
    def test_hourly_not_consume_overnight_availability(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        rtid = int(s["rt"]["id"])
        today = "2026-10-01"
        # 基准：2 间全空
        assert _avail(client, code, rtid, today) == 2

        # 过夜散客入住 0101（今天→明天）
        a = _walk_in(client, code, s, "0101", "过夜客")
        assert a["stay_type"] == "daily"
        assert _avail(client, code, rtid, today) == 1

        # 钟点房入住 0102（4 小时，同日）——不占过夜可售房量
        h = _walk_in(client, code, s, "0102", "钟点客", hourly=4)
        assert h["stay_type"] == "hourly"
        assert h["hourly_hours"] == 4
        assert h["check_in_date"] == today and h["check_out_date"] == today  # 强制同日
        assert h["total_price"] == 5000 * 4  # 时租价 × 时长
        # M32.17b：到店时刻已记录（HH:MM），离店时刻由前端按 时刻+时长 展示
        import re as _re
        assert h["hourly_start_time"] and _re.fullmatch(r"\d{2}:\d{2}", h["hourly_start_time"])
        assert _avail(client, code, rtid, today) == 1  # 关键断言：仍是 1，未被钟点房占用

    def test_hourly_forces_same_day(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        # 前端误传跨日离店 → 服务端强制同日
        body = {
            "room_no": "0101",
            "room_type_id": int(s["rt"]["id"]),
            "guest_name": "钟点客",
            "check_in_date": "2026-10-01",
            "check_out_date": "2026-10-02",
            "stay_type": "hourly",
            "hourly_hours": 3,
        }
        r = client.post(f"/api/v1/tenants/{code}/reception/check-in", json=body)
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["check_out_date"] == "2026-10-01"
        assert b["total_price"] == 5000 * 3

    def test_hourly_requires_positive_hours(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        body = {
            "room_no": "0101",
            "room_type_id": int(s["rt"]["id"]),
            "guest_name": "钟点客",
            "check_in_date": "2026-10-01",
            "check_out_date": "2026-10-01",
            "stay_type": "hourly",
        }
        r = client.post(f"/api/v1/tenants/{code}/reception/check-in", json=body)
        assert r.status_code == 409
        assert "hourly_hours" in r.json()["detail"] or "时长" in r.json()["detail"]

    def test_hourly_respects_one_in_house_per_room(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        _walk_in(client, code, s, "0101", "钟点客A", hourly=2)
        # 同房再来一单钟点房 → 一房一在住单守卫拦截
        body = {
            "room_no": "0101",
            "room_type_id": int(s["rt"]["id"]),
            "guest_name": "钟点客B",
            "check_in_date": "2026-10-01",
            "check_out_date": "2026-10-01",
            "stay_type": "hourly",
            "hourly_hours": 2,
        }
        r = client.post(f"/api/v1/tenants/{code}/reception/check-in", json=body)
        assert r.status_code == 409, r.text
        assert "已有在住单" in r.json()["detail"] or "不可预锁" in r.json()["detail"]
