"""预订引擎测试（M2）。"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    tenant = client.post(
        "/api/v1/tenants", json={"code": "t-book", "name": "预订测试"}
    ).json()
    hotel = client.post(
        f"/api/v1/tenants/{tenant['id']}/hotels", json={"code": "H1", "name": "店"}
    ).json()
    room_type = client.post(
        f"/api/v1/tenants/{tenant['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{hotel['id']}/rooms",
        json=[
            {"room_type_id": room_type["id"], "room_no": "0101"},
            {"room_type_id": room_type["id"], "room_no": "0102"},
        ],
    )
    return {"tenant": tenant, "hotel": hotel, "room_type": room_type}


class TestBooking:
    def test_full_lifecycle(self, client: TestClient) -> None:
        s = _seed(client)
        rt = s["room_type"]

        # 创建预订
        resp = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/bookings",
            json={
                "hotel_id": s["hotel"]["id"],
                "room_type_id": rt["id"],
                "guest_name": "张三",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-03",
                "channel": "direct",
            },
        )
        assert resp.status_code == 201
        booking = resp.json()
        assert booking["status"] == "created"
        assert booking["nights"] == 2
        assert booking["total_price"] == 60000  # 30000 * 2

        # 房量占用：10-01 与 10-02 各占 1
        avail = client.get(
            f"/api/v1/tenants/{s['tenant']['code']}/room-types/{rt['id']}/availability",
            params={"date": "2026-10-02"},
        ).json()
        assert avail["available"] == 1

        # 入住（分配 0101）
        resp = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/bookings/{booking['id']}/check-in",
            json={"room_no": "0101"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "checked_in"
        # 房态应转在住
        room = client.get(
            f"/api/v1/tenants/{s['tenant']['code']}/rooms",
            params={"state": "occupied"},
        ).json()
        assert any(r["room_no"] == "0101" for r in room)

        # 退房
        resp = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/bookings/{booking['id']}/check-out",
            json={},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "checked_out"

    def test_overbooking_rejected(self, client: TestClient) -> None:
        s = _seed(client)
        rt = s["room_type"]
        # 两间房，订 3 晚占用其中 1 间两天
        for _ in range(2):
            resp = client.post(
                f"/api/v1/tenants/{s['tenant']['code']}/bookings",
                json={
                    "hotel_id": s["hotel"]["id"],
                    "room_type_id": rt["id"],
                    "guest_name": "客人",
                    "check_in_date": "2026-10-01",
                    "check_out_date": "2026-10-02",
                    "channel": "direct",
                },
            )
            assert resp.status_code == 201
        # 第三单同晚应房量不足
        resp = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/bookings",
            json={
                "hotel_id": s["hotel"]["id"],
                "room_type_id": rt["id"],
                "guest_name": "超订客人",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-02",
                "channel": "direct",
            },
        )
        assert resp.status_code == 409
        assert "房量不足" in resp.json()["detail"]

    def test_cancel_releases_lock_and_inventory(self, client: TestClient) -> None:
        s = _seed(client)
        rt = s["room_type"]
        # 预分配房号创建预订（应锁房 ARRIVAL_LOCKED）
        resp = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/bookings",
            json={
                "hotel_id": s["hotel"]["id"],
                "room_type_id": rt["id"],
                "guest_name": "李四",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-02",
                "room_no": "0101",
            },
        )
        booking = resp.json()
        assert booking["status"] == "created"
        room = client.get(
            f"/api/v1/tenants/{s['tenant']['code']}/rooms",
            params={"state": "arrival_locked"},
        ).json()
        assert any(r["room_no"] == "0101" for r in room)

        # 取消应释放锁房并恢复空净
        resp = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/bookings/{booking['id']}/cancel",
            json={},
        )
        assert resp.json()["status"] == "cancelled"
        room = client.get(
            f"/api/v1/tenants/{s['tenant']['code']}/rooms",
            params={"state": "vacant_clean"},
        ).json()
        assert any(r["room_no"] == "0101" for r in room)


class TestBookingInHouseOps:
    """在住房间业务操作：续住（extend-stay）/ 换房（change-room）。"""

    def _checked_in(self, client: TestClient) -> dict:
        s = _seed(client)
        resp = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/bookings",
            json={
                "hotel_id": s["hotel"]["id"],
                "room_type_id": s["room_type"]["id"],
                "guest_name": "王五",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-03",
                "channel": "direct",
            },
        )
        booking = resp.json()
        client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/bookings/{booking['id']}/check-in",
            json={"room_no": "0101"},
        )
        s["booking"] = booking
        return s

    def test_extend_stay(self, client: TestClient) -> None:
        s = self._checked_in(client)
        code = s["tenant"]["code"]
        bid = s["booking"]["id"]

        # 延长至 10-04：间夜 2→3，房费 60000→90000
        resp = client.post(
            f"/api/v1/tenants/{code}/bookings/{bid}/extend-stay",
            json={"new_check_out_date": "2026-10-04"},
        )
        assert resp.status_code == 200, resp.text
        b = resp.json()
        assert b["status"] == "checked_in"
        assert b["check_out_date"] == "2026-10-04"
        assert b["nights"] == 3
        assert b["total_price"] == 90000

        # 非法：离店日期不晚于当前 → 409
        resp = client.post(
            f"/api/v1/tenants/{code}/bookings/{bid}/extend-stay",
            json={"new_check_out_date": "2026-10-04"},
        )
        assert resp.status_code == 409

    def test_extend_stay_requires_checked_in(self, client: TestClient) -> None:
        s = _seed(client)
        resp = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/bookings",
            json={
                "hotel_id": s["hotel"]["id"],
                "room_type_id": s["room_type"]["id"],
                "guest_name": "赵六",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-03",
                "channel": "direct",
            },
        )
        # created 状态不可续住
        resp = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/bookings/{resp.json()['id']}/extend-stay",
            json={"new_check_out_date": "2026-10-05"},
        )
        assert resp.status_code == 409

    def test_change_room(self, client: TestClient) -> None:
        s = self._checked_in(client)
        code = s["tenant"]["code"]
        bid = s["booking"]["id"]

        resp = client.post(
            f"/api/v1/tenants/{code}/bookings/{bid}/change-room",
            json={"new_room_no": "0102", "reason": "客人要求"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["room_no"] == "0102"

        # 新房 0102 转在住，原房 0101 转空脏待清扫
        rooms = client.get(f"/api/v1/tenants/{code}/rooms").json()
        by_no = {r["room_no"]: r["state"] for r in rooms}
        assert by_no["0102"] == "occupied"
        assert by_no["0101"] == "vacant_dirty"

    def test_change_room_rejects_same_and_invalid(self, client: TestClient) -> None:
        s = self._checked_in(client)
        code = s["tenant"]["code"]
        bid = s["booking"]["id"]

        # 目标房不能是原房
        resp = client.post(
            f"/api/v1/tenants/{code}/bookings/{bid}/change-room",
            json={"new_room_no": "0101", "reason": "客人要求"},
        )
        assert resp.status_code == 409

        # 目标房不存在
        resp = client.post(
            f"/api/v1/tenants/{code}/bookings/{bid}/change-room",
            json={"new_room_no": "0999", "reason": "客人要求"},
        )
        assert resp.status_code == 409


class TestBookingExtras:
    def _create(self, client: TestClient) -> dict:
        s = _seed(client)
        rt = s["room_type"]
        booking = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/bookings",
            json={
                "hotel_id": s["hotel"]["id"],
                "room_type_id": rt["id"],
                "guest_name": "附加客",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-03",
                "channel": "direct",
            },
        ).json()
        s["booking"] = booking
        s["code"] = s["tenant"]["code"]
        return s

    def test_set_extras_on_created(self, client: TestClient) -> None:
        s = self._create(client)
        resp = client.post(
            f"/api/v1/tenants/{s['code']}/bookings/{s['booking']['id']}/extras",
            json={"extra_bed_count": 2, "companion_names": ["李四", "王五"]},
        )
        assert resp.status_code == 200, resp.text
        b = resp.json()
        assert b["extra_bed_count"] == 2
        assert b["companion_names"] == ["李四", "王五"]

    def test_set_extras_on_checked_in(self, client: TestClient) -> None:
        s = self._create(client)
        # 入住
        client.post(
            f"/api/v1/tenants/{s['code']}/bookings/{s['booking']['id']}/check-in",
            json={"room_no": "0101"},
        )
        resp = client.post(
            f"/api/v1/tenants/{s['code']}/bookings/{s['booking']['id']}/extras",
            json={"extra_bed_count": 1, "companion_names": ["赵六"]},
        )
        assert resp.status_code == 200
        assert resp.json()["extra_bed_count"] == 1

    def test_extras_rejects_after_checkout(self, client: TestClient) -> None:
        s = self._create(client)
        client.post(
            f"/api/v1/tenants/{s['code']}/bookings/{s['booking']['id']}/check-in",
            json={"room_no": "0101"},
        )
        client.post(
            f"/api/v1/tenants/{s['code']}/bookings/{s['booking']['id']}/check-out",
            json={},
        )
        resp = client.post(
            f"/api/v1/tenants/{s['code']}/bookings/{s['booking']['id']}/extras",
            json={"extra_bed_count": 1},
        )
        assert resp.status_code == 409

