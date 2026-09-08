"""M23 前台运营深度集成测试（验收清单 #3 / #4 / #11）。

覆盖：
- NoShow：前台手动标记端点 + 夜审自动标记（含锁房释放）
- 客人检索：证件号 / 订单号 维度
- 交班三口径：现金流 / 实收（全方式）/ 应收（正向条目）
"""

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> tuple[dict, dict, dict]:
    t = client.post("/api/v1/tenants", json={"code": "m23", "name": "M23测试"}).json()
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


def _room_state(client: TestClient, t: dict, room_no: str) -> str:
    rooms = client.get(f"/api/v1/tenants/{t['code']}/rooms").json()
    return next(r["state"] for r in rooms if r["room_no"] == room_no)


class TestNoshow:
    def test_manual_noshow_releases_locked_room(self, client: TestClient) -> None:
        t, h, rt = _seed(client)
        bk = client.post(
            f"/api/v1/tenants/{t['code']}/bookings",
            json={
                "hotel_id": h["id"],
                "room_type_id": rt["id"],
                "guest_name": "张三",
                "guest_phone": "13800001111",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-02",
                "room_no": "0101",
            },
        ).json()
        # 预分配锁房生效
        assert _room_state(client, t, "0101") == "arrival_locked"

        r = client.post(
            f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/noshow",
            json={"reason": "客人来电告知无法到店"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "noshow"
        assert body["noshow_reason"] == "客人来电告知无法到店"
        # 锁房释放为空净可售
        assert _room_state(client, t, "0101") == "vacant_clean"

    def test_noshow_rejected_on_non_created(self, client: TestClient) -> None:
        t, h, rt = _seed(client)
        bk = client.post(
            f"/api/v1/tenants/{t['code']}/bookings",
            json={
                "hotel_id": h["id"],
                "room_type_id": rt["id"],
                "guest_name": "李四",
                "guest_phone": "13800002222",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-02",
                "room_no": "0102",
            },
        ).json()
        client.post(
            f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-in",
            json={"room_no": "0102"},
        )
        r = client.post(
            f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/noshow",
            json={"reason": "误操作"},
        )
        assert r.status_code == 409

    def test_night_audit_auto_noshow(self, client: TestClient) -> None:
        t, h, rt = _seed(client)
        # 应到 10-01，至 10-02 夜审仍未入住 → 自动 NoShow
        bk = client.post(
            f"/api/v1/tenants/{t['code']}/bookings",
            json={
                "hotel_id": h["id"],
                "room_type_id": rt["id"],
                "guest_name": "王五",
                "guest_phone": "13800003333",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-02",
                "room_no": "0101",
            },
        ).json()
        assert _room_state(client, t, "0101") == "arrival_locked"

        rep = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-02"},
        )
        assert rep.status_code in (200, 201), rep.text

        detail = client.get(f"/api/v1/tenants/{t['code']}/bookings").json()
        target = next(b for b in detail if b["id"] == bk["id"])
        assert target["status"] == "noshow"
        assert "逾期未到" in (target.get("noshow_reason") or "")
        assert "2026-10-01" in (target.get("noshow_reason") or "")
        # 锁房已由夜审释放
        assert _room_state(client, t, "0101") == "vacant_clean"
        # 快照记录 noshow 数
        reports = client.get(f"/api/v1/tenants/{t['code']}/daily-reports").json()
        snapshot = reports[0]["snapshot"]
        assert isinstance(snapshot, str) and '"count": 1' in snapshot


class TestGuestSearch:
    def test_search_by_id_no(self, client: TestClient) -> None:
        t, h, _ = _seed(client)
        client.post(
            f"/api/v1/tenants/{t['code']}/guests",
            json={
                "hotel_id": h["id"],
                "name": "张三",
                "phone": "13800001111",
                "id_no": "440301199001011234",
            },
        )
        r = client.get(
            f"/api/v1/tenants/{t['code']}/guests/search",
            params={"id_no": "440301199001011234"},
        )
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1 and rows[0]["name"] == "张三"

    def test_search_by_booking_id(self, client: TestClient) -> None:
        t, h, rt = _seed(client)
        # 先建档再建预订（同手机号自动关联）
        client.post(
            f"/api/v1/tenants/{t['code']}/guests",
            json={
                "hotel_id": h["id"],
                "name": "赵六",
                "phone": "13800004444",
                "id_no": "440301199001015678",
            },
        )
        bk = client.post(
            f"/api/v1/tenants/{t['code']}/bookings",
            json={
                "hotel_id": h["id"],
                "room_type_id": rt["id"],
                "guest_name": "赵六",
                "guest_phone": "13800004444",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-02",
            },
        ).json()
        r = client.get(
            f"/api/v1/tenants/{t['code']}/guests/search",
            params={"booking_id": bk["id"]},
        )
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) == 1 and rows[0]["name"] == "赵六"

    def test_search_requires_at_least_one(self, client: TestClient) -> None:
        t, _, _ = _seed(client)
        r = client.get(f"/api/v1/tenants/{t['code']}/guests/search")
        assert r.status_code == 400


class TestShiftThreeModes:
    def test_cash_received_receivable(self, client: TestClient) -> None:
        t, h, _ = _seed(client)
        shift = client.post(
            f"/api/v1/tenants/{t['code']}/shifts/open",
            json={"hotel_id": h["id"], "cashier": "erin", "opening_float_cents": 0},
        ).json()
        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills",
            json={"hotel_id": h["id"], "guest_name": "Z"},
        ).json()
        # 班内应收 12000（erin 加账）
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "ROOM_CHARGE", "amount": 12000, "operator": "erin"},
        )
        # 班内实收 12000 = 现金 8000 + 微信 4000
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/payments",
            json={"method": "CASH", "amount": 8000, "operator": "erin"},
        )
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/payments",
            json={"method": "WECHAT", "amount": 4000, "operator": "erin"},
        )
        closed = client.post(
            f"/api/v1/tenants/{t['code']}/shifts/{shift['id']}/close",
            json={"counted_cash_cents": 8000},
        ).json()
        # 现金流口径
        assert closed["expected_cash_cents"] == 8000
        assert closed["discrepancy_cents"] == 0
        # 三口径
        assert closed["received_cents"] == 12000  # 全支付方式
        assert closed["receivable_cents"] == 12000  # 正向应收条目

    def test_receivable_excludes_negative_and_other_cashier(self, client: TestClient) -> None:
        t, h, _ = _seed(client)
        shift = client.post(
            f"/api/v1/tenants/{t['code']}/shifts/open",
            json={"hotel_id": h["id"], "cashier": "frank", "opening_float_cents": 0},
        ).json()
        bill = client.post(
            f"/api/v1/tenants/{t['code']}/bills",
            json={"hotel_id": h["id"], "guest_name": "Z"},
        ).json()
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "ROOM_CHARGE", "amount": 10000, "operator": "frank"},
        )
        # frank 的折扣冲减不计应收
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "DISCOUNT", "amount": -2000, "operator": "frank"},
        )
        # 他人加账不计 frank 班次
        client.post(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
            json={"charge_type": "MISC", "amount": 5000, "operator": "someone_else"},
        )
        closed = client.post(
            f"/api/v1/tenants/{t['code']}/shifts/{shift['id']}/close",
            json={"counted_cash_cents": 0},
        ).json()
        assert closed["receivable_cents"] == 10000
        assert closed["received_cents"] == 0
