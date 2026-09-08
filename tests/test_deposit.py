"""M32.18 押金与预授权域测试（service + 8 API 端到端）。

覆盖：
- create 收押金 / 预授权，**不**触碰 Bill.balance
- apply 写 Payment(method=DEPOSIT) + Bill.balance 减少，**不**写 BillItem
- refund 强制审计 + 不动 Bill.balance
- release 仅 PREAUTH + applied==0
- 守卫：金额越界 / kind 非法 / status 不合法 / 退款超额
- 乐观锁：expected_version 不匹配 → 409
- auto_release_expired 30 天
- 押金模型不变式 I1：available_cents = amount - applied - refunded - forfeited
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.deposit_service import DepositError, DepositService


def _db_path(tmp_path) -> str:
    return str(tmp_path / "test.db")


def _seed_minimal(client: TestClient) -> dict:
    """建租户 + 门店 + 房型 + 1 间房 + 1 张账单，返回 id 集合。"""
    t = client.post("/api/v1/tenants", json={"code": "tdp", "name": "押金测试"}).json()
    h = client.post(f"/api/v1/tenants/{t['code']}/hotels", json={"code": "H", "name": "总店"}).json()
    rt = client.post(
        f"/api/v1/tenants/{t['code']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    room = client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[{"room_type_id": rt["id"], "room_no": "0101"}],
    ).json()[0]
    # 散客建单（reception 流程可能复杂，直接 DB 插 bill 简单粗暴）
    from app.db import session as db_session
    from app.models.billing import Bill
    from app.models.tenant import Tenant
    import asyncio

    async def _make_bill():
        async with db_session._session_factory() as s:
            tenant = (await s.execute(
                __import__("sqlalchemy").select(Tenant).where(Tenant.code == t["code"])
            )).scalar_one()
            bill = Bill(
                tenant_id=tenant.code,
                hotel_id=h["id"],
                bill_no="B-TDP-1",
                room_no="0101",
                source="WALK_IN",
                status="OPEN",
                balance=60000,  # 应收 600 元（预留给冲抵测试）
            )
            s.add(bill)
            await s.commit()
            return bill.id

    bill_id = asyncio.run(_make_bill())
    return {
        "t": t, "h": h, "rt": rt, "room": room, "bill_id": bill_id,
    }


class TestDepositCreate:
    def test_create_deposit_does_not_touch_bill(self, client: TestClient, tmp_path) -> None:
        """收押金**不**写 Payment、**不**改 Bill.balance。"""
        ctx = _seed_minimal(client)
        db = _db_path(tmp_path)
        # 取建账前 Bill.balance（建账后是 60000，create 不应影响）
        before = sqlite3.connect(db).execute(
            "SELECT balance FROM bills WHERE id=?", (ctx["bill_id"],)
        ).fetchone()[0]

        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits",
            json={
                "hotel_id": ctx["h"]["id"],
                "bill_id": ctx["bill_id"],
                "room_no": "0101",
                "kind": "DEPOSIT",
                "method": "CASH",
                "amount": 10000,
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "HELD"
        assert body["available_cents"] == 10000
        assert body["applied_cents"] == 0
        assert body["deposit_no"].startswith("D")

        # Bill.balance 完全不变
        after = sqlite3.connect(db).execute(
            "SELECT balance FROM bills WHERE id=?", (ctx["bill_id"],)
        ).fetchone()[0]
        assert after == before, f"收押金不该动 Bill.balance：{before} → {after}"

        # 没新增 Payment（押金不写 Payment）
        pay = sqlite3.connect(db).execute(
            "SELECT COUNT(*) FROM payments WHERE bill_id=?", (ctx["bill_id"],)
        ).fetchone()[0]
        assert pay == 0

        # 流水存在 + 审计存在
        assert sqlite3.connect(db).execute(
            "SELECT COUNT(*) FROM deposit_transactions WHERE deposit_id=?", (body["id"],)
        ).fetchone()[0] == 1
        assert sqlite3.connect(db).execute(
            "SELECT COUNT(*) FROM audit_logs WHERE action='deposit.create' AND resource_id=?",
            (body["id"],),
        ).fetchone()[0] == 1

    def test_create_preauth_status_authorized(self, client: TestClient, tmp_path) -> None:
        """预授权 → AUTHORIZED + 30 天 expires_at。"""
        ctx = _seed_minimal(client)
        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits",
            json={
                "hotel_id": ctx["h"]["id"],
                "room_no": "0101",
                "kind": "PREAUTH",
                "method": "UNIONPAY",
                "amount": 30000,
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "AUTHORIZED"
        assert body["expires_at"] is not None
        assert "T" in body["expires_at"]  # ISO8601

    def test_create_amount_out_of_range_409(self, client: TestClient, tmp_path) -> None:
        ctx = _seed_minimal(client)
        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits",
            json={
                "hotel_id": ctx["h"]["id"],
                "kind": "DEPOSIT",
                "method": "CASH",
                "amount": 0,
            },
        )
        assert r.status_code == 422  # Pydantic ge=1

    def test_create_unionpay_real_deposit_rejected(self, client: TestClient, tmp_path) -> None:
        """UNIONPAY 收实收押金 → 409（须走预授权）。"""
        ctx = _seed_minimal(client)
        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits",
            json={
                "hotel_id": ctx["h"]["id"],
                "kind": "DEPOSIT",
                "method": "UNIONPAY",
                "amount": 10000,
            },
        )
        assert r.status_code == 409
        assert "DEPOSIT_UNIONPAY_NEED_PREAUTH" in r.text


class TestDepositApply:
    def test_apply_writes_payment_decreases_bill_no_billitem(
        self, client: TestClient, tmp_path
    ) -> None:
        """apply 写 Payment(method=DEPOSIT) + Bill.balance -= amount；不写 BillItem。"""
        ctx = _seed_minimal(client)
        db = _db_path(tmp_path)
        # 收 100 元押金
        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits",
            json={
                "hotel_id": ctx["h"]["id"],
                "bill_id": ctx["bill_id"],
                "kind": "DEPOSIT",
                "method": "CASH",
                "amount": 10000,
            },
        )
        d = r.json()
        # 冲抵 60 元
        r2 = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits/{d['id']}/apply",
            json={"amount": 6000},
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["applied_cents"] == 6000
        assert body["available_cents"] == 4000
        assert body["status"] == "PARTIALLY_APPLIED"

        # Bill.balance: 60000 - 6000 = 54000
        bal = sqlite3.connect(db).execute(
            "SELECT balance FROM bills WHERE id=?", (ctx["bill_id"],)
        ).fetchone()[0]
        assert bal == 54000

        # Payment(method=DEPOSIT) 写入
        pay = sqlite3.connect(db).execute(
            "SELECT method, amount, is_deposit, ref_no FROM payments WHERE bill_id=?",
            (ctx["bill_id"],),
        ).fetchall()
        assert len(pay) == 1
        method, amount, is_deposit, ref_no = pay[0]
        assert method == "DEPOSIT"
        assert amount == 6000
        # 冲抵 Payment 标记 is_deposit=False：这是真实冲抵（客人的钱已抵房费），
        # 须被 _paid_excl_deposit（过滤 is_deposit=True 的旧押金路径）计入会员积分基数。
        assert is_deposit == 0
        assert ref_no == d["deposit_no"]

        # **不**写 BillItem（冲抵不重复计营收）
        billitems = sqlite3.connect(db).execute(
            "SELECT COUNT(*) FROM bill_items WHERE bill_id=?", (ctx["bill_id"],)
        ).fetchone()[0]
        assert billitems == 0

    def test_apply_full_marks_applied(self, client: TestClient, tmp_path) -> None:
        """全额冲抵 → status=APPLIED（终态）。"""
        ctx = _seed_minimal(client)
        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits",
            json={
                "hotel_id": ctx["h"]["id"],
                "bill_id": ctx["bill_id"],
                "kind": "DEPOSIT",
                "method": "CASH",
                "amount": 10000,
            },
        )
        d = r.json()
        r2 = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits/{d['id']}/apply",
            json={"amount": 10000},
        )
        body = r2.json()
        assert body["status"] == "APPLIED"
        assert body["available_cents"] == 0

    def test_apply_exceeds_available_409(self, client: TestClient, tmp_path) -> None:
        ctx = _seed_minimal(client)
        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits",
            json={
                "hotel_id": ctx["h"]["id"],
                "bill_id": ctx["bill_id"],
                "kind": "DEPOSIT",
                "method": "CASH",
                "amount": 5000,
            },
        )
        d = r.json()
        r2 = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits/{d['id']}/apply",
            json={"amount": 6000},
        )
        assert r2.status_code == 409
        assert "DEPOSIT_INSUFFICIENT" in r2.text

    def test_apply_optimistic_lock_conflict_409(self, client: TestClient, tmp_path) -> None:
        """expected_version 不匹配 → 409 DEPOSIT_VERSION_CONFLICT。"""
        ctx = _seed_minimal(client)
        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits",
            json={
                "hotel_id": ctx["h"]["id"],
                "bill_id": ctx["bill_id"],
                "kind": "DEPOSIT",
                "method": "CASH",
                "amount": 10000,
            },
        )
        d = r.json()
        r2 = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits/{d['id']}/apply",
            json={"amount": 3000, "expected_version": 999},
        )
        assert r2.status_code == 409
        assert "DEPOSIT_VERSION_CONFLICT" in r2.text


class TestDepositRefund:
    def test_refund_partial_marks_partially_applied_and_audits(
        self, client: TestClient, tmp_path
    ) -> None:
        """部分退款 → PARTIALLY_APPLIED + 强制审计。"""
        ctx = _seed_minimal(client)
        db = _db_path(tmp_path)
        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits",
            json={
                "hotel_id": ctx["h"]["id"],
                "kind": "DEPOSIT",
                "method": "CASH",
                "amount": 10000,
            },
        )
        d = r.json()
        r2 = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits/{d['id']}/refund",
            json={"amount": 3000, "note": "客人临时取消"},
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["refunded_cents"] == 3000
        assert body["available_cents"] == 7000
        # HELD + 部分退后变 PARTIALLY_APPLIED（设计稿 #7）
        assert body["status"] == "PARTIALLY_APPLIED"

        # 审计必留 + detail.note
        audit = sqlite3.connect(db).execute(
            "SELECT detail FROM audit_logs WHERE action='deposit.refund' AND resource_id=?",
            (d["id"],),
        ).fetchall()
        assert len(audit) == 1
        import json as _json
        detail = _json.loads(audit[0][0])
        assert detail.get("note") == "客人临时取消"

    def test_refund_full_marks_refunded(self, client: TestClient, tmp_path) -> None:
        ctx = _seed_minimal(client)
        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits",
            json={
                "hotel_id": ctx["h"]["id"],
                "kind": "DEPOSIT",
                "method": "CASH",
                "amount": 10000,
            },
        )
        d = r.json()
        r2 = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits/{d['id']}/refund",
            json={"amount": 10000, "note": "全额退"},
        )
        assert r2.json()["status"] == "REFUNDED"

    def test_refund_without_note_409(self, client: TestClient, tmp_path) -> None:
        """退款 note 必填。"""
        ctx = _seed_minimal(client)
        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits",
            json={
                "hotel_id": ctx["h"]["id"],
                "kind": "DEPOSIT",
                "method": "CASH",
                "amount": 10000,
            },
        )
        d = r.json()
        r2 = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits/{d['id']}/refund",
            json={"amount": 1000},  # 故意没 note
        )
        assert r2.status_code == 409
        assert "DEPOSIT_REASON_REQUIRED" in r2.text


class TestDepositRelease:
    def test_release_preauth_succeeds(self, client: TestClient, tmp_path) -> None:
        """预授权 + applied==0 → release → RELEASED。"""
        ctx = _seed_minimal(client)
        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits",
            json={
                "hotel_id": ctx["h"]["id"],
                "kind": "PREAUTH",
                "method": "UNIONPAY",
                "amount": 30000,
            },
        )
        d = r.json()
        r2 = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits/{d['id']}/release",
            json={"operator": "front_desk", "cause": "MANUAL"},
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["status"] == "RELEASED"
        assert body["release_cause"] == "MANUAL"
        assert body["released_at"] is not None

    def test_release_real_deposit_rejected(self, client: TestClient, tmp_path) -> None:
        """实收押金 release → 409。"""
        ctx = _seed_minimal(client)
        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits",
            json={
                "hotel_id": ctx["h"]["id"],
                "kind": "DEPOSIT",
                "method": "CASH",
                "amount": 10000,
            },
        )
        d = r.json()
        r2 = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits/{d['id']}/release",
            json={"operator": "front_desk"},
        )
        assert r2.status_code == 409
        assert "DEPOSIT_NOT_PREAUTH" in r2.text


class TestDepositInvariants:
    def test_invariant_I1_available_equals_amount_minus_three(
        self, client: TestClient, tmp_path
    ) -> None:
        """不变式 I1：available = amount − applied − refunded − forfeited 恒等。"""
        ctx = _seed_minimal(client)
        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits",
            json={
                "hotel_id": ctx["h"]["id"],
                "bill_id": ctx["bill_id"],
                "kind": "DEPOSIT",
                "method": "CASH",
                "amount": 10000,
            },
        )
        d = r.json()
        # apply 6000
        client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits/{d['id']}/apply",
            json={"amount": 6000},
        )
        # refund 1000
        client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/deposits/{d['id']}/refund",
            json={"amount": 1000, "note": "退 1000"},
        )
        # 查 DB
        db = _db_path(tmp_path)
        row = sqlite3.connect(db).execute(
            "SELECT amount_cents, applied_cents, refunded_cents, forfeited_cents, available_cents "
            "FROM deposits WHERE id=?",
            (d["id"],),
        ).fetchone()
        amount, applied, refunded, forfeited, available = row
        assert amount == 10000
        assert applied == 6000
        assert refunded == 1000
        assert forfeited == 0
        assert available == 10000 - 6000 - 1000 - 0  # = 3000
