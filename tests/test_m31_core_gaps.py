"""M31 核心缺口关闭集成测试。

#9 会员积分支付：扣减积分 → POINTS 收款流水；不足 409；结账再累积扣除积分支付部分（防回流）。
#10 团队分批结账：逐间结清（余额自动现金补收）+ 退房释放；结算汇总进度。
#34 免打扰（DND）：房态开关 + 清扫派单守卫。
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _seed(client: TestClient, code: str, rooms: tuple[str, ...] = ("0101", "0102")) -> tuple[dict, dict, dict]:
    t = client.post("/api/v1/tenants", json={"code": code, "name": "测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[{"room_type_id": rt["id"], "room_no": r} for r in rooms],
    )
    return t, h, rt


def _member_with_points(client: TestClient, code: str, hid: int, rt: dict, phone: str, room: str) -> dict:
    """注册会员 → 预订入住 → 开账 → 现金结清 → 积分按实收累积。"""
    m = client.post(
        f"/api/v1/tenants/{code}/members",
        json={"hotel_id": hid, "name": "积分客", "phone": phone},
    )
    assert m.status_code == 201, m.text
    bk = client.post(
        f"/api/v1/tenants/{code}/bookings",
        json={
            "hotel_id": hid,
            "room_type_id": rt["id"],
            "guest_name": "积分客",
            "guest_phone": phone,
            "check_in_date": "2026-11-01",
            "check_out_date": "2026-11-02",
            "room_no": room,
        },
    )
    assert bk.status_code == 201, bk.text
    r = client.post(f"/api/v1/tenants/{code}/bookings/{bk.json()['id']}/check-in", json={"room_no": room})
    assert r.status_code == 200, r.text
    bill = client.post(
        f"/api/v1/tenants/{code}/bills",
        json={"hotel_id": hid, "guest_name": "积分客", "booking_id": bk.json()["id"]},
    ).json()
    client.post(
        f"/api/v1/tenants/{code}/bills/{bill['id']}/charges",
        json={"charge_type": "ROOM_CHARGE", "amount": 30000, "description": "房租"},
    )
    client.post(
        f"/api/v1/tenants/{code}/bills/{bill['id']}/payments",
        json={"method": "CASH", "amount": 30000},
    )
    r = client.post(f"/api/v1/tenants/{code}/bills/{bill['id']}/settle")
    assert r.status_code == 200, r.text
    return client.get(f"/api/v1/tenants/{code}/members/{phone}").json()


# ================= #9 会员积分支付 =================


class TestPointsPay:
    def test_partial_points_deduction(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m31p1")
        m = _member_with_points(client, t["code"], int(h["id"]), rt, "13811110001", "0101")
        assert m["points"] == 300  # 30000 分 = 300 元 → 300 积分

        # 独立账单：余额 30000 分，用 300 积分抵 300 分
        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills",
            json={"hotel_id": h["id"], "guest_name": "积分客"},
        ).json()
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "MISC", "amount": 30000},
        )
        r = client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/pay-points",
            json={"member_phone": "13811110001", "points": 300, "operator": "ca"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["amount_cents"] == 300
        assert body["points_used"] == 300
        assert body["member_points_left"] == 0
        assert body["bill_balance"] == 29700

    def test_insufficient_points_409(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m31p2")
        m = _member_with_points(client, t["code"], int(h["id"]), rt, "13811110002", "0101")
        assert m["points"] == 300
        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills",
            json={"hotel_id": h["id"], "guest_name": "x"},
        ).json()
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "MISC", "amount": 10000},
        )
        r = client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/pay-points",
            json={"member_phone": "13811110002", "points": 301},
        )
        assert r.status_code == 409

    def test_points_over_balance_409(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m31p3")
        m = _member_with_points(client, t["code"], int(h["id"]), rt, "13811110003", "0101")
        assert m["points"] == 300
        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills",
            json={"hotel_id": h["id"], "guest_name": "x"},
        ).json()
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "MISC", "amount": 10000},
        )
        r = client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/pay-points",
            json={"member_phone": "13811110003", "points": 10001},
        )
        assert r.status_code == 409

    def test_settle_earn_excludes_points_payment(self, client: TestClient) -> None:
        """防积分回流：积分支付部分不计入再累积基数。"""
        t, h, rt = _seed(client, "m31p4")
        m = _member_with_points(client, t["code"], int(h["id"]), rt, "13811110004", "0101")
        assert m["points"] == 300

        # 会员预订在住房间的第二张账单：30000 分，积分抵 300 + 现金 29700 → 结账累积基数 29700 → +297 积分
        bk = client.post(
            f"/api/v1/tenants/{t['code']}/bookings",
            json={
                "hotel_id": h["id"],
                "room_type_id": rt["id"],
                "guest_name": "积分客",
                "guest_phone": "13811110004",
                "check_in_date": "2026-11-01",
                "check_out_date": "2026-11-02",
            },
        ).json()
        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills",
            json={"hotel_id": h["id"], "guest_name": "积分客", "booking_id": bk["id"]},
        ).json()
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "ROOM_CHARGE", "amount": 30000},
        )
        r = client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/pay-points",
            json={"member_phone": "13811110004", "points": 300},
        )
        assert r.status_code == 200
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/payments",
            json={"method": "CASH", "amount": 29700},
        )
        r = client.post(f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/settle")
        assert r.status_code == 200
        m2 = client.get(f"/api/v1/tenants/{t['code']}/members/13811110004").json()
        # 无防回流则 +300；防回流后 +297
        assert m2["points"] == 297, m2


# ================= #10 团队分批结账 =================


class TestGroupPartialSettle:
    def _setup_block(self, client: TestClient, code: str) -> tuple[int, list[dict]]:
        t = client.get(f"/api/v1/tenants/{code}").json()
        h = client.get(f"/api/v1/tenants/{code}/hotels").json()[0]
        rt = client.get(f"/api/v1/tenants/{code}/room-types").json()[0]
        blk = client.post(
            f"/api/v1/tenants/{code}/group-blocks",
            json={
                "hotel_id": int(h["id"]),
                "name": "分批团",
                "arrival_date": "2026-10-01",
                "departure_date": "2026-10-03",
            },
        )
        assert blk.status_code == 201, blk.text
        block_id = blk.json()["id"]
        r = client.post(
            f"/api/v1/tenants/{code}/group-blocks/{block_id}/assign",
            json={
                "allocations": [
                    {"room_no": "0101", "room_type_id": int(rt["id"]), "guest_name": "张三", "guest_phone": "13822220001"},
                    {"room_no": "0102", "room_type_id": int(rt["id"]), "guest_name": "李四"},
                ]
            },
        )
        assert r.status_code == 200, r.text
        r = client.post(f"/api/v1/tenants/{code}/group-blocks/{block_id}/check-in", params={"operator": "fd"})
        assert r.status_code == 200, r.text
        return block_id, r.json()

    def test_settle_allocation_progressive(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m31g1", rooms=("0101", "0102"))
        block_id, _ = self._setup_block(client, t["code"])

        # 给 0101 的账单加一笔消费，制造正余额（验证自动现金补收）
        allocs = client.get(f"/api/v1/tenants/{t['code']}/group-blocks/{block_id}").json()["allocations"]
        a1 = next(a for a in allocs if a["room_no"] == "0101")
        bookings = client.get(f"/api/v1/tenants/{t['code']}/bookings", params={"guest_name": "张三"}).json()
        bk1 = next(b for b in bookings if b["status"] == "checked_in")
        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills",
            json={"hotel_id": int(h["id"]), "guest_name": "张三", "booking_id": bk1["id"], "room_no": "0101"},
        ).json()
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "MISC", "amount": 8800, "description": "迷你吧"},
        )

        # 分批结账第 1 间
        r = client.post(
            f"/api/v1/tenants/{t['code']}/group-blocks/{block_id}/allocations/{a1['id']}/settle",
            json={"operator": "fd"},
        )
        assert r.status_code == 200, r.text
        row = r.json()
        assert row["room_no"] == "0101" and row["settled"] is True
        assert row["block_settled_count"] == 1

        # 结账汇总：1/2 已结
        s = client.get(f"/api/v1/tenants/{t['code']}/group-blocks/{block_id}/settlement").json()
        assert s["total_allocations"] == 2
        assert s["settled_allocations"] == 1
        # 0101 房已退（不在住），0102 仍在住
        rooms = {r_["room_no"]: r_["state"] for r_ in client.get(f"/api/v1/tenants/{t['code']}/rooms").json()}
        assert rooms["0101"] != "occupied"
        assert rooms["0102"] == "occupied"

        # 结第 2 间 → 2/2
        a2 = next(a for a in allocs if a["room_no"] == "0102")
        r = client.post(
            f"/api/v1/tenants/{t['code']}/group-blocks/{block_id}/allocations/{a2['id']}/settle",
            json={"operator": "fd"},
        )
        assert r.status_code == 200, r.text
        s = client.get(f"/api/v1/tenants/{t['code']}/group-blocks/{block_id}/settlement").json()
        assert s["settled_allocations"] == 2

    def test_settle_twice_409(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m31g2", rooms=("0101", "0102"))
        block_id, _ = self._setup_block(client, t["code"])
        allocs = client.get(f"/api/v1/tenants/{t['code']}/group-blocks/{block_id}").json()["allocations"]
        a1 = allocs[0]
        r = client.post(
            f"/api/v1/tenants/{t['code']}/group-blocks/{block_id}/allocations/{a1['id']}/settle",
            json={"operator": "fd"},
        )
        assert r.status_code == 200
        r = client.post(
            f"/api/v1/tenants/{t['code']}/group-blocks/{block_id}/allocations/{a1['id']}/settle",
            json={"operator": "fd"},
        )
        assert r.status_code == 409  # 已退房不可重复结账


# ================= #34 免打扰（DND） =================


class TestRoomDnd:
    def _checkin_room(self, client: TestClient, code: str, hid: int, rt: dict, room: str, phone: str) -> dict:
        bk = client.post(
            f"/api/v1/tenants/{code}/bookings",
            json={
                "hotel_id": hid,
                "room_type_id": rt["id"],
                "guest_name": "在住客",
                "guest_phone": phone,
                "check_in_date": "2026-11-01",
                "check_out_date": "2026-11-03",
                "room_no": room,
            },
        )
        assert bk.status_code == 201, bk.text
        r = client.post(f"/api/v1/tenants/{code}/bookings/{bk.json()['id']}/check-in", json={"room_no": room})
        assert r.status_code == 200, r.text
        return bk.json()

    def test_toggle_and_room_grid(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m31d1")
        code, hid = t["code"], int(h["id"])
        # M32.1：非在住房不允许开启免打扰
        r = client.post(
            f"/api/v1/tenants/{code}/rooms/0101/dnd",
            json={"dnd": True, "operator": "fd"},
        )
        assert r.status_code == 409, r.text
        assert "免打扰仅限在住" in r.json()["detail"]
        # 在住房可开启
        self._checkin_room(client, code, hid, rt, "0101", "13855560001")
        r = client.post(
            f"/api/v1/tenants/{code}/rooms/0101/dnd",
            json={"dnd": True, "operator": "fd"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["dnd"] == 1
        rooms = {x["room_no"]: x for x in client.get(f"/api/v1/tenants/{code}/rooms").json()}
        assert rooms["0101"]["dnd"] == 1
        assert rooms["0101"]["state"] == "occupied"
        # 取消（关闭随时可操作）
        r = client.post(
            f"/api/v1/tenants/{code}/rooms/0101/dnd",
            json={"dnd": False, "operator": "fd"},
        )
        assert r.json()["dnd"] == 0

    def test_dnd_auto_cleared_on_checkout(self, client: TestClient) -> None:
        """M32.1：在住房退房后自动清除免打扰。"""
        t, h, rt = _seed(client, "m31d4")
        code, hid = t["code"], int(h["id"])
        bk = self._checkin_room(client, code, hid, rt, "0101", "13855560002")
        client.post(f"/api/v1/tenants/{code}/rooms/0101/dnd", json={"dnd": True, "operator": "fd"})
        r = client.post(f"/api/v1/tenants/{code}/bookings/{bk['id']}/check-out", json={})
        assert r.status_code == 200, r.text
        rooms = {x["room_no"]: x for x in client.get(f"/api/v1/tenants/{code}/rooms").json()}
        assert rooms["0101"]["dnd"] == 0
        assert rooms["0101"]["state"] == "vacant_dirty"

    def test_dnd_cleared_via_room_transition(self, client: TestClient) -> None:
        """M32.1：房态盘手动「退房」走房态流转端点，同样自动清除 DND。"""
        t, h, rt = _seed(client, "m31d5")
        code, hid = t["code"], int(h["id"])
        self._checkin_room(client, code, hid, rt, "0101", "13855560004")
        client.post(f"/api/v1/tenants/{code}/rooms/0101/dnd", json={"dnd": True, "operator": "fd"})
        # 房态盘路径：直接房态流转 check_out（不经 BookingService）
        r = client.post(
            f"/api/v1/tenants/{code}/rooms/0101/transition",
            json={"trigger": "check_out", "operator": "fd"},
        )
        assert r.status_code == 200, r.text
        rooms = {x["room_no"]: x for x in client.get(f"/api/v1/tenants/{code}/rooms").json()}
        assert rooms["0101"]["dnd"] == 0
        assert rooms["0101"]["state"] == "vacant_dirty"

    def test_dnd_blocks_cleanup_assign(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m31d2")
        code, hid = t["code"], int(h["id"])
        self._checkin_room(client, code, hid, rt, "0101", "13855560003")
        client.post(f"/api/v1/tenants/{code}/rooms/0101/dnd", json={"dnd": True, "operator": "fd"})
        # 创建清扫工单 → 派单应被 DND 守卫拒绝
        task = client.post(
            f"/api/v1/tenants/{t['code']}/housekeeping-tasks",
            json={"hotel_id": int(h["id"]), "room_no": "0101", "task_type": "CLEANUP", "priority": "NORMAL"},
        )
        assert task.status_code == 201, task.text
        r = client.post(
            f"/api/v1/tenants/{t['code']}/housekeeping-tasks/{task.json()['id']}/assign",
            json={"assignee": "阿姨A"},
        )
        assert r.status_code == 409, r.text
        assert "免打扰" in r.json()["detail"]
        # 取消 DND 后可派单
        client.post(f"/api/v1/tenants/{t['code']}/rooms/0101/dnd", json={"dnd": False, "operator": "fd"})
        r = client.post(
            f"/api/v1/tenants/{t['code']}/housekeeping-tasks/{task.json()['id']}/assign",
            json={"assignee": "阿姨A"},
        )
        assert r.status_code == 200, r.text

    def test_dnd_room_not_found_404(self, client: TestClient) -> None:
        t, _, _ = _seed(client, "m31d3")
        r = client.post(
            f"/api/v1/tenants/{t['code']}/rooms/9999/dnd",
            json={"dnd": True, "operator": "fd"},
        )
        assert r.status_code == 404
