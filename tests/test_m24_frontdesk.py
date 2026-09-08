"""M24 前台深度 II 集成测试（验收清单 #1 / #5 / #10）。

覆盖：
- 协议单位挂账月结：建户 → 账单挂账（COMPANY）→ 欠款累计 → 还款冲减 → 信用额度拦截
- 时租房：stay_type=hourly 按小时计价；夜审跳过时租房房租过账
- 智能排房：房态过滤 + 空净优先 + 历史偏好加分
"""

from fastapi.testclient import TestClient


def _seed(client: TestClient, code: str = "m24") -> tuple[dict, dict, dict]:
    t = client.post("/api/v1/tenants", json={"code": code, "name": "M24测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000, "hourly_rate": 5000},
    ).json()
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[
            {"room_type_id": rt["id"], "room_no": "0101", "floor": "1"},
            {"room_type_id": rt["id"], "room_no": "0102", "floor": "1"},
            {"room_type_id": rt["id"], "room_no": "0201", "floor": "2"},
        ],
    )
    return t, h, rt


def _make_open_bill(client: TestClient, t: dict, h: dict, amount: int = 8000) -> dict:
    bill = client.post(
        f"/api/v1/tenants/{t['code']}/bills",
        json={"hotel_id": h["id"], "guest_name": "协议客"},
    ).json()
    client.post(
        f"/api/v1/tenants/{t['code']}/bills/{bill['id']}/charges",
        json={"charge_type": "ROOM_CHARGE", "amount": amount, "operator": "ar_test"},
    )
    return bill


