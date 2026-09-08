"""M26 客房深度 + M27 餐饮运营深度 集成测试。

M26（客房）：批量派单/完成、多维过滤、员工清扫绩效。
M27（餐饮）：沽清拒点、退菜扣减、整单折扣（金额/百分比）、结账净额、KDS 过滤退菜。
"""

from fastapi.testclient import TestClient


def _seed(client: TestClient, code: str) -> tuple[dict, dict, dict]:
    t = client.post("/api/v1/tenants", json={"code": code, "name": "测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
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


def _book_checkin(client: TestClient, t: dict, h: dict, rt: dict, phone: str, room_no: str) -> dict:
    bk = client.post(
        f"/api/v1/tenants/{t['code']}/bookings",
        json={
            "hotel_id": h["id"],
            "room_type_id": rt["id"],
            "guest_name": f"客{phone[-2:]}",
            "guest_phone": phone,
            "check_in_date": "2026-10-01",
            "check_out_date": "2026-10-02",
            "room_no": room_no,
        },
    ).json()
    client.post(
        f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-in",
        json={"room_no": room_no},
    )
    return bk


def _book_checkin_checkout(client: TestClient, t: dict, h: dict, rt: dict, phone: str, room_no: str) -> dict:
    """入住后立即退房 → 自动生成空脏 CLEANUP 工单。"""
    bk = _book_checkin(client, t, h, rt, phone, room_no)
    r = client.post(f"/api/v1/tenants/{t['code']}/bookings/{bk['id']}/check-out", json={})
    assert r.status_code == 200, r.text
    return bk


# ================= M26 客房深度 =================


class TestHousekeepingBatchAndFilter:
    def test_batch_assign_and_done(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m26a")
        # 两间入住再退房 → 2 张自动清扫单（空脏）
        _book_checkin(client, t, h, rt, "13900020001", "0101")
        bk2 = _book_checkin(client, t, h, rt, "13900020002", "0102")
        client.post(f"/api/v1/tenants/{t['code']}/bookings/{bk2['id']}/check-out", json={})
        tasks = client.get(
            f"/api/v1/tenants/{t['code']}/housekeeping-tasks",
            params={"hotel_id": h["id"], "status": "PENDING"},
        ).json()
        assert len(tasks) >= 1
        ids = [x["id"] for x in tasks]

        # 批量派单
        r = client.post(
            f"/api/v1/tenants/{t['code']}/housekeeping-tasks/batch-assign",
            json={"task_ids": ids, "assignee": "阿姨王"},
        )
        assert r.status_code == 200, r.text
        assert len(r.json()["assigned"]) == len(ids)

        # 批量完成 → M32 后进入待检查（房态不放行）
        r2 = client.post(
            f"/api/v1/tenants/{t['code']}/housekeeping-tasks/batch-done",
            json={"task_ids": ids},
        )
        assert r2.status_code == 200, r2.text
        assert len(r2.json()["done"]) == len(ids)
        rooms = client.get(f"/api/v1/tenants/{t['code']}/rooms").json()
        st = {x["room_no"]: x["state"] for x in rooms}
        assert st["0102"] != "vacant_clean"
        # 主管逐间检查通过 → 空净可售（M32 验收 #39）
        for tid in ids:
            r3 = client.post(
                f"/api/v1/tenants/{t['code']}/housekeeping-tasks/{tid}/inspect",
                json={"passed": True, "operator": "主管"},
            )
            assert r3.status_code == 200, r3.text
        rooms = client.get(f"/api/v1/tenants/{t['code']}/rooms").json()
        st = {x["room_no"]: x["state"] for x in rooms}
        assert st["0102"] == "vacant_clean"

        # 完成后再派 → 失败明细
        r3 = client.post(
            f"/api/v1/tenants/{t['code']}/housekeeping-tasks/batch-assign",
            json={"task_ids": ids, "assignee": "李阿姨"},
        )
        assert len(r3.json()["failed"]) == len(ids)

    def test_filter_by_type_assignee_floor(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m26b")
        _book_checkin_checkout(client, t, h, rt, "13900020003", "0101")
        tasks = client.get(
            f"/api/v1/tenants/{t['code']}/housekeeping-tasks",
            params={"hotel_id": h["id"]},
        ).json()
        tid = tasks[0]["id"]
        client.post(
            f"/api/v1/tenants/{t['code']}/housekeeping-tasks/{tid}/assign",
            json={"assignee": "张阿姨"},
        )
        r = client.get(
            f"/api/v1/tenants/{t['code']}/housekeeping-tasks",
            params={"hotel_id": h["id"], "assignee": "张阿姨", "task_type": "CLEANUP"},
        )
        rows = r.json()
        assert rows and all(x["assignee"] == "张阿姨" for x in rows)
        # 楼层过滤：2 层无工单
        r2 = client.get(
            f"/api/v1/tenants/{t['code']}/housekeeping-tasks",
            params={"hotel_id": h["id"], "floor": "2"},
        )
        assert r2.json() == []


class TestStaffPerformance:
    def test_performance_stats(self, client: TestClient) -> None:
        t, h, rt = _seed(client, "m26c")
        _book_checkin_checkout(client, t, h, rt, "13900020004", "0101")
        tasks = client.get(
            f"/api/v1/tenants/{t['code']}/housekeeping-tasks",
            params={"hotel_id": h["id"], "status": "PENDING"},
        ).json()
        tid = tasks[0]["id"]
        client.post(
            f"/api/v1/tenants/{t['code']}/housekeeping-tasks/{tid}/assign",
            json={"assignee": "绩效阿姨"},
        )
        client.post(f"/api/v1/tenants/{t['code']}/housekeeping-tasks/{tid}/done")
        # M32：待检查 → 主管通过后才计入绩效（done_at 落在检查时刻）
        client.post(
            f"/api/v1/tenants/{t['code']}/housekeeping-tasks/{tid}/inspect",
            json={"passed": True, "operator": "主管"},
        )
        r = client.get(
            f"/api/v1/tenants/{t['code']}/analytics/housekeeping-performance",
            params={"hotel_id": h["id"]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        staff = {s["assignee"]: s for s in body["staff"]}
        assert "绩效阿姨" in staff
        assert staff["绩效阿姨"]["done_count"] >= 1
        assert staff["绩效阿姨"]["avg_minutes"] >= 0


# ================= M27 餐饮运营深度 =================


def _fnb_setup(client: TestClient, code: str) -> tuple[dict, dict, dict, dict, dict]:
    t, h, rt = _seed(client, code)
    menu = client.post(
        f"/api/v1/tenants/{t['code']}/fnb/menu-items",
        json={"hotel_id": h["id"], "name": "宫保鸡丁", "category": "热菜", "price_cents": 3200},
    ).json()
    table = client.post(
        f"/api/v1/tenants/{t['code']}/fnb/tables",
        json={"hotel_id": h["id"], "table_no": "T01", "seats": 4},
    ).json()
    order = client.post(
        f"/api/v1/tenants/{t['code']}/fnb/orders",
        json={"hotel_id": h["id"], "table_id": table["id"], "guest_name": "餐客"},
    ).json()
    return t, h, rt, menu, order


def _add_item(client: TestClient, t: dict, order: dict, menu: dict, qty: int):
    """按菜单价加菜（name/unit_price 为必填，价格取自菜单）。"""
    return client.post(
        f"/api/v1/tenants/{t['code']}/fnb/orders/{order['id']}/items",
        json={
            "item_id": menu["id"],
            "name": menu["name"],
            "unit_price_cents": menu["price_cents"],
            "qty": qty,
        },
    )


class TestSoldOut:
    def test_sold_out_rejects_ordering(self, client: TestClient) -> None:
        t, h, rt, menu, order = _fnb_setup(client, "m27a")
        r = client.post(
            f"/api/v1/tenants/{t['code']}/fnb/menu-items/{menu['id']}/sold-out",
            json={"sold_out": True},
        )
        assert r.status_code == 200, r.text
        assert r.json()["sold_out"] == 1
        r2 = client.post(
            f"/api/v1/tenants/{t['code']}/fnb/orders/{order['id']}/items",
            json={"item_id": menu["id"], "name": menu["name"], "unit_price_cents": menu["price_cents"], "qty": 1},
        )
        assert r2.status_code == 409
        # 恢复供应后可点
        client.post(
            f"/api/v1/tenants/{t['code']}/fnb/menu-items/{menu['id']}/sold-out",
            json={"sold_out": False},
        )
        r3 = client.post(
            f"/api/v1/tenants/{t['code']}/fnb/orders/{order['id']}/items",
            json={"item_id": menu["id"], "name": menu["name"], "unit_price_cents": menu["price_cents"], "qty": 2},
        )
        assert r3.status_code == 201, r3.text


class TestVoidItem:
    def test_void_deducts_and_blocks_settled(self, client: TestClient) -> None:
        t, h, rt, menu, order = _fnb_setup(client, "m27b")
        line = client.post(
            f"/api/v1/tenants/{t['code']}/fnb/orders/{order['id']}/items",
            json={"item_id": menu["id"], "name": menu["name"], "unit_price_cents": menu["price_cents"], "qty": 3},
        ).json()
        # 退 1 行（3 份 9600）
        r = client.post(
            f"/api/v1/tenants/{t['code']}/fnb/orders/{order['id']}/items/{line['id']}/void",
            json={"reason": "客人不吃辣"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_cents"] == 0
        assert body["items"][0]["voided"] == 1
        assert body["items"][0]["void_reason"] == "客人不吃辣"
        # 重复退 → 409
        r2 = client.post(
            f"/api/v1/tenants/{t['code']}/fnb/orders/{order['id']}/items/{line['id']}/void",
            json={},
        )
        assert r2.status_code == 409


class TestOrderDiscount:
    def test_discount_percent_and_cash_net(self, client: TestClient) -> None:
        t, h, rt, menu, order = _fnb_setup(client, "m27c")
        client.post(
            f"/api/v1/tenants/{t['code']}/fnb/orders/{order['id']}/items",
            json={"item_id": menu["id"], "name": menu["name"], "unit_price_cents": menu["price_cents"], "qty": 1},
        )  # 3200
        r = client.post(
            f"/api/v1/tenants/{t['code']}/fnb/orders/{order['id']}/discount",
            json={"percent": 10},
        )
        assert r.status_code == 200, r.text
        assert r.json()["discount_cents"] == 320
        # 现金结账按净额 2880
        r2 = client.post(
            f"/api/v1/tenants/{t['code']}/fnb/orders/{order['id']}/settle-cash",
            json={"operator": "fnb"},
        )
        assert r2.status_code == 200, r2.text
        bills = client.get(f"/api/v1/tenants/{t['code']}/bills?source=FNB").json()
        assert bills[0]["balance"] == 0  # 已平账
        settled_bill = bills[0]
        charge = next(i for i in settled_bill["items"] if i["type"] == "FNB")
        assert charge["amount"] == 2880  # 净额入账

    def test_discount_amount_and_over_limit(self, client: TestClient) -> None:
        t, h, rt, menu, order = _fnb_setup(client, "m27d")
        client.post(
            f"/api/v1/tenants/{t['code']}/fnb/orders/{order['id']}/items",
            json={"item_id": menu["id"], "name": menu["name"], "unit_price_cents": menu["price_cents"], "qty": 1},
        )
        # 超总额折扣 → 409
        r = client.post(
            f"/api/v1/tenants/{t['code']}/fnb/orders/{order['id']}/discount",
            json={"discount_cents": 99999},
        )
        assert r.status_code == 409
        # 金额折扣
        r2 = client.post(
            f"/api/v1/tenants/{t['code']}/fnb/orders/{order['id']}/discount",
            json={"discount_cents": 200},
        )
        assert r2.json()["discount_cents"] == 200

    def test_void_respects_discount_cap(self, client: TestClient) -> None:
        t, h, rt, menu, order = _fnb_setup(client, "m27e")
        line = client.post(
            f"/api/v1/tenants/{t['code']}/fnb/orders/{order['id']}/items",
            json={"item_id": menu["id"], "name": menu["name"], "unit_price_cents": menu["price_cents"], "qty": 1},
        ).json()
        client.post(
            f"/api/v1/tenants/{t['code']}/fnb/orders/{order['id']}/discount",
            json={"percent": 50},
        )  # 1600
        client.post(
            f"/api/v1/tenants/{t['code']}/fnb/orders/{order['id']}/items/{line['id']}/void",
            json={},
        )  # 总额清零 → 折扣同步归零
        r = client.get(
            f"/api/v1/tenants/{t['code']}/fnb/orders?hotel_id={h['id']}&status=open"
        )
        body = r.json()[0]
        assert body["total_cents"] == 0
        assert body["discount_cents"] == 0
