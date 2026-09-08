"""Sprint 8 测试：移动支付（M7-2）。

验证：回调幂等（同 notify_id 去重 / 已付重放 DUPLICATE）；金额校验拒绝（防篡改）；
支付成功落账（回调时已有 OPEN 账单直接落 Payment / 开单晚于回调经 apply-prepay 抵扣）；
掉单对账（超时未付单关单，已关单迟到回调拒绝）。
"""

from fastapi.testclient import TestClient


def _seed_and_order(client: TestClient) -> dict:
    t = client.post("/api/v1/tenants", json={"code": "pay1", "name": "支付测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['id']}/hotels", json={"code": "H", "name": "店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['id']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    client.post(f"/api/v1/hotels/{h['id']}/rooms", json=[{"room_type_id": rt["id"], "room_no": "0301"}])
    order = client.post(
        f"/api/v1/tenants/{t['code']}/mp/orders",
        json={
            "hotel_id": h["id"],
            "room_type_id": rt["id"],
            "guest_name": "支付客",
            "check_in_date": "2026-12-01",
            "check_out_date": "2026-12-03",
        },
    ).json()
    return {"t": t, "h": h, "rt": rt, "order": order}


def _notify(client: TestClient, code: str, order: dict, amount: int, notify_id: str) -> dict:
    return client.post(
        f"/api/v1/tenants/{code}/pay/notify",
        json={
            "out_trade_no": order["pay_order"]["out_trade_no"],
            "amount_cents": amount,
            "transaction_id": "wx_txn_001",
            "notify_id": notify_id,
        },
    ).json()


class TestPayNotify:
    def test_notify_idempotent(self, client: TestClient) -> None:
        d = _seed_and_order(client)
        code = d["t"]["code"]
        first = _notify(client, code, d["order"], 60000, "nid-1")
        assert first["result"] == "PROCESSED"
        assert first["posted_to_bill"] is False  # 尚未开账单，仅标记已支付
        replay = _notify(client, code, d["order"], 60000, "nid-1")
        assert replay["result"] == "DUPLICATE"
        other = _notify(client, code, d["order"], 60000, "nid-2")
        assert other["result"] == "DUPLICATE"  # 订单已 PAID，迟到重放不重复落账
        orders = client.get(f"/api/v1/tenants/{code}/pay-orders?status_=PAID").json()
        assert len(orders) == 1
        assert orders[0]["transaction_id"] == "wx_txn_001"

    def test_notify_amount_mismatch_rejected(self, client: TestClient) -> None:
        d = _seed_and_order(client)
        code = d["t"]["code"]
        bad = _notify(client, code, d["order"], 59999, "nid-bad")
        assert bad["result"] == "REJECTED"
        still = client.get(
            f"/api/v1/tenants/{code}/mp/orders/{d['order']['pay_order']['out_trade_no']}"
        ).json()
        assert still["pay_order"]["status"] == "CREATED"  # 未被篡改支付

    def test_notify_posts_payment_to_open_bill(self, client: TestClient) -> None:
        d = _seed_and_order(client)
        code = d["t"]["code"]
        bk = d["order"]["booking"]
        bill = client.post(
            f"/api/v1/tenants/{code}/bills",
            json={"hotel_id": d["h"]["id"], "guest_name": "支付客", "booking_id": bk["id"]},
        ).json()
        client.post(
            f"/api/v1/tenants/{code}/bills/{bill['id']}/charges",
            json={"charge_type": "ROOM_CHARGE", "amount": 60000, "description": "房费"},
        )
        result = _notify(client, code, d["order"], 60000, "nid-bill")
        assert result["result"] == "PROCESSED"
        assert result["posted_to_bill"] is True
        after = client.get(f"/api/v1/tenants/{code}/bills/{bill['id']}").json()
        assert after["balance"] == 0
        assert any(p["method"] == "WECHAT" and p["amount"] == 60000 for p in after["payments"])

    def test_apply_prepay_after_bill_opened(self, client: TestClient) -> None:
        d = _seed_and_order(client)
        code = d["t"]["code"]
        bk = d["order"]["booking"]
        assert _notify(client, code, d["order"], 60000, "nid-pre")["result"] == "PROCESSED"
        bill = client.post(
            f"/api/v1/tenants/{code}/bills",
            json={"hotel_id": d["h"]["id"], "guest_name": "支付客", "booking_id": bk["id"]},
        ).json()
        client.post(
            f"/api/v1/tenants/{code}/bills/{bill['id']}/charges",
            json={"charge_type": "ROOM_CHARGE", "amount": 60000, "description": "房费"},
        )
        # 开单晚于回调：余额 60000 → 预付抵扣 → 0
        after = client.post(f"/api/v1/tenants/{code}/bills/{bill['id']}/apply-prepay").json()
        assert after["balance"] == 0
        assert any(p["method"] == "WECHAT" for p in after["payments"])


class TestPayReconcile:
    def test_reconcile_closes_stale_and_rejects_late_notify(self, client: TestClient) -> None:
        d = _seed_and_order(client)
        code = d["t"]["code"]
        recon = client.post(
            f"/api/v1/tenants/{code}/pay/reconcile",
            json={"before": "2099-01-01T00:00"},
        ).json()
        assert recon["scanned"] == 1
        assert recon["closed"] == 1
        assert recon["recovered"] == 0
        assert recon["details"][0]["action"] == "closed"
        out_no = d["order"]["pay_order"]["out_trade_no"]
        closed = client.get(f"/api/v1/tenants/{code}/mp/orders/{out_no}").json()
        assert closed["pay_order"]["status"] == "CLOSED"
        assert closed["pay_order"]["close_reason"] == "reconcile_timeout"
        # 已关单的迟到回调 → REJECTED（走人工补单）
        late = _notify(client, code, d["order"], 60000, "nid-late")
        assert late["result"] == "REJECTED"
