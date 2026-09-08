"""M21 餐饮 POS（F&B）测试：菜品/餐桌/开单点菜/两类结账/列表 + 权限守卫。

功能测试依赖 conftest 的 ``auth_bypass``（视为该租户默认管理员已登录，
拥有 FNB_MANAGE），聚焦业务流；权限守卫用例用 ``@pytest.mark.auth``
退出旁路，验证认证层（401）与授权层（403/200）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

ADMIN = {"username": "admin", "password": "admin123"}


# ---------- 功能测试（admin 旁路） ----------

def _seed(client: TestClient, code: str = "fnb") -> dict:
    """开通租户 + 建门店，返回 {tenant_code, hotel_id}。"""
    client.post("/api/v1/tenants", json={"code": code, "name": "餐饮测试"})
    h = client.post(
        f"/api/v1/tenants/{code}/hotels",
        json={"code": "H1", "name": "一号店"},
    ).json()
    return {"tenant": code, "hotel_id": h["id"]}


def test_menu_item_crud_and_list(client: TestClient) -> None:
    """菜品新增 / 列表（默认仅上架）/ 上下架切换。"""
    d = _seed(client)
    # 新增
    r = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/menu-items",
        json={"hotel_id": d["hotel_id"], "name": "宫保鸡丁", "category": "热菜", "price_cents": 3800},
    )
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["name"] == "宫保鸡丁"
    assert item["price_cents"] == 3800
    assert item["is_active"] == 1

    # 列表默认仅上架
    r = client.get(
        f"/api/v1/tenants/{d['tenant']}/fnb/menu-items",
        params={"hotel_id": d["hotel_id"]},
    )
    assert r.status_code == 200
    assert any(i["name"] == "宫保鸡丁" for i in r.json())

    # 下架
    r = client.patch(
        f"/api/v1/tenants/{d['tenant']}/fnb/menu-items/{item['id']}",
        json={"is_active": 0},
    )
    assert r.status_code == 200
    assert r.json()["is_active"] == 0

    # 仅上架列表不再出现，全量列表出现
    r = client.get(
        f"/api/v1/tenants/{d['tenant']}/fnb/menu-items",
        params={"hotel_id": d["hotel_id"], "active_only": True},
    )
    assert not any(i["name"] == "宫保鸡丁" for i in r.json())
    r = client.get(
        f"/api/v1/tenants/{d['tenant']}/fnb/menu-items",
        params={"hotel_id": d["hotel_id"], "active_only": False},
    )
    assert any(i["name"] == "宫保鸡丁" for i in r.json())


def test_table_lifecycle_and_invalid_state(client: TestClient) -> None:
    """餐桌新增 → 状态流转（free→occupied→cleaning→free）；非法状态 409。"""
    d = _seed(client)
    r = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/tables",
        json={"hotel_id": d["hotel_id"], "table_no": "A1", "seats": 4, "zone": "大厅"},
    )
    assert r.status_code == 201, r.text
    table_id = r.json()["id"]
    assert r.json()["state"] == "free"

    for st in ("occupied", "cleaning", "free"):
        r = client.patch(
            f"/api/v1/tenants/{d['tenant']}/fnb/tables/{table_id}/state",
            params={"state": st},
        )
        assert r.status_code == 200, r.text
        assert r.json()["state"] == st

    r = client.patch(
        f"/api/v1/tenants/{d['tenant']}/fnb/tables/{table_id}/state",
        params={"state": "bogus"},
    )
    assert r.status_code == 409


def test_open_order_add_items_cash_settle(client: TestClient) -> None:
    """开单 → 加菜 → 现金结账：金额累计、餐桌释放、入账到 Bill。"""
    d = _seed(client)
    table = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/tables",
        json={"hotel_id": d["hotel_id"], "table_no": "B2", "seats": 2},
    ).json()

    # 开单（占用餐桌）
    r = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders",
        json={"hotel_id": d["hotel_id"], "table_id": table["id"], "guest_name": "张三"},
    )
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["status"] == "open"

    # 加菜两道
    client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/items",
        json={"name": "宫保鸡丁", "qty": 1, "unit_price_cents": 3800},
    )
    r = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/items",
        json={"name": "米饭", "qty": 2, "unit_price_cents": 300},
    )
    assert r.status_code == 201, r.text
    assert r.json()["subtotal_cents"] == 600  # 2*300

    # 现金结账
    r = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/settle-cash",
        json={},
    )
    assert r.status_code == 200, r.text
    settled = r.json()
    assert settled["status"] == "settled"
    assert settled["settle_type"] == "cash"
    assert settled["total_cents"] == 4400  # 3800 + 600
    assert len(settled["items"]) == 2

    # 餐桌释放为 cleaning
    r = client.get(
        f"/api/v1/tenants/{d['tenant']}/fnb/tables",
        params={"hotel_id": d["hotel_id"]},
    )
    tbl = next(t for t in r.json() if t["id"] == table["id"])
    assert tbl["state"] == "cleaning"

    # 餐饮消费确实入账到 Bill（CashierService 财务口径）
    r = client.get(
        f"/api/v1/tenants/{d['tenant']}/bills",
        params={"source": "FNB"},
    )
    assert r.status_code == 200
    fnb_bills = r.json()
    assert len(fnb_bills) == 1
    bill = fnb_bills[0]
    assert bill["status"] == "SETTLED"
    assert bill["balance"] == 0
    assert bill["items"][0]["type"] == "FNB"
    assert bill["items"][0]["amount"] == 4400


def test_room_settle_posts_to_guest_bill(client: TestClient) -> None:
    """挂房账结账：消费计入客房在开账单（保持 OPEN），餐桌释放。"""
    d = _seed(client)
    table = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/tables",
        json={"hotel_id": d["hotel_id"], "table_no": "C3", "seats": 6},
    ).json()

    r = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders",
        json={"hotel_id": d["hotel_id"], "table_id": table["id"], "room_no": "0808", "guest_name": "李四"},
    )
    assert r.status_code == 201, r.text
    order = r.json()
    client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/items",
        json={"name": "啤酒", "qty": 3, "unit_price_cents": 1500},
    )

    r = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/settle-room",
        json={"room_no": "0808"},
    )
    assert r.status_code == 200, r.text
    settled = r.json()
    assert settled["status"] == "settled"
    assert settled["settle_type"] == "room"
    assert settled["room_no"] == "0808"
    assert settled["total_cents"] == 4500

    # 挂房账保持 OPEN（随房账退房时结）
    r = client.get(
        f"/api/v1/tenants/{d['tenant']}/bills",
        params={"source": "FNB"},
    )
    bill = r.json()[0]
    assert bill["status"] == "OPEN"
    assert bill["room_no"] == "0808"
    assert bill["items"][0]["amount"] == 4500


def test_list_orders_and_status_filter(client: TestClient) -> None:
    """餐饮账单列表 + 状态过滤。"""
    d = _seed(client)
    r1 = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders",
        json={"hotel_id": d["hotel_id"], "guest_name": "单A"},
    ).json()
    r2 = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders",
        json={"hotel_id": d["hotel_id"], "guest_name": "单B"},
    ).json()
    client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{r1['id']}/items",
        json={"name": "可乐", "qty": 1, "unit_price_cents": 800},
    )
    client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{r1['id']}/settle-cash", json={}
    )

    r = client.get(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders",
        params={"hotel_id": d["hotel_id"]},
    )
    assert r.status_code == 200
    assert len(r.json()) == 2

    r = client.get(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders",
        params={"hotel_id": d["hotel_id"], "status": "settled"},
    )
    ids = [o["id"] for o in r.json()]
    assert r1["id"] in ids and r2["id"] not in ids


def test_settle_zero_total_rejected(client: TestClient) -> None:
    """金额为 0 不可结账。"""
    d = _seed(client)
    order = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders",
        json={"hotel_id": d["hotel_id"]},
    ).json()
    client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/items",
        json={"name": "赠品", "qty": 1, "unit_price_cents": 0},
    )
    r = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/settle-cash", json={}
    )
    assert r.status_code == 409


def test_add_item_after_settle_rejected(client: TestClient) -> None:
    """已结账账单不可再加菜。"""
    d = _seed(client)
    order = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders",
        json={"hotel_id": d["hotel_id"]},
    ).json()
    client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/items",
        json={"name": "咖啡", "qty": 1, "unit_price_cents": 2500},
    )
    client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/settle-cash", json={}
    )
    r = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/items",
        json={"name": "蛋糕", "qty": 1, "unit_price_cents": 3000},
    )
    assert r.status_code == 409


def test_fnb_report_sales(client: TestClient) -> None:
    """餐饮报表：总营收 / 单数 / 品类销售 / 桌均消费聚合正确。"""
    d = _seed(client)
    # 菜品（带品类，用于验证品类销售冗余字段）
    mi = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/menu-items",
        json={"hotel_id": d["hotel_id"], "name": "宫保鸡丁", "category": "热菜", "price_cents": 3800},
    ).json()
    table = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/tables",
        json={"hotel_id": d["hotel_id"], "table_no": "A1", "seats": 4},
    ).json()

    # 开台 → 点菜单品（带 category）+ 手动菜（兜底"其他"）
    order = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders",
        json={"hotel_id": d["hotel_id"], "table_id": table["id"]},
    ).json()
    client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/items",
        json={"name": "宫保鸡丁", "qty": 1, "unit_price_cents": 3800, "item_id": mi["id"]},
    )
    client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/items",
        json={"name": "米饭", "qty": 2, "unit_price_cents": 300},  # 手动，category=其他
    )
    # 现金结账（报表仅统计 settled）
    r = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/settle-cash", json={}
    )
    assert r.status_code == 200

    # 取报表
    r = client.get(
        f"/api/v1/tenants/{d['tenant']}/fnb/reports/sales",
        params={"hotel_id": d["hotel_id"]},
    )
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["total_revenue_cents"] == 4400  # 3800 + 600
    assert rep["order_count"] == 1
    assert rep["item_count"] == 3
    # 品类销售
    by_cat = {c["category"]: c for c in rep["by_category"]}
    assert by_cat["热菜"]["qty"] == 1 and by_cat["热菜"]["revenue_cents"] == 3800
    assert by_cat["其他"]["qty"] == 2 and by_cat["其他"]["revenue_cents"] == 600
    # 桌均消费（仅 1 桌）
    assert rep["avg_per_table_cents"] == 4400
    tbl = next(t for t in rep["by_table"] if t["table_no"] == "A1")
    assert tbl["order_count"] == 1 and tbl["revenue_cents"] == 4400

    # 未结账账单不计入报表
    client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders",
        json={"hotel_id": d["hotel_id"]},
    )
    r = client.get(
        f"/api/v1/tenants/{d['tenant']}/fnb/reports/sales",
        params={"hotel_id": d["hotel_id"]},
    )
    assert r.json()["order_count"] == 1  # 仍只 1 单 settled


def test_kds_ticket_flow(client: TestClient) -> None:
    """厨房出单：取待做票 → 出餐(ready) → 上菜(served)，served 后退出默认列表。"""
    d = _seed(client)
    order = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders",
        json={"hotel_id": d["hotel_id"], "table_id": None, "guest_name": "王五"},
    ).json()
    i1 = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/items",
        json={"name": "牛排", "qty": 1, "unit_price_cents": 8800},
    ).json()
    i2 = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/items",
        json={"name": "沙拉", "qty": 1, "unit_price_cents": 2200},
    ).json()
    assert i1["kds_status"] == "pending"
    assert i2["kds_status"] == "pending"

    # 出单屏默认取 pending|ready
    r = client.get(
        f"/api/v1/tenants/{d['tenant']}/fnb/kitchen/tickets",
        params={"hotel_id": d["hotel_id"]},
    )
    assert r.status_code == 200
    ids = {t["item_id"]: t for t in r.json()}
    assert i1["id"] in ids and i2["id"] in ids

    # 牛排出餐
    r = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/items/{i1['id']}/ready"
    )
    assert r.status_code == 200 and r.json()["kds_status"] == "ready"

    # 牛排上菜
    r = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/orders/{order['id']}/items/{i1['id']}/served"
    )
    assert r.status_code == 200 and r.json()["kds_status"] == "served"

    # 默认列表（pending|ready）不再含已上菜
    r = client.get(
        f"/api/v1/tenants/{d['tenant']}/fnb/kitchen/tickets",
        params={"hotel_id": d["hotel_id"]},
    )
    ids = [t["item_id"] for t in r.json()]
    assert i1["id"] not in ids and i2["id"] in ids  # 牛排已 served 退出；沙拉仍在

    # 取全部（含 served）可看到牛排
    r = client.get(
        f"/api/v1/tenants/{d['tenant']}/fnb/kitchen/tickets",
        params={"hotel_id": d["hotel_id"], "states": "served"},
    )
    assert i1["id"] in [t["item_id"] for t in r.json()]


# ---------- 权限守卫（仅本组用例退出 admin 旁路，验证认证/授权层） ----------


def _seed_with_admin(client: TestClient, code: str) -> dict:
    """公开开通租户，用管理员登录并建门店，返回 admin token 与 hotel_id。"""
    client.post("/api/v1/tenants", json={"code": code, "name": "餐饮鉴权"})
    token = client.post(
        f"/api/v1/tenants/{code}/auth/login", json=ADMIN
    ).json()["token"]
    auth = {"Authorization": f"Bearer {token}"}
    h = client.post(
        f"/api/v1/tenants/{code}/hotels",
        json={"code": "H1", "name": "一号店"},
        headers=auth,
    ).json()
    return {"tenant": code, "auth": auth, "hotel_id": h["id"]}


def _user_token(client: TestClient, code: str, auth: dict, username: str, role_name: str | None, hotel_id: int | None = None) -> str:
    """建用户并（可选）绑定某默认/自定义角色，返回其登录 token。

    酒店级角色（如前台）必须传 ``hotel_id`` 才会对该门店授予权限。
    """
    u = client.post(
        f"/api/v1/tenants/{code}/users",
        json={"username": username, "password": "pw123456"},
        headers=auth,
    ).json()
    if role_name is not None:
        roles = client.get(f"/api/v1/tenants/{code}/roles", headers=auth).json()
        role = next(r for r in roles if r["name"] == role_name)
        client.post(
            f"/api/v1/tenants/{code}/users/{u['id']}/roles",
            json={"role_id": role["id"], "hotel_id": hotel_id},
            headers=auth,
        )
    return client.post(
        f"/api/v1/tenants/{code}/auth/login",
        json={"username": username, "password": "pw123456"},
    ).json()["token"]


@pytest.mark.auth
def test_fnb_requires_authentication(client: TestClient) -> None:
    """无 token → 401（认证层生效）。"""
    _seed_with_admin(client, "fnbauth")
    r = client.post(
        "/api/v1/tenants/fnbauth/fnb/menu-items",
        json={"hotel_id": 1, "name": "x", "price_cents": 100},
    )
    assert r.status_code == 401


@pytest.mark.auth
def test_front_desk_with_fnb_allowed(client: TestClient) -> None:
    """前台（含 FNB_MANAGE）可开菜品。"""
    d = _seed_with_admin(client, "fnbfd")
    token = _user_token(client, "fnbfd", d["auth"], "desk", "前台", d["hotel_id"])
    r = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/menu-items",
        json={"hotel_id": d["hotel_id"], "name": "酸辣汤", "price_cents": 1800},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text


@pytest.mark.auth
def test_user_without_fnb_denied(client: TestClient) -> None:
    """自定义无 FNB_MANAGE 角色 → 403（授权层生效）。"""
    d = _seed_with_admin(client, "fnbdeny")
    # 建一个空权限自定义角色
    role = client.post(
        f"/api/v1/tenants/{d['tenant']}/roles",
        json={"name": "viewer", "level": "STAFF", "permissions": []},
        headers=d["auth"],
    ).json()
    u = client.post(
        f"/api/v1/tenants/{d['tenant']}/users",
        json={"username": "viewer1", "password": "pw123456"},
        headers=d["auth"],
    ).json()
    client.post(
        f"/api/v1/tenants/{d['tenant']}/users/{u['id']}/roles",
        json={"role_id": role["id"], "hotel_id": None},
        headers=d["auth"],
    )
    token = client.post(
        f"/api/v1/tenants/{d['tenant']}/auth/login",
        json={"username": "viewer1", "password": "pw123456"},
    ).json()["token"]
    r = client.post(
        f"/api/v1/tenants/{d['tenant']}/fnb/menu-items",
        json={"hotel_id": d["hotel_id"], "name": "x", "price_cents": 100},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403
