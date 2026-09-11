"""押金列表 status 筛选回归测试（缺陷修复锁定）。

背景
----
``GET /api/v1/tenants/{tenant_id}/deposits`` 的查询参数一度被命名为
``status_filter``，而前端 ``listDeposits()`` 传的是 ``params.status``，
且项目其余 6 个列表端点（订单/账单/预授权等）统一使用 ``status``。

后果：请求 ``?status=HELD`` 时 FastAPI 找不到名为 ``status`` 的形参，
**静默忽略**该参数 → 押金管理页状态筛选点了没反应，永远返回全量。

本文件锁定修复：``status`` 必须真正生效。若将来有人把参数改回
``status_filter``（或任何其它名字），``test_list_returns_all_when_param_name_drifts``
会立刻失败。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

_DEPOSITS_URL = "/api/v1/tenants/{tenant_code}/deposits"


def _seed(client: TestClient) -> dict:
    """建租户 + 门店。押金创建不强依赖订单/账单，最小种子即可。"""
    t = client.post(
        "/api/v1/tenants", json={"code": "dps", "name": "押金筛选测试"}
    ).json()
    h = client.post(
        f"/api/v1/tenants/{t['code']}/hotels", json={"code": "H", "name": "总店"}
    ).json()
    return {"code": t["code"], "hotel_id": h["id"]}


def _create_deposit(client: TestClient, ctx: dict, amount: int) -> dict:
    """收一笔实收押金，初态 HELD。"""
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


def _refund_full(client: TestClient, ctx: dict, deposit_id: int, amount: int) -> dict:
    """全额退款 → 终态 REFUNDED。"""
    resp = client.post(
        f"{_DEPOSITS_URL.format(tenant_code=ctx['code'])}/{deposit_id}/refund",
        json={"amount": amount, "note": "回归测试：全额退款"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _list(client: TestClient, ctx: dict, **params: object) -> list[dict]:
    resp = client.get(_DEPOSITS_URL.format(tenant_code=ctx["code"]), params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestDepositListStatusFilter:
    """``?status=`` 必须真正过滤，而不是被忽略。"""

    def test_status_filter_returns_only_matching_deposit(
        self, client: TestClient
    ) -> None:
        """建 HELD + REFUNDED 两笔，?status=HELD 只应返回那一笔。"""
        ctx = _seed(client)

        held = _create_deposit(client, ctx, 10000)
        refunded = _create_deposit(client, ctx, 20000)
        assert held["status"] == "HELD"
        assert refunded["status"] == "HELD"

        # 第二笔全额退款 → REFUNDED
        after_refund = _refund_full(client, ctx, refunded["id"], 20000)
        assert after_refund["status"] == "REFUNDED"

        # 前置断言：不带筛选应返回全量 2 笔（证明种子确实落库了两条）
        all_rows = _list(client, ctx)
        assert len(all_rows) == 2, all_rows

        # 核心断言：筛选 HELD 只返回第一笔
        held_rows = _list(client, ctx, status="HELD")
        assert [row["id"] for row in held_rows] == [held["id"]], held_rows

        # 反向也成立：筛选 REFUNDED 只返回第二笔
        refunded_rows = _list(client, ctx, status="REFUNDED")
        assert [row["id"] for row in refunded_rows] == [refunded["id"]], refunded_rows

    def test_status_filter_no_match_returns_empty(self, client: TestClient) -> None:
        """无匹配状态时返回空列表，而不是退化成全量。"""
        ctx = _seed(client)
        _create_deposit(client, ctx, 10000)

        assert len(_list(client, ctx)) == 1
        assert _list(client, ctx, status="APPLIED") == []

    def test_list_returns_all_when_param_name_drifts(self, client: TestClient) -> None:
        """参数名守门：``?status=`` 生效，错误名字（如 status_filter）不生效。

        这条用例是改名回归的哨兵。若端点参数被改回 ``status_filter``，
        则 ``?status=HELD`` 失效（下面第一个断言会拿到 2 条而失败）。
        """
        ctx = _seed(client)
        held = _create_deposit(client, ctx, 10000)
        other = _create_deposit(client, ctx, 20000)
        _refund_full(client, ctx, other["id"], 20000)

        # 正确参数名：生效
        assert [row["id"] for row in _list(client, ctx, status="HELD")] == [held["id"]]

        # 错误参数名：被 FastAPI 静默忽略 → 全量返回（这正是缺陷时的表现）
        # 断言它的"无过滤"行为，确保没人误以为换名也能工作。
        drifting = _list(client, ctx, status_filter="HELD")
        assert len(drifting) == 2, drifting

    def test_status_filter_combines_with_kind(self, client: TestClient) -> None:
        """status 与 kind 可叠加过滤（多角度确认 status 确实进了 WHERE）。"""
        ctx = _seed(client)

        cash = _create_deposit(client, ctx, 10000)  # kind=DEPOSIT
        preauth = client.post(
            _DEPOSITS_URL.format(tenant_code=ctx["code"]),
            json={
                "hotel_id": ctx["hotel_id"],
                "kind": "PREAUTH",
                "method": "UNIONPAY",
                "amount": 30000,
            },
        )
        assert preauth.status_code in (200, 201), preauth.text
        preauth_body = preauth.json()

        # DEPOSIT 初态 HELD；PREAUTH 初态 AUTHORIZED（见 deposit_service.py:141）——
        # 二者状态不同，正好用来验证 status 与 kind 能同时进 WHERE 且不互相覆盖。
        held_rows = _list(client, ctx, status="HELD")
        assert [row["id"] for row in held_rows] == [cash["id"]], held_rows

        preauth_rows = _list(client, ctx, status="AUTHORIZED", kind="PREAUTH")
        assert [row["id"] for row in preauth_rows] == [preauth_body["id"]], preauth_rows

        # 单独按 kind=PREAUTH 过滤（不带 status）也只应拿到那一条
        by_kind = _list(client, ctx, kind="PREAUTH")
        assert [row["id"] for row in by_kind] == [preauth_body["id"]], by_kind