class TestArAccount:
    def test_charge_and_repay_flow(self, client: TestClient) -> None:
        t, h, _ = _seed(client, "m24a")
        acct = client.post(
            f"/api/v1/tenants/{t['code']}/ar-accounts",
            json={"hotel_id": h["id"], "name": "深圳华创", "credit_limit_cents": 0},
        )
        assert acct.status_code == 201, acct.text
        acct = acct.json()

        bill = _make_open_bill(client, t, h, amount=8000)
        r = client.post(
            f"/api/v1/tenants/{t['code']}/ar-accounts/{acct['id']}/charge",
            json={"bill_id": bill["id"], "operator": "ar_test"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "SETTLED"
        assert body["balance"] == 0
        assert body["ar_account_id"] == acct["id"]
        assert any(p["method"] == "COMPANY" for p in body["payments"])

        # 挂账账单可查
        bills = client.get(
            f"/api/v1/tenants/{t['code']}/ar-accounts/{acct['id']}/bills"
        ).json()
        assert [b["id"] for b in bills] == [bill["id"]]

        # 欠款 8000，还款 3000 → 余 5000
        rep = client.post(
            f"/api/v1/tenants/{t['code']}/ar-accounts/{acct['id']}/repayments",
            json={"amount": 3000, "method": "BANK", "operator": "ar_test"},
        )
        assert rep.status_code == 200, rep.text
        assert rep.json()["balance_cents"] == 5000

        # 还款超额被拒
        r2 = client.post(
            f"/api/v1/tenants/{t['code']}/ar-accounts/{acct['id']}/repayments",
            json={"amount": 999999},
        )
        assert r2.status_code == 400

    def test_credit_limit_blocks_overcharge(self, client: TestClient) -> None:
        t, h, _ = _seed(client, "m24b")
        acct = client.post(
            f"/api/v1/tenants/{t['code']}/ar-accounts",
            json={"hotel_id": h["id"], "name": "限额单位", "credit_limit_cents": 10000},
        ).json()
        bill = _make_open_bill(client, t, h, amount=12000)
        r = client.post(
            f"/api/v1/tenants/{t['code']}/ar-accounts/{acct['id']}/charge",
            json={"bill_id": bill["id"]},
        )
        assert r.status_code == 409
        # 账单未被结清
        after = client.get(
            f"/api/v1/tenants/{t['code']}/bills/{bill['id']}"
        ).json()
        assert after["status"] == "OPEN"
        # 账户欠款不变
        accounts = client.get(f"/api/v1/tenants/{t['code']}/ar-accounts").json()
        assert accounts[0]["balance_cents"] == 0


class TestHourlyStay:
    def test_hourly_pricing(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m24c")
        r = client.post(
            f"/api/v1/tenants/{t['code']}/bookings",
            json={
                "hotel_id": h["id"],
                "room_type_id": rt["id"],
                "guest_name": "时租客",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-01",
                "stay_type": "hourly",
                "hourly_hours": 4,
            },
        )
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body["stay_type"] == "hourly"
        assert body["hourly_hours"] == 4
        assert body["total_price"] == 5000 * 4  # hourly_rate 5000 分/小时

    def test_hourly_requires_positive_hours(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m24d")
        r = client.post(
            f"/api/v1/tenants/{t['code']}/bookings",
            json={
                "hotel_id": h["id"],
                "room_type_id": rt["id"],
                "guest_name": "时租客",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-01",
                "stay_type": "hourly",
            },
        )
        assert r.status_code == 409  # ValueError → 409

    def test_night_audit_skips_hourly_posting(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m24e")
        bk = client.post(
            f"/api/v1/tenants/{t['code']}/bookings",
            json={
                "hotel_id": h["id"],
                "room_type_id": rt["id"],
                "guest_name": "时租过夜",
                "guest_phone": "13900005555",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-02",
                "room_no": "0101",
                "stay_type": "hourly",
                "hourly_hours": 6,
            },
        ).json()
        client.post(
            f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-in",
            json={"room_no": "0101"},
        )
        rep = client.post(
            f"/api/v1/tenants/{t['code']}/night-audit",
            json={"hotel_id": h["id"], "business_date": "2026-10-01"},
        )
        assert rep.status_code in (200, 201), rep.text
        # 时租房无账单过账（未自动开单收租）
        bills = client.get(f"/api/v1/tenants/{t['code']}/bills").json()
        room_charges = [
            i
            for b in bills
            for i in b["items"]
            if i["type"] == "ROOM_CHARGE"
        ]
        assert room_charges == []


class TestRoomRecommend:
    def test_state_filter_and_clean_first(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m24f")
        # 0102 入住 → occupied；0201 保持 vacant_clean；0101 保持 vacant_clean
        bk = client.post(
            f"/api/v1/tenants/{t['code']}/bookings",
            json={
                "hotel_id": h["id"],
                "room_type_id": rt["id"],
                "guest_name": "住客A",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-03",
                "room_no": "0102",
            },
        ).json()
        client.post(
            f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-in",
            json={"room_no": "0102"},
        )
        r = client.get(
            f"/api/v1/tenants/{t['code']}/rooms/recommend",
            params={"hotel_id": h["id"]},
        )
        assert r.status_code == 200, r.text
        rows = r.json()
        nos = [x["room_no"] for x in rows]
        assert "0102" not in nos  # 在住被排除
        assert set(nos) == {"0101", "0201"}
        assert all(x["state"] == "vacant_clean" for x in rows)

    def test_history_preference_boost(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m24g")
        # 该客人历史住过 0201（楼层 2），已退房 → 空脏（60+偏好50=110 胜空净 100）
        bk = client.post(
            f"/api/v1/tenants/{t['code']}/bookings",
            json={
                "hotel_id": h["id"],
                "room_type_id": rt["id"],
                "guest_name": "回头客",
                "guest_phone": "13900006666",
                "check_in_date": "2026-09-01",
                "check_out_date": "2026-09-02",
                "room_no": "0201",
            },
        ).json()
        client.post(
            f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-in",
            json={"room_no": "0201"},
        )
        client.post(
            f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-out",
            json={},
        )
        r = client.get(
            f"/api/v1/tenants/{t['code']}/rooms/recommend",
            params={"hotel_id": h["id"], "guest_phone": "13900006666"},
        )
        rows = r.json()
        assert rows[0]["room_no"] == "0201", rows
        assert any("历史" in reason for x in rows for reason in x["reasons"])

    def test_dirty_ranked_after_clean(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m24h")
        # 把 0201 弄脏（入住再退房 → vacant_dirty）
        bk = client.post(
            f"/api/v1/tenants/{t['code']}/bookings",
            json={
                "hotel_id": h["id"],
                "room_type_id": rt["id"],
                "guest_name": "退房客",
                "check_in_date": "2026-10-01",
                "check_out_date": "2026-10-02",
                "room_no": "0201",
            },
        ).json()
        client.post(
            f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-in",
            json={"room_no": "0201"},
        )
        client.post(
            f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-out",
            json={},
        )
        r = client.get(
            f"/api/v1/tenants/{t['code']}/rooms/recommend",
            params={"hotel_id": h["id"], "limit": 5},
        )
        rows = r.json()
        assert rows[0]["state"] == "vacant_clean"
        dirty = [x for x in rows if x["state"] == "vacant_dirty"]
        assert dirty and dirty[0]["room_no"] == "0201"
        assert any("清扫" in reason for reason in dirty[0]["reasons"])
