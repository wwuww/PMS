"""团队 / 会议排房测试（M15，FR-GROUP）。"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    tenant = client.post(
        "/api/v1/tenants", json={"code": "t-group", "name": "团队测试"}
    ).json()
    hotel = client.post(
        f"/api/v1/tenants/{tenant['id']}/hotels", json={"code": "G1", "name": "店"}
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
            {"room_type_id": rt["id"], "room_no": "0201"},
        ],
    )
    return {"tenant": tenant, "hotel": hotel, "room_type": rt}


class TestGroupBlock:
    def test_create_assign_and_check_in(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        hid = int(s["hotel"]["id"])
        rtid = int(s["room_type"]["id"])
        # 建 block
        blk = client.post(
            f"/api/v1/tenants/{code}/group-blocks",
            json={
                "hotel_id": hid,
                "name": "旅行团A",
                "arrival_date": "2026-10-01",
                "departure_date": "2026-10-03",
            },
        )
        assert blk.status_code == 201
        block_id = blk.json()["id"]
        # 排房（锁房预留）
        assign = client.post(
            f"/api/v1/tenants/{code}/group-blocks/{block_id}/assign",
            json={
                "allocations": [
                    {"room_no": "0101", "room_type_id": rtid, "guest_name": "张三", "guest_phone": "13800000301"},
                    {"room_no": "0102", "room_type_id": rtid, "guest_name": "李四"},
                ]
            },
        )
        assert assign.status_code == 200
        body = assign.json()
        assert len(body["allocations"]) == 2
        assert all(a["status"] == "assigned" for a in body["allocations"])
        # 锁房后房态应为锁房
        rooms = client.get(f"/api/v1/tenants/{code}/rooms").json()
        locked = {r["room_no"]: r["state"] for r in rooms}
        assert locked["0101"] == "arrival_locked"
        assert locked["0102"] == "arrival_locked"
        # 批量入住
        checkin = client.post(
            f"/api/v1/tenants/{code}/group-blocks/{block_id}/check-in",
            params={"operator": "front_desk"},
        )
        assert checkin.status_code == 200
        ci = checkin.json()
        assert all(a["status"] == "checked_in" for a in ci["allocations"])
        # 入住后房态转为在住
        rooms2 = client.get(f"/api/v1/tenants/{code}/rooms").json()
        occ = {r["room_no"]: r["state"] for r in rooms2}
        assert occ["0101"] == "occupied"
        assert occ["0102"] == "occupied"
        # 生成了 group 渠道预订
        bks = client.get(f"/api/v1/tenants/{code}/bookings").json()
        grp = [b for b in bks if b["channel"] == "group"]
        assert len(grp) == 2
        # 带手机号的客档联动会员
        g = client.get(
            f"/api/v1/tenants/{code}/guests/search", params={"phone": "13800000301"}
        ).json()
        assert len(g) == 1

    def test_block_not_found_404(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        resp = client.post(
            f"/api/v1/tenants/{code}/group-blocks/999999/assign",
            json={"allocations": [{"room_no": "0101", "room_type_id": 1}]},
        )
        assert resp.status_code == 404

    def test_assign_non_vacant_room_409(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        hid = int(s["hotel"]["id"])
        rtid = int(s["room_type"]["id"])
        # 先用散客接待占用 0201
        walk = client.post(
            f"/api/v1/tenants/{code}/reception/check-in",
            json={
                "room_no": "0201",
                "room_type_id": rtid,
                "guest_name": "占用客",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-03",
                "operator": "front_desk",
            },
        )
        assert walk.status_code == 200
        # 建 block 并尝试排已被占用的房
        blk = client.post(
            f"/api/v1/tenants/{code}/group-blocks",
            json={
                "hotel_id": hid,
                "name": "会议B",
                "arrival_date": "2026-10-01",
                "departure_date": "2026-10-03",
            },
        ).json()
        assign = client.post(
            f"/api/v1/tenants/{code}/group-blocks/{blk['id']}/assign",
            json={"allocations": [{"room_no": "0201", "room_type_id": rtid}]},
        )
        assert assign.status_code == 409

    def test_assign_duplicate_room_409(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        hid = int(s["hotel"]["id"])
        rtid = int(s["room_type"]["id"])
        b1 = client.post(
            f"/api/v1/tenants/{code}/group-blocks",
            json={
                "hotel_id": hid,
                "name": "团1",
                "arrival_date": "2026-10-01",
                "departure_date": "2026-10-03",
            },
        ).json()
        b2 = client.post(
            f"/api/v1/tenants/{code}/group-blocks",
            json={
                "hotel_id": hid,
                "name": "团2",
                "arrival_date": "2026-10-01",
                "departure_date": "2026-10-03",
            },
        ).json()
        # 团1 排 0101
        a1 = client.post(
            f"/api/v1/tenants/{code}/group-blocks/{b1['id']}/assign",
            json={"allocations": [{"room_no": "0101", "room_type_id": rtid}]},
        )
        assert a1.status_code == 200
        # 团2 再排同一房 → 409
        a2 = client.post(
            f"/api/v1/tenants/{code}/group-blocks/{b2['id']}/assign",
            json={"allocations": [{"room_no": "0101", "room_type_id": rtid}]},
        )
        assert a2.status_code == 409

    def test_close_block(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        hid = int(s["hotel"]["id"])
        rtid = int(s["room_type"]["id"])
        blk = client.post(
            f"/api/v1/tenants/{code}/group-blocks",
            json={
                "hotel_id": hid,
                "name": "团3",
                "arrival_date": "2026-10-01",
                "departure_date": "2026-10-03",
            },
        ).json()
        client.post(
            f"/api/v1/tenants/{code}/group-blocks/{blk['id']}/assign",
            json={"allocations": [{"room_no": "0103", "room_type_id": rtid}]},
        )
        close = client.post(
            f"/api/v1/tenants/{code}/group-blocks/{blk['id']}/close"
        )
        assert close.status_code == 200
        assert close.json()["status"] == "closed"
        # 关闭后不可再批量入住
        again = client.post(
            f"/api/v1/tenants/{code}/group-blocks/{blk['id']}/check-in",
            params={"operator": "front_desk"},
        )
        assert again.status_code == 409

    def test_departure_before_arrival_409(self, client: TestClient) -> None:
        s = _seed(client)
        code = s["tenant"]["code"]
        hid = int(s["hotel"]["id"])
        resp = client.post(
            f"/api/v1/tenants/{code}/group-blocks",
            json={
                "hotel_id": hid,
                "name": "非法团",
                "arrival_date": "2026-10-05",
                "departure_date": "2026-10-03",
            },
        )
        assert resp.status_code == 409
