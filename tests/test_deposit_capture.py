"""预授权请款（capture）能力测试。

背景
----
``app/models/deposit.py`` 早已预留 ``DepositStatus.CAPTURED``、
``DepositAction.CAPTURE`` 与 ``Deposit.captured_at``，但 service / route 层
一直缺失 ``capture()``，导致：

- ``CAPTURED`` 状态**永远不可达**；
- ``deposit_service._APPLICABLE_POOL`` 里的 ``(PREAUTH, CAPTURED)`` 是死代码；
- 预授权只能「冻结 → 释放」，**永远无法「请款 → 冲抵」**。

本文件锁定补齐后的语义：

1. capture 只把冻结额度转实收（``AUTHORIZED → CAPTURED``），
   **不**写 Payment、**不**动 ``Bill.balance``（计营收是后续 ``apply`` 的事，
   capture 再写一次会重复计营收）；
2. capture 之后 ``(PREAUTH, CAPTURED)`` 命中可冲抵池，``apply`` 才能生效
   —— ``test_captured_preauth_can_apply_to_bill`` 是「死代码被盘活」的证明；
3. 已请款的预授权不能再 ``release``（钱已真实收到，只能走 refund）。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

_DEPOSITS_URL = "/api/v1/tenants/{tenant_code}/deposits"


# ----------------------------- 种子与辅助 -----------------------------
def _seed(client: TestClient) -> dict:
    """建租户 + 门店。押金/预授权创建不强依赖订单，最小种子即可。"""
    t = client.post(
        "/api/v1/tenants", json={"code": "cap", "name": "预授权请款测试"}
    ).json()
    h = client.post(
        f"/api/v1/tenants/{t['code']}/hotels", json={"code": "H", "name": "总店"}
    ).json()
    return {"code": t["code"], "hotel_id": h["id"]}


def _create_preauth(
    client: TestClient,
    ctx: dict,
    amount: int,
    *,
    bill_id: int | None = None,
    method: str = "UNIONPAY",
) -> dict:
    """冻结一笔预授权，初态 AUTHORIZED。"""
    payload: dict = {
        "hotel_id": ctx["hotel_id"],
        "kind": "PREAUTH",
        "method": method,
        "amount": amount,
    }
    if bill_id is not None:
        payload["bill_id"] = bill_id
    resp = client.post(_DEPOSITS_URL.format(tenant_code=ctx["code"]), json=payload)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["status"] == "AUTHORIZED", body
    return body


def _create_cash_deposit(client: TestClient, ctx: dict, amount: int) -> dict:
    """收一笔实收押金，初态 HELD（用于验证 capture 拒绝非预授权）。"""
    resp = client.post(
        _DEPOSITS_URL.format(tenant_code=ctx["code"]),
        json={
            "hotel_id": ctx["hotel_id"],
            "kind": "DEPOSIT",
            "method": "CASH",
            "amount": amount,
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


def _capture(client: TestClient, ctx: dict, deposit_id: int, **body: object):
    return client.post(
        f"{_DEPOSITS_URL.format(tenant_code=ctx['code'])}/{deposit_id}/capture",
        json=body,
    )


def _apply(client: TestClient, ctx: dict, deposit_id: int, **body: object):
    return client.post(
        f"{_DEPOSITS_URL.format(tenant_code=ctx['code'])}/{deposit_id}/apply",
        json=body,
    )


def _release(client: TestClient, ctx: dict, deposit_id: int, **body: object):
    return client.post(
        f"{_DEPOSITS_URL.format(tenant_code=ctx['code'])}/{deposit_id}/release",
        json=body,
    )


def _get_deposit(client: TestClient, ctx: dict, deposit_id: int) -> dict:
    resp = client.get(
        f"{_DEPOSITS_URL.format(tenant_code=ctx['code'])}/{deposit_id}"
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _open_bill(client: TestClient, ctx: dict, charge: int) -> dict:
    """开一张散客账 + 加一笔房费，返回账单（balance == charge）。"""
    bill = client.post(
        f"/api/v1/tenants/{ctx['code']}/bills",
        json={"hotel_id": ctx["hotel_id"], "guest_name": "请款客"},
    )
    assert bill.status_code in (200, 201), bill.text
    bill_body = bill.json()
    charged = client.post(
        f"/api/v1/tenants/{ctx['code']}/bills/{bill_body['id']}/charges",
        json={"charge_type": "ROOM_CHARGE", "amount": charge, "description": "房租"},
    )
    assert charged.status_code == 200, charged.text
    charged_body = charged.json()
    assert charged_body["balance"] == charge, charged_body
    return charged_body


def _get_bill(client: TestClient, ctx: dict, bill_id: int) -> dict:
    resp = client.get(f"/api/v1/tenants/{ctx['code']}/bills/{bill_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _txn_actions(deposit_detail: dict) -> list[str]:
    return [t["action"] for t in deposit_detail.get("transactions", [])]


# ----------------------------- 请款主流程 -----------------------------
class TestPreauthCapture:
    """AUTHORIZED → CAPTURED 主链路。"""

    def test_full_capture_marks_captured(self, client: TestClient) -> None:
        """全额请款：status=CAPTURED、captured_at 非空、version 递增、额度不变。"""
        ctx = _seed(client)
        d = _create_preauth(client, ctx, 30000)
        assert d["captured_at"] is None
        assert d["version"] == 0

        resp = _capture(client, ctx, d["id"])
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["status"] == "CAPTURED", body
        assert body["captured_at"], body
        assert body["version"] == d["version"] + 1, body
        # 全额请款不改额度，可用余额仍为全额（等同 HELD 参与后续冲抵）
        assert body["amount_cents"] == 30000, body
        assert body["available_cents"] == 30000, body
        assert body["applied_cents"] == 0, body

        # 流水追加 CAPTURE（WORM，只追加不改写）
        detail = _get_deposit(client, ctx, d["id"])
        assert _txn_actions(detail) == ["CREATE", "CAPTURE"], detail
        capture_txn = detail["transactions"][-1]
        assert capture_txn["amount_cents"] == 30000, capture_txn

    def test_partial_capture_shrinks_authorized_amount(
        self, client: TestClient
    ) -> None:
        """部分请款：授权 30000 请款 10000 → 额度收敛为 10000，可用余额同步。"""
        ctx = _seed(client)
        d = _create_preauth(client, ctx, 30000)

        resp = _capture(client, ctx, d["id"], amount=10000)
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["status"] == "CAPTURED", body
        assert body["amount_cents"] == 10000, body
        # available = amount - applied - refunded - forfeited = 10000 - 0 - 0 - 0
        assert body["available_cents"] == 10000, body
        assert body["captured_at"], body

        # 流水按实际请款额记账，并留痕被放弃的冻结额度（便于追溯）
        detail = _get_deposit(client, ctx, d["id"])
        capture_txn = detail["transactions"][-1]
        assert capture_txn["action"] == "CAPTURE", capture_txn
        assert capture_txn["amount_cents"] == 10000, capture_txn
        assert "released_cents=20000" in (capture_txn["note"] or ""), capture_txn

    def test_capture_full_amount_explicitly_equals_default(
        self, client: TestClient
    ) -> None:
        """显式传满额 == 缺省全额请款（额度不收敛）。"""
        ctx = _seed(client)
        d = _create_preauth(client, ctx, 25000)

        resp = _capture(client, ctx, d["id"], amount=25000)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "CAPTURED", body
        assert body["amount_cents"] == 25000, body
        assert body["available_cents"] == 25000, body


# --------------------- 请款后可冲抵（死代码被盘活的证明） ---------------------
class TestCapturedPreauthApply:
    """``_APPLICABLE_POOL`` 里的 ``(PREAUTH, CAPTURED)`` 必须真正可用。"""

    def test_authorized_preauth_cannot_apply_before_capture(
        self, client: TestClient
    ) -> None:
        """前置对照：未请款的预授权不可冲抵（否则本组测试证明不了任何事）。"""
        ctx = _seed(client)
        bill = _open_bill(client, ctx, 20000)
        d = _create_preauth(client, ctx, 30000, bill_id=bill["id"])

        resp = _apply(client, ctx, d["id"], amount=20000, target_bill_id=bill["id"])
        assert resp.status_code == 409, resp.text
        assert "DEPOSIT_NOT_HELD" in resp.text
        # 账单未被触碰
        assert _get_bill(client, ctx, bill["id"])["balance"] == 20000

    def test_captured_preauth_can_apply_to_bill(self, client: TestClient) -> None:
        """请款后冲抵：bill.balance 减少、押金转 PARTIALLY_APPLIED。"""
        ctx = _seed(client)
        bill = _open_bill(client, ctx, 20000)
        d = _create_preauth(client, ctx, 30000, bill_id=bill["id"])

        captured = _capture(client, ctx, d["id"])
        assert captured.status_code == 200, captured.text
        # capture 自身不计营收：账单余额此刻不动
        assert _get_bill(client, ctx, bill["id"])["balance"] == 20000

        applied = _apply(
            client, ctx, d["id"], amount=20000, target_bill_id=bill["id"]
        )
        assert applied.status_code == 200, applied.text
        body = applied.json()

        assert body["status"] == "PARTIALLY_APPLIED", body  # 20000 < 30000
        assert body["applied_cents"] == 20000, body
        assert body["available_cents"] == 10000, body

        # 冲抵才计营收：balance 归零
        assert _get_bill(client, ctx, bill["id"])["balance"] == 0

    def test_partial_capture_then_full_apply_marks_applied(
        self, client: TestClient
    ) -> None:
        """部分请款 + 全额冲抵 → APPLIED（额度已收敛，applied 追平 amount）。"""
        ctx = _seed(client)
        bill = _open_bill(client, ctx, 10000)
        d = _create_preauth(client, ctx, 30000, bill_id=bill["id"])

        assert _capture(client, ctx, d["id"], amount=10000).status_code == 200
        applied = _apply(
            client, ctx, d["id"], amount=10000, target_bill_id=bill["id"]
        )
        assert applied.status_code == 200, applied.text
        body = applied.json()

        assert body["status"] == "APPLIED", body
        assert body["applied_cents"] == 10000, body
        assert body["available_cents"] == 0, body
        assert _get_bill(client, ctx, bill["id"])["balance"] == 0

    def test_apply_cannot_exceed_captured_amount(self, client: TestClient) -> None:
        """部分请款后，冲抵上限是收敛后的额度，而非原授权额度。"""
        ctx = _seed(client)
        bill = _open_bill(client, ctx, 30000)
        d = _create_preauth(client, ctx, 30000, bill_id=bill["id"])

        assert _capture(client, ctx, d["id"], amount=10000).status_code == 200
        resp = _apply(client, ctx, d["id"], amount=20000, target_bill_id=bill["id"])
        assert resp.status_code == 409, resp.text
        assert "DEPOSIT_INSUFFICIENT" in resp.text
        assert _get_bill(client, ctx, bill["id"])["balance"] == 30000


# ----------------------------- 校验分支 -----------------------------
class TestCaptureGuards:
    """kind / status / 金额 / 乐观锁四类守卫。"""

    def test_cash_deposit_cannot_capture(self, client: TestClient) -> None:
        """实收押金没有「请款」概念 → DEPOSIT_NOT_PREAUTH。"""
        ctx = _seed(client)
        d = _create_cash_deposit(client, ctx, 10000)

        resp = _capture(client, ctx, d["id"])
        assert resp.status_code == 409, resp.text
        assert "DEPOSIT_NOT_PREAUTH" in resp.text
        assert _get_deposit(client, ctx, d["id"])["status"] == "HELD"

    def test_released_preauth_cannot_capture(self, client: TestClient) -> None:
        """非 AUTHORIZED（此处 RELEASED）不可请款 → DEPOSIT_CAPTURE_NOT_ALLOWED。"""
        ctx = _seed(client)
        d = _create_preauth(client, ctx, 30000)
        assert _release(client, ctx, d["id"]).status_code == 200

        resp = _capture(client, ctx, d["id"])
        assert resp.status_code == 409, resp.text
        assert "DEPOSIT_CAPTURE_NOT_ALLOWED" in resp.text
        assert _get_deposit(client, ctx, d["id"])["status"] == "RELEASED"

    def test_capture_twice_is_rejected(self, client: TestClient) -> None:
        """重复请款直接拒（不做幂等）；第二次不得改动任何字段。"""
        ctx = _seed(client)
        d = _create_preauth(client, ctx, 30000)
        first = _capture(client, ctx, d["id"])
        assert first.status_code == 200, first.text
        snapshot = first.json()

        second = _capture(client, ctx, d["id"])
        assert second.status_code == 409, second.text
        assert "DEPOSIT_CAPTURE_NOT_ALLOWED" in second.text

        after = _get_deposit(client, ctx, d["id"])
        assert after["version"] == snapshot["version"], after
        assert after["captured_at"] == snapshot["captured_at"], after
        assert _txn_actions(after) == ["CREATE", "CAPTURE"], after

    def test_capture_exceeding_authorized_amount_is_rejected(
        self, client: TestClient
    ) -> None:
        """请款金额 > 授权额度 → DEPOSIT_CAPTURE_EXCEEDS。"""
        ctx = _seed(client)
        d = _create_preauth(client, ctx, 30000)

        resp = _capture(client, ctx, d["id"], amount=30001)
        assert resp.status_code == 409, resp.text
        assert "DEPOSIT_CAPTURE_EXCEEDS" in resp.text

        after = _get_deposit(client, ctx, d["id"])
        assert after["status"] == "AUTHORIZED", after
        assert after["version"] == 0, after

    def test_capture_zero_amount_is_rejected_by_schema(
        self, client: TestClient
    ) -> None:
        """amount=0 由 schema（ge=1）拦下 → 422，不进 service。"""
        ctx = _seed(client)
        d = _create_preauth(client, ctx, 30000)

        resp = _capture(client, ctx, d["id"], amount=0)
        assert resp.status_code == 422, resp.text
        assert _get_deposit(client, ctx, d["id"])["status"] == "AUTHORIZED"

    def test_capture_version_conflict(self, client: TestClient) -> None:
        """expected_version 不匹配 → DEPOSIT_VERSION_CONFLICT，且状态不变。"""
        ctx = _seed(client)
        d = _create_preauth(client, ctx, 30000)
        assert d["version"] == 0

        resp = _capture(client, ctx, d["id"], expected_version=7)
        assert resp.status_code == 409, resp.text
        assert "DEPOSIT_VERSION_CONFLICT" in resp.text

        after = _get_deposit(client, ctx, d["id"])
        assert after["status"] == "AUTHORIZED", after
        assert after["version"] == 0, after

        # 传对的版本号则通过
        ok = _capture(client, ctx, d["id"], expected_version=0)
        assert ok.status_code == 200, ok.text
        assert ok.json()["status"] == "CAPTURED"

    def test_capture_on_missing_deposit(self, client: TestClient) -> None:
        """不存在的押金 → DEPOSIT_NOT_FOUND（与相邻写端点一致映射为 409）。"""
        ctx = _seed(client)
        resp = _capture(client, ctx, 999999)
        assert resp.status_code == 409, resp.text
        assert "DEPOSIT_NOT_FOUND" in resp.text


# ------------------- 请款后不可释放（补的资金漏洞守卫） -------------------
class TestReleaseAfterCapture:
    """已请款 = 钱已真实收到，只能 refund，不能当冻结额度释放掉。"""

    def test_captured_preauth_cannot_release(self, client: TestClient) -> None:
        ctx = _seed(client)
        d = _create_preauth(client, ctx, 30000)
        assert _capture(client, ctx, d["id"]).status_code == 200

        resp = _release(client, ctx, d["id"])
        assert resp.status_code == 409, resp.text
        assert "DEPOSIT_PREAUTH_CAPTURED" in resp.text

        after = _get_deposit(client, ctx, d["id"])
        assert after["status"] == "CAPTURED", after
        assert after["released_at"] is None, after

    def test_authorized_preauth_can_still_release(self, client: TestClient) -> None:
        """对照组：未请款的预授权释放路径未被新守卫波及。"""
        ctx = _seed(client)
        d = _create_preauth(client, ctx, 30000)

        resp = _release(client, ctx, d["id"])
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "RELEASED"

    def test_captured_preauth_can_refund(self, client: TestClient) -> None:
        """请款后的正确退路是 refund（守卫不能把钱锁死在系统里）。"""
        ctx = _seed(client)
        d = _create_preauth(client, ctx, 30000)
        assert _capture(client, ctx, d["id"]).status_code == 200

        resp = client.post(
            f"{_DEPOSITS_URL.format(tenant_code=ctx['code'])}/{d['id']}/refund",
            json={"amount": 30000, "note": "客人异议，请款后原路退回"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "REFUNDED", body
        assert body["available_cents"] == 0, body
