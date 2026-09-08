"""宾客档案 / 客史测试（M14，FR-GUEST）。"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    tenant = client.post(
        "/api/v1/tenants", json={"code": "t-guest", "name": "宾客测试"}
    ).json()
    hotel = client.post(
        f"/api/v1/tenants/{tenant['id']}/hotels", json={"code": "G1", "name": "店"}
    ).json()
    room_type = client.post(
        f"/api/v1/tenants/{tenant['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(
        f"/api/v1/hotels/{hotel['id']}/rooms",
        json=[{"room_type_id": room_type["id"], "room_no": "0101"}],
    )
    return {"tenant": tenant, "hotel": hotel, "room_type": room_type}


class TestGuest:
    def test_create_and_get(self, client: TestClient) -> None:
        s = _seed(client)
        resp = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/guests",
            json={
                "hotel_id": int(s["hotel"]["id"]),
                "name": "王五",
                "phone": "13800000001",
                "id_type": "ID",
                "id_no": "440100199001010011",
                "vip_level": "GOLD",
                "tags": ["高楼层", "无烟房"],
                "notes": "喜欢安静",
            },
        )
        assert resp.status_code == 201
        g = resp.json()
        assert g["name"] == "王五"
        assert g["vip_level"] == "GOLD"
        assert g["tags"] == ["高楼层", "无烟房"]

        got = client.get(
            f"/api/v1/tenants/{s['tenant']['code']}/guests/{g['id']}"
        ).json()
        assert got["id"] == g["id"]
        assert got["notes"] == "喜欢安静"

    def test_create_without_phone_ok(self, client: TestClient) -> None:
        s = _seed(client)
        # 散客无手机号也可建档
        resp = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/guests",
            json={"hotel_id": int(s["hotel"]["id"]), "name": "散客A"},
        )
        assert resp.status_code == 201
        assert resp.json()["phone"] is None

    def test_duplicate_phone_returns_same_guest(self, client: TestClient) -> None:
        s = _seed(client)
        body = {
            "hotel_id": int(s["hotel"]["id"]),
            "name": "赵六",
            "phone": "13800000002",
        }
        first = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/guests", json=body
        ).json()
        second = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/guests", json=body
        ).json()
        assert second["id"] == first["id"]

    def test_search_by_phone_and_name(self, client: TestClient) -> None:
        s = _seed(client)
        client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/guests",
            json={
                "hotel_id": int(s["hotel"]["id"]),
                "name": "孙七",
                "phone": "13800000003",
            },
        )
        by_phone = client.get(
            f"/api/v1/tenants/{s['tenant']['code']}/guests/search",
            params={"phone": "13800000003"},
        ).json()
        assert len(by_phone) == 1 and by_phone[0]["name"] == "孙七"

        by_name = client.get(
            f"/api/v1/tenants/{s['tenant']['code']}/guests/search",
            params={"name": "孙七"},
        ).json()
        assert len(by_name) == 1

        empty = client.get(
            f"/api/v1/tenants/{s['tenant']['code']}/guests/search"
        )
        assert empty.status_code == 400

    def test_update_notes_and_tags(self, client: TestClient) -> None:
        s = _seed(client)
        g = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/guests",
            json={"hotel_id": int(s["hotel"]["id"]), "name": "周八", "phone": "13800000004"},
        ).json()
        resp = client.patch(
            f"/api/v1/tenants/{s['tenant']['code']}/guests/{g['id']}",
            json={"notes": "VIP 偏好", "tags": ["安静房"], "vip_level": "PLATINUM"},
        )
        assert resp.status_code == 200
        upd = resp.json()
        assert upd["notes"] == "VIP 偏好"
        assert upd["tags"] == ["安静房"]
        assert upd["vip_level"] == "PLATINUM"

    def test_list_keyword(self, client: TestClient) -> None:
        s = _seed(client)
        client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/guests",
            json={"hotel_id": int(s["hotel"]["id"]), "name": "吴九", "phone": "13800000005"},
        )
        found = client.get(
            f"/api/v1/tenants/{s['tenant']['code']}/guests",
            params={"keyword": "13800000005"},
        ).json()
        assert any(g["name"] == "吴九" for g in found)

    def test_checkin_records_stay_history(self, client: TestClient) -> None:
        s = _seed(client)
        # 建预订（不预分配房，房间保持空净）
        resp = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/bookings",
            json={
                "hotel_id": int(s["hotel"]["id"]),
                "room_type_id": int(s["room_type"]["id"]),
                "guest_name": "入住客",
                "guest_phone": "13800000006",
                "check_in_date": "2026-09-10",
                "check_out_date": "2026-09-12",
            },
        )
        assert resp.status_code == 201
        booking_id = resp.json()["id"]
        # 入住 → 触发客史累计（record_stay）
        ci = client.post(
            f"/api/v1/tenants/{s['tenant']['code']}/bookings/{booking_id}/check-in",
            json={"room_no": "0101", "operator": "front_desk"},
        )
        assert ci.status_code == 200
        # 按手机号查客档，断言客史累计正确
        found = client.get(
            f"/api/v1/tenants/{s['tenant']['code']}/guests/search",
            params={"phone": "13800000006"},
        ).json()
        assert len(found) == 1
        assert found[0]["stay_count"] >= 1
        assert found[0]["total_spend"] > 0

    def test_create_links_member_by_phone(self, client: TestClient) -> None:
        s = _seed(client)
        hid = int(s["hotel"]["id"])
        code = s["tenant"]["code"]
        # 先注册会员
        m = client.post(
            f"/api/v1/tenants/{code}/members",
            json={"hotel_id": hid, "name": "会员甲", "phone": "13800000099"},
        )
        assert m.status_code == 201
        # 同手机号建档宾客 → 自动关联会员并回填等级/积分/储值
        g = client.post(
            f"/api/v1/tenants/{code}/guests",
            json={"hotel_id": hid, "name": "会员甲", "phone": "13800000099"},
        ).json()
        assert g["member_id"] is not None
        assert g["member_level"] is not None
        assert g["member_points"] is not None
        assert g["member_stored_value"] is not None

    def test_checkin_keeps_member_link(self, client: TestClient) -> None:
        s = _seed(client)
        hid = int(s["hotel"]["id"])
        code = s["tenant"]["code"]
        phone = "13800000100"
        # 注册会员
        client.post(
            f"/api/v1/tenants/{code}/members",
            json={"hotel_id": hid, "name": "会员乙", "phone": phone},
        )
        # 无会员身份建档（仅手机号）→ 自动关联会员
        g = client.post(
            f"/api/v1/tenants/{code}/guests",
            json={"hotel_id": hid, "name": "散客乙", "phone": phone},
        ).json()
        assert g["member_id"] is not None
        # 入住后客档仍保留会员关联，且客史继续累计（record_stay 幂等重关联）
        booking = client.post(
            f"/api/v1/tenants/{code}/bookings",
            json={
                "hotel_id": hid,
                "room_type_id": int(s["room_type"]["id"]),
                "guest_name": "散客乙",
                "guest_phone": phone,
                "check_in_date": "2026-09-10",
                "check_out_date": "2026-09-12",
            },
        ).json()
        ci = client.post(
            f"/api/v1/tenants/{code}/bookings/{booking['id']}/check-in",
            json={"room_no": "0101", "operator": "front_desk"},
        )
        assert ci.status_code == 200
        got = client.get(f"/api/v1/tenants/{code}/guests/{g['id']}").json()
        assert got["member_id"] is not None
        assert got["member_level"] is not None
        assert got["stay_count"] >= 1
