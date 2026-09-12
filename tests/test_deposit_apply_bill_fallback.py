"""冲抵目标账单兜底（deposit 未绑账单时回退到订单在开账单）。

背景
----
UI 侧两个冲抵入口（入住登记页「押金/预授权」快捷面板、押金管理页）在开押时
**都不采集账单**，创建押金只带 ``booking_id`` + ``room_no``；冲抵时又固定传
``target_bill_id = null``。而 ``DepositService.apply`` 原本只认
``target_bill_id or d.bill_id``，两者皆空就直接 ``DEPOSIT_BILL_REQUIRED``。

结果：**冲抵在 UI 上 100% 失败**（端到端 UI 复测 C10/C11 实测命中）。
接口层单测因为都显式传了 ``bill_id`` 建押，从未覆盖这条路径。

修复
----
``apply`` 在两者皆空且 ``d.booking_id`` 存在时，回退到该订单的在开(OPEN)账单。
业务上「押金冲抵」就是抵这位客人的账，这是唯一合理的默认值。

不变量
------
- 兜底只用于本次冲抵，**不回写** ``d.bill_id`` —— ``bill_id`` 可空是为支持
  跨账单冲抵，写死会毁掉这个能力；
- 无 ``booking_id`` 或订单确实没有在开账单时，**仍然必须报错**，不能静默放行
  （否则钱就凭空消失在账外）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _seed(client: TestClient) -> dict:
    """租户 + 门店 + 房型 + 房间 + 一间物理房。"""
    t = client.post("/api/v1/tenants", json={"code": "apb", "name": "冲抵兜底测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['code']}/hotels", json={"code": "H", "name": "总店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['code']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 20000},
    ).json()
    client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[{"room_type_id": rt["id"], "room_no": "301"}],
    )
    return {"code": t["code"], "hotel_id": h["id"], "rt_id": rt["id"]}


def _new_booking(client: TestClient, ctx: dict, room_no: str = "301") -> dict:
    resp = client.post(
        f"/api/v1/tenants/{ctx['code']}/bookings",
        json={
            "hotel_id": ctx["hotel_id"],
            "room_type_id": ctx["rt_id"],
            "guest_name": "冲抵客",
            "check_in_date": "2026-12-01",
            "check_out_date": "2026-12-02",
            "room_no": room_no,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _open_bill_for_booking(client: TestClient, ctx: dict, booking_id: str, charge: int) -> dict:
    """给订单开一张账并挂一笔房费（此时 status=OPEN，balance=charge）。"""
    bill = client.post(
        f"/api/v1/tenants/{ctx['code']}/bills",
        json={
            "hotel_id": ctx["hotel_id"],
            "guest_name": "冲抵客",
            "booking_id": booking_id,
        },
    )
    assert bill.status_code in (200, 201), bill.text
    charged = client.post(
        f"/api/v1/tenants/{ctx['code']}/bills/{bill.json()['id']}/charges",
        json={"charge_type": "ROOM_CHARGE", "amount": charge, "description": "房租"},
    )
    assert charged.status_code == 200, charged.text
    body = charged.json()
    assert body["balance"] == charge, body
    return body


def _create_deposit(client: TestClient, ctx: dict, amount: int, *, booking_id: str | None) -> dict:
    """收一笔实收押金（初态 HELD，可直接冲抵）。不传 bill_id —— 复刻 UI 行为。"""
    payload: dict = {
        "hotel_id": ctx["hotel_id"],
        "kind": "DEPOSIT",
        "method": "CASH",
        "amount": amount,
    }
    if booking_id is not None:
        payload["booking_id"] = booking_id
    resp = client.post(f"/api/v1/tenants/{ctx['code']}/deposits", json=payload)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["bill_id"] is None, body  # 前置条件：未绑账单
    return body


def _apply(client: TestClient, ctx: dict, deposit_id: str, amount: int) -> object:
    """复刻 UI：不传 target_bill_id。"""
    return client.post(
        f"/api/v1/tenants/{ctx['code']}/deposits/{deposit_id}/apply",
        json={"amount": amount},
    )


class TestApplyBillFallback:
    """deposit 未绑账单 → 回退到 booking 的 OPEN 账单。"""

    def test_apply_without_bill_id_uses_booking_open_bill(self, client: TestClient) -> None:
        """主用例：UI 那种「只带 booking_id」的押金也能冲抵成功。"""
        ctx = _seed(client)
        bk = _new_booking(client, ctx)
        bill = _open_bill_for_booking(client, ctx, bk["id"], 20000)
        d = _create_deposit(client, ctx, 30000, booking_id=bk["id"])

        resp = _apply(client, ctx, d["id"], 20000)
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["status"] == "PARTIALLY_APPLIED", body  # 20000 < 30000
        assert body["applied_cents"] == 20000, body
        assert body["available_cents"] == 10000, body

        # 钱真的抵到了该订单的账单上
        got = client.get(f"/api/v1/tenants/{ctx['code']}/bills/{bill['id']}").json()
        assert got["balance"] == 0, got

    def test_fallback_does_not_persist_bill_id(self, client: TestClient) -> None:
        """兜底不回写 d.bill_id：bill_id 可空是为支持跨账单冲抵。"""
        ctx = _seed(client)
        bk = _new_booking(client, ctx)
        _open_bill_for_booking(client, ctx, bk["id"], 20000)
        d = _create_deposit(client, ctx, 30000, booking_id=bk["id"])

        assert _apply(client, ctx, d["id"], 5000).status_code == 200

        after = client.get(f"/api/v1/tenants/{ctx['code']}/deposits/{d['id']}").json()
        assert after["bill_id"] is None, after

    def test_full_apply_marks_applied(self, client: TestClient) -> None:
        """全额冲抵 → APPLIED，账单余额归零。"""
        ctx = _seed(client)
        bk = _new_booking(client, ctx)
        bill = _open_bill_for_booking(client, ctx, bk["id"], 30000)
        d = _create_deposit(client, ctx, 30000, booking_id=bk["id"])

        resp = _apply(client, ctx, d["id"], 30000)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "APPLIED", body
        assert body["available_cents"] == 0, body

        got = client.get(f"/api/v1/tenants/{ctx['code']}/bills/{bill['id']}").json()
        assert got["balance"] == 0, got


class TestApplyBillFallbackGuards:
    """兜底不能变成「没有账单也放行」，钱不能凭空出账。"""

    def test_no_booking_and_no_bill_still_rejected(self, client: TestClient) -> None:
        """散客押金（无 booking、无 bill）→ 仍 DEPOSIT_BILL_REQUIRED。"""
        ctx = _seed(client)
        d = _create_deposit(client, ctx, 30000, booking_id=None)

        resp = _apply(client, ctx, d["id"], 10000)
        assert resp.status_code == 409, resp.text
        assert "DEPOSIT_BILL_REQUIRED" in resp.text
        # 状态与金额未被改动
        after = client.get(f"/api/v1/tenants/{ctx['code']}/deposits/{d['id']}").json()
        assert after["status"] == "HELD", after
        assert after["applied_cents"] == 0, after

    def test_booking_without_open_bill_still_rejected(self, client: TestClient) -> None:
        """有 booking 但该订单没开账 → 仍 DEPOSIT_BILL_REQUIRED（无账可抵）。"""
        ctx = _seed(client)
        bk = _new_booking(client, ctx)  # 刻意不开账
        d = _create_deposit(client, ctx, 30000, booking_id=bk["id"])

        resp = _apply(client, ctx, d["id"], 10000)
        assert resp.status_code == 409, resp.text
        assert "DEPOSIT_BILL_REQUIRED" in resp.text

    def test_settled_bill_of_booking_is_not_used(self, client: TestClient) -> None:
        """订单账单已结账(SETTLED) → 不能拿它当兜底目标（账已封）。

        注意顺序：**先结账、后开押**。结账会自动退还该订单名下的押金，
        若先开押再结账，押金会被置成 REFUNDED，命中的就不是本守卫
        （会报 DEPOSIT_NOT_HELD，等于测了个寂寞）。
        """
        ctx = _seed(client)
        bk = _new_booking(client, ctx)
        bill = _open_bill_for_booking(client, ctx, bk["id"], 20000)

        # 结清该账单（先收款）
        paid = client.post(
            f"/api/v1/tenants/{ctx['code']}/bills/{bill['id']}/payments",
            json={"method": "CASH", "amount": 20000},
        )
        assert paid.status_code in (200, 201), paid.text
        settled = client.post(f"/api/v1/tenants/{ctx['code']}/bills/{bill['id']}/settle")
        assert settled.status_code == 200, settled.text
        assert (
            client.get(f"/api/v1/tenants/{ctx['code']}/bills/{bill['id']}").json()["status"]
            == "SETTLED"
        )

        # 结账之后再开押，避开「结账自动退押金」这条旁路
        d = _create_deposit(client, ctx, 30000, booking_id=bk["id"])
        assert d["status"] == "HELD", d

        resp = _apply(client, ctx, d["id"], 10000)
        assert resp.status_code == 409, resp.text
        assert "DEPOSIT_BILL_REQUIRED" in resp.text

    def test_explicit_target_bill_wins_over_fallback(self, client: TestClient) -> None:
        """显式指定 target_bill_id 时以它为准（跨账单冲抵能力不被兜底吞掉）。"""
        ctx = _seed(client)
        bk = _new_booking(client, ctx)
        own = _open_bill_for_booking(client, ctx, bk["id"], 20000)
        other = client.post(
            f"/api/v1/tenants/{ctx['code']}/bills",
            json={"hotel_id": ctx["hotel_id"], "guest_name": "他单"},
        ).json()
        client.post(
            f"/api/v1/tenants/{ctx['code']}/bills/{other['id']}/charges",
            json={"charge_type": "ROOM_CHARGE", "amount": 50000, "description": "他单消费"},
        )
        d = _create_deposit(client, ctx, 30000, booking_id=bk["id"])

        resp = client.post(
            f"/api/v1/tenants/{ctx['code']}/deposits/{d['id']}/apply",
            json={"amount": 10000, "target_bill_id": other["id"]},
        )
        assert resp.status_code == 200, resp.text

        # 冲到指定账单，本单账单不受影响
        assert client.get(f"/api/v1/tenants/{ctx['code']}/bills/{other['id']}").json()["balance"] == 40000
        assert client.get(f"/api/v1/tenants/{ctx['code']}/bills/{own['id']}").json()["balance"] == 20000
