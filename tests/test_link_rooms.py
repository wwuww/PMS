"""在住联房测试（M32.15）：link / unlink，各单保留自己的来离店日期。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    tenant = client.post(
        "/api/v1/tenants", json={"code": "t-link", "name": "联房测试"}
    ).json()
    hotel = client.post(
        f"/api/v1/tenants/{tenant['id']}/hotels", json={"code": "L1", "name": "店"}
    ).json()
    rt = client.post(
        f"/api/v1/tenants/{tenant['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{hotel['id']}/rooms",
        json=[
            {"room_type_id": rt["id"], "room_no": "0101"},
            {"room_type_id": rt["id"], "room_no": "0102"},
            {"room_type_id": rt["id"], "room_no": "0103"},
        ],
    )
    return {"tenant": tenant, "hotel": hotel, "rt": rt}


def _check_in(client: TestClient, code: str, s: dict, room_no: str, guest: str, cin: str, cout: str) -> dict:
    bk = client.post(
        f"/api/v1/tenants/{code}/bookings",
        json={
            "hotel_id": int(s["hotel"]["id"]),
            "room_type_id": int(s["rt"]["id"]),
            "guest_name": guest,
            "check_in_date": cin,
            "check_out_date": cout,
        },
    ).json()
    ci = client.post(
        f"/api/v1/tenants/{code}/bookings/{bk['id']}/check-in",
        json={"room_no": room_no},
    )
    assert ci.status_code == 200, ci.text
    return ci.json()


class TestLinkRooms:
    def test_link_two_rooms_keeps_own_dates(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        # 两间在住：来离店日期刻意不同
        a = _check_in(client, code, s, "0101", "张三", "2026-10-01", "2026-10-03")
        b = _check_in(client, code, s, "0102", "李四", "2026-10-02", "2026-10-05")

        r = client.post(
            f"/api/v1/tenants/{code}/bookings/link",
            json={"room_nos": ["0101", "0102"], "master_room_no": "0101"},
        )
        assert r.status_code == 200, r.text
        out = {x["room_no"]: x for x in r.json()}
        assert out["0101"]["is_link_master"] is True
        assert out["0102"]["is_link_master"] is False
        assert out["0101"]["link_group_id"] == out["0102"]["link_group_id"]
        # 关键业务规则：联房不改动各自的来离店日期
        assert out["0101"]["check_in_date"] == "2026-10-01"
        assert out["0101"]["check_out_date"] == "2026-10-03"
        assert out["0102"]["check_in_date"] == "2026-10-02"
        assert out["0102"]["check_out_date"] == "2026-10-05"

    def test_link_requires_two_in_house(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        _check_in(client, code, s, "0101", "张三", "2026-10-01", "2026-10-03")
        # 一间在住 + 一间空房 → 409
        r = client.post(
            f"/api/v1/tenants/{code}/bookings/link",
            json={"room_nos": ["0101", "0102"], "master_room_no": "0101"},
        )
        assert r.status_code == 409
        assert "在住单" in r.json()["detail"]
        # 只有一间 → 422（schema 层 min_length=2 拦截）
        r2 = client.post(
            f"/api/v1/tenants/{code}/bookings/link",
            json={"room_nos": ["0101"], "master_room_no": "0101"},
        )
        assert r2.status_code == 422
        # 主房不在列表内 → 409
        _check_in(client, code, s, "0102", "李四", "2026-10-01", "2026-10-03")
        r3 = client.post(
            f"/api/v1/tenants/{code}/bookings/link",
            json={"room_nos": ["0101", "0102"], "master_room_no": "0103"},
        )
        assert r3.status_code == 409

    def test_unlink_and_master_handover(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        _check_in(client, code, s, "0101", "张三", "2026-10-01", "2026-10-03")
        _check_in(client, code, s, "0102", "李四", "2026-10-01", "2026-10-04")
        _check_in(client, code, s, "0103", "王五", "2026-10-02", "2026-10-06")
        r = client.post(
            f"/api/v1/tenants/{code}/bookings/link",
            json={"room_nos": ["0101", "0102", "0103"], "master_room_no": "0101"},
        )
        assert r.status_code == 200
        gid = r.json()[0]["link_group_id"]

        # 主房 0101 移出 → 剩余组内自动移交主房（字典序第一间 0102）
        r2 = client.post(
            f"/api/v1/tenants/{code}/bookings/unlink",
            json={"room_nos": ["0101"]},
        )
        assert r2.status_code == 200, r2.text
        out = {x["room_no"]: x for x in r2.json()}
        assert out["0101"]["link_group_id"] is None
        assert out["0101"]["is_link_master"] is False

        # 0102/0103 仍在原组，0102 接管主房
        bl = client.get(f"/api/v1/tenants/{code}/bookings").json()
        byroom = {x["room_no"]: x for x in bl if x["status"] == "checked_in"}
        assert byroom["0102"]["link_group_id"] == gid
        assert byroom["0102"]["is_link_master"] is True
        assert byroom["0103"]["link_group_id"] == gid
        assert byroom["0103"]["is_link_master"] is False

    def test_unlink_without_group_conflict(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        _check_in(client, code, s, "0101", "张三", "2026-10-01", "2026-10-03")
        r = client.post(f"/api/v1/tenants/{code}/bookings/unlink", json={"room_nos": ["0101"]})
        assert r.status_code == 409
        assert "没有联房关系" in r.json()["detail"]


class TestSettleToMaster:
    def _link(self, client: TestClient, code: str) -> None:
        r = client.post(
            f"/api/v1/tenants/{code}/bookings/link",
            json={"room_nos": ["0101", "0102"], "master_room_no": "0101"},
        )
        assert r.status_code == 200

    def _bill_by_room(self, client: TestClient, code: str, room_no: str) -> dict:
        bl = client.get(f"/api/v1/tenants/{code}/bills").json()
        hits = [b for b in bl if b.get("room_no") == room_no and b["status"] == "OPEN"]
        return hits[0] if hits else {}

    def test_transfer_and_checkout(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        _check_in(client, code, s, "0101", "张三", "2026-10-01", "2026-10-03")
        _check_in(client, code, s, "0102", "李四", "2026-10-01", "2026-10-03")
        self._link(client, code)
        # 从房账单加杂费 8000 分
        sub_bill = self._bill_by_room(client, code, "0102")
        assert sub_bill, "入住应自动开账"
        r = client.post(
            f"/api/v1/tenants/{code}/bills/{sub_bill['id']}/charges",
            json={"charge_type": "MISC", "amount": 8000, "description": "洗衣"},
        )
        assert r.status_code == 200, r.text
        sub_balance = r.json()["balance"]
        assert sub_balance == 8000
        master_before = self._bill_by_room(client, code, "0101").get("balance", 0)

        # 结转
        t = client.post(
            f"/api/v1/tenants/{code}/bookings/settle-to-master",
            json={"room_no": "0102"},
        )
        assert t.status_code == 200, t.text
        out = t.json()
        assert out["amount"] == 8000
        assert out["sub_bill_balance"] == 0
        assert out["master_bill_balance"] == master_before + 8000
        # 组内净额守恒：主房 +8000，从房归零
        assert self._bill_by_room(client, code, "0102")["balance"] == 0

        # 从房余额归零后可正常退房
        bid = None
        for b in client.get(f"/api/v1/tenants/{code}/bookings").json():
            if b["room_no"] == "0102" and b["status"] == "checked_in":
                bid = b["id"]
        co = client.post(f"/api/v1/tenants/{code}/bookings/{bid}/check-out", json={"operator": "front_desk"})
        assert co.status_code == 200, co.text

    def test_transfer_requires_sub_room(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        _check_in(client, code, s, "0101", "张三", "2026-10-01", "2026-10-03")
        _check_in(client, code, s, "0102", "李四", "2026-10-01", "2026-10-03")
        self._link(client, code)
        # 主房不可结转
        r = client.post(
            f"/api/v1/tenants/{code}/bookings/settle-to-master",
            json={"room_no": "0101"},
        )
        assert r.status_code == 409
        assert "从房" in r.json()["detail"]
        # 未联房房间不可结转
        _check_in(client, code, s, "0103", "王五", "2026-10-01", "2026-10-03")
        r2 = client.post(
            f"/api/v1/tenants/{code}/bookings/settle-to-master",
            json={"room_no": "0103"},
        )
        assert r2.status_code == 409
        assert "从房" in r2.json()["detail"]

    def test_transfer_empty_balance_conflict(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        _check_in(client, code, s, "0101", "张三", "2026-10-01", "2026-10-03")
        _check_in(client, code, s, "0102", "李四", "2026-10-01", "2026-10-03")
        self._link(client, code)
        # 从房余额为 0 → 409
        r = client.post(
            f"/api/v1/tenants/{code}/bookings/settle-to-master",
            json={"room_no": "0102"},
        )
        assert r.status_code == 409
        assert "未结账务" in r.json()["detail"]


class TestUniqueInHouse:
    """业务规则：一间房同时只能有一笔在住单。"""

    def test_second_check_in_rejected(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        _check_in(client, code, s, "0101", "张三", "2026-10-01", "2026-10-03")
        # 第二笔订单尝试入住同一房间 → 409
        bk2 = client.post(
            f"/api/v1/tenants/{code}/bookings",
            json={
                "hotel_id": int(s["hotel"]["id"]),
                "room_type_id": int(s["rt"]["id"]),
                "guest_name": "李四",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-02",
            },
        ).json()
        r = client.post(
            f"/api/v1/tenants/{code}/bookings/{bk2['id']}/check-in",
            json={"room_no": "0101"},
        )
        assert r.status_code == 409, r.text
        assert "已有在住单" in r.json()["detail"]
        # 房间状态应保持 occupied，第一笔在住单不受影响
        rooms = client.get(f"/api/v1/tenants/{code}/rooms").json()
        assert next(x for x in rooms if x["room_no"] == "0101")["state"] == "occupied"
        bks = client.get(f"/api/v1/tenants/{code}/bookings?status_=checked_in").json()
        assert [b["guest_name"] for b in bks if b["room_no"] == "0101"] == ["张三"]
