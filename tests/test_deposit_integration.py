"""M32.18 结账/夜审集成测试（T04）。

覆盖设计稿 §C（结账自动冲抵 + 退余款）、§B5/B6（夜审 30 天自动释放）、
§D（事务落库直连 DB 校验）、§E1（8 条押金路由权限守卫）。

不破坏既有「balance != 0 → 409」语义（F1 回归由 test_cashier 守护）。
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.routes import require_perm, router as api_router
from app.db import session as db_session
from app.models.deposit import Deposit, DepositKind, DepositStatus
from app.models.tenant import Tenant


# ----------------------------- 种子 -----------------------------
def _seed(client: TestClient) -> dict:
    t = client.post("/api/v1/tenants", json={"code": "itg", "name": "集成测试"}).json()
    h = client.post(
        f"/api/v1/tenants/{t['code']}/hotels", json={"code": "H", "name": "总店"}
    ).json()
    rt = client.post(
        f"/api/v1/tenants/{t['code']}/room-types",
        json={"code": "STD", "name": "标间", "base_price": 30000},
    ).json()
    room = client.post(
        f"/api/v1/hotels/{h['id']}/rooms",
        json=[{"room_type_id": rt["id"], "room_no": "0101"}],
    ).json()[0]
    return {"t": t, "h": h, "rt": rt, "room": room}


def _booking_bill(client: TestClient, ctx: dict, phone: str = "13800000099") -> tuple[dict, dict]:
    bk = client.post(
        f"/api/v1/tenants/{ctx['t']['code']}/bookings",
        json={
            "hotel_id": ctx["h"]["id"],
            "room_type_id": ctx["rt"]["id"],
            "guest_name": "集成客",
            "guest_phone": phone,
            "check_in_date": "2026-12-01",
            "check_out_date": "2026-12-02",
            "room_no": "0101",
        },
    ).json()
    bill = client.post(
        f"/api/v1/tenants/{ctx['t']['code']}/bills",
        json={"hotel_id": ctx["h"]["id"], "guest_name": "集成客", "booking_id": bk["id"]},
    ).json()
    return bk, bill


def _charge(client: TestClient, ctx: dict, bill_id: int, amount: int) -> None:
    client.post(
        f"/api/v1/tenants/{ctx['t']['code']}/bills/{bill_id}/charges",
        json={"charge_type": "ROOM_CHARGE", "amount": amount, "description": "房租"},
    )


def _deposit(
    client: TestClient,
    ctx: dict,
    bill_id: int,
    booking_id: int,
    amount: int,
    *,
    kind: str = "DEPOSIT",
    method: str = "CASH",
) -> dict:
    return client.post(
        f"/api/v1/tenants/{ctx['t']['code']}/deposits",
        json={
            "hotel_id": ctx["h"]["id"],
            "booking_id": booking_id,
            "bill_id": bill_id,
            "room_no": "0101",
            "kind": kind,
            "method": method,
            "amount": amount,
        },
    ).json()


def _settle(client: TestClient, ctx: dict, bill_id: int):
    return client.post(f"/api/v1/tenants/{ctx['t']['code']}/bills/{bill_id}/settle")


def _get_deposit(client: TestClient, ctx: dict, deposit_id: int) -> dict:
    return client.get(f"/api/v1/tenants/{ctx['t']['code']}/deposits/{deposit_id}").json()


def _member_points(db_path: str, phone: str) -> int:
    row = sqlite3.connect(db_path).execute(
        "SELECT points FROM members WHERE phone=?", (phone,)
    ).fetchone()
    return int(row[0]) if row else 0


# ----------------------------- §C 结账集成 -----------------------------
class TestSettleDepositIntegration:
    def test_C1_apply_and_refund_surplus(self, client: TestClient, tmp_path) -> None:
        """消费 35000，押金 50000 → 冲抵 35000 + 退余款 15000，balance=0，SETTLED。"""
        ctx = _seed(client)
        bk, bill = _booking_bill(client, ctx)
        _charge(client, ctx, bill["id"], 35000)
        d = _deposit(client, ctx, bill["id"], bk["id"], 50000)
        assert d["status"] == "HELD"

        r = _settle(client, ctx, bill["id"])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "SETTLED"
        assert body["balance"] == 0

        # 押金：冲抵 35000 + 退余款 15000 → REFUNDED
        d2 = _get_deposit(client, ctx, d["id"])
        assert d2["applied_cents"] == 35000
        assert d2["refunded_cents"] == 15000
        assert d2["status"] == "REFUNDED"

        db = str(tmp_path / "test.db")
        # 退还**不**写 Payment（D3）
        pay = sqlite3.connect(db).execute(
            "SELECT COUNT(*) FROM payments WHERE bill_id=? AND ref_no=?",
            (bill["id"], d["deposit_no"]),
        ).fetchone()[0]
        assert pay == 1  # 仅冲抵那笔 Payment(DEPOSIT)
        # 审计留痕（D4）
        audit = sqlite3.connect(db).execute(
            "SELECT COUNT(*) FROM audit_logs WHERE action='deposit.refund' AND resource_id=?",
            (d["id"],),
        ).fetchone()[0]
        assert audit == 1

    def test_C2_deposit_insufficient_409(self, client: TestClient, tmp_path) -> None:
        """消费 35000，押金 10000 → 冲抵 10000 后仍欠 25000 → 409 DEPOSIT_INSUFFICIENT。"""
        ctx = _seed(client)
        bk, bill = _booking_bill(client, ctx)
        _charge(client, ctx, bill["id"], 35000)
        _deposit(client, ctx, bill["id"], bk["id"], 10000)

        r = _settle(client, ctx, bill["id"])
        assert r.status_code == 409, r.text
        assert "DEPOSIT_INSUFFICIENT" in r.text
        assert "需补收 25000" in r.text

    def test_C3_deposit_exact_no_refund(self, client: TestClient, tmp_path) -> None:
        """消费 35000，押金 35000 → 冲抵 35000，无退款，balance=0，SETTLED。"""
        ctx = _seed(client)
        bk, bill = _booking_bill(client, ctx)
        _charge(client, ctx, bill["id"], 35000)
        d = _deposit(client, ctx, bill["id"], bk["id"], 35000)

        r = _settle(client, ctx, bill["id"])
        assert r.status_code == 200, r.text
        assert r.json()["balance"] == 0

        d2 = _get_deposit(client, ctx, d["id"])
        assert d2["applied_cents"] == 35000
        assert d2["refunded_cents"] == 0
        assert d2["status"] == "APPLIED"  # 全额冲抵，终态

    def test_C4_fifo_two_deposits(self, client: TestClient, tmp_path) -> None:
        """两笔押金(20000+30000) 冲抵 35000：第一笔 APPLIED，第二笔 PARTIAL(15000) 后余款退 REFUNDED。"""
        ctx = _seed(client)
        bk, bill = _booking_bill(client, ctx)
        _charge(client, ctx, bill["id"], 35000)
        d1 = _deposit(client, ctx, bill["id"], bk["id"], 20000)  # 先建 → FIFO 在前
        d2 = _deposit(client, ctx, bill["id"], bk["id"], 30000)

        r = _settle(client, ctx, bill["id"])
        assert r.status_code == 200, r.text
        assert r.json()["balance"] == 0

        got1 = _get_deposit(client, ctx, d1["id"])
        got2 = _get_deposit(client, ctx, d2["id"])
        # FIFO：第一笔被全额冲抵 → APPLIED；第二笔冲抵 15000 → 余款退 → REFUNDED
        assert got1["applied_cents"] == 20000
        assert got1["status"] == "APPLIED"
        assert got2["applied_cents"] == 15000
        assert got2["refunded_cents"] == 15000
        assert got2["status"] == "REFUNDED"

    def test_C5_no_negative_payment_after_settle(self, client: TestClient, tmp_path) -> None:
        """settle 后 balance 恒 0，且无新增负向 Payment（余款退走 refund 不写 Payment）。"""
        ctx = _seed(client)
        bk, bill = _booking_bill(client, ctx)
        _charge(client, ctx, bill["id"], 35000)
        _deposit(client, ctx, bill["id"], bk["id"], 50000)

        r = _settle(client, ctx, bill["id"])
        assert r.status_code == 200, r.text
        assert r.json()["balance"] == 0

        db = str(tmp_path / "test.db")
        amounts = sqlite3.connect(db).execute(
            "SELECT amount FROM payments WHERE bill_id=?", (bill["id"],)
        ).fetchall()
        assert all(a[0] >= 0 for a in amounts), f"存在负向 Payment: {amounts}"

    def test_C6_deposit_applied_counts_toward_member_points(
        self, client: TestClient, tmp_path
    ) -> None:
        """押金冲抵计入会员积分基数（is_deposit=False 使 _paid_excl_deposit 含冲抵额）。"""
        ctx = _seed(client)
        phone = "13900001111"
        # 注册会员
        m = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/members",
            json={"hotel_id": ctx["h"]["id"], "name": "积分客", "phone": phone},
        )
        assert m.status_code == 201, m.text

        bk, bill = _booking_bill(client, ctx, phone=phone)
        _charge(client, ctx, bill["id"], 35000)
        _deposit(client, ctx, bill["id"], bk["id"], 50000)

        r = _settle(client, ctx, bill["id"])
        assert r.status_code == 200, r.text

        # 积分 = 实收(含押金冲抵 35000¢) // 100 = 350 分（1 元 = 1 分）。
        # 若 is_deposit 误设为 True，_paid_excl_deposit 会排除冲抵额 → 积分为 0，
        # 故 350 同时验证了「押金冲抵计入积分基数」。
        assert _member_points(str(tmp_path / "test.db"), phone) == 350


# ----------------------------- §B5/B6 夜审自动释放 -----------------------------
async def _insert_preauth(
    tenant_code: str, hotel_id: int, booking_id: int, created_at: datetime
) -> int:
    async with db_session._session_factory() as s:
        tenant = (
            await s.execute(select(Tenant).where(Tenant.code == tenant_code))
        ).scalar_one()
        dep = Deposit(
            tenant_id=tenant.code,
            hotel_id=hotel_id,
            deposit_no="PTEST-OLD",
            booking_id=booking_id,
            room_no="0101",
            kind=DepositKind.PREAUTH.value,
            method="UNIONPAY",
            amount_cents=30000,
            available_cents=30000,
            status=DepositStatus.AUTHORIZED.value,
            operator="seed",
            created_at=created_at,
            version=0,
        )
        s.add(dep)
        await s.commit()
        await s.refresh(dep)
        return int(dep.id)


class TestNightAuditAutoRelease:
    def test_B5_expired_preauth_released_by_night_audit(self, client: TestClient, tmp_path) -> None:
        """31 天前的 PREAUTH 经夜审日切自动释放（RELEASED + release_cause=EXPIRED）。"""
        ctx = _seed(client)
        bk, _ = _booking_bill(client, ctx)
        old = datetime.now(timezone.utc) - timedelta(days=31)
        dep_id = asyncio.run(_insert_preauth(ctx["t"]["code"], ctx["h"]["id"], bk["id"], old))

        # 跑夜审（business_date 任取，房间为空净不影响释放扫描）
        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/night-audit",
            json={"hotel_id": ctx["h"]["id"], "business_date": "2026-12-01"},
        )
        assert r.status_code in (200, 201), r.text

        d = _get_deposit(client, ctx, dep_id)
        assert d["status"] == "RELEASED"
        assert d["release_cause"] == "EXPIRED"

        # 释放记录进夜审快照
        db = str(tmp_path / "test.db")
        snap = sqlite3.connect(db).execute(
            "SELECT snapshot FROM daily_reports ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
        assert "auto_released_preauth" in snap
        assert str(dep_id) in snap  # 释放的押金 id 已写入快照

    def test_B6_recent_preauth_not_released(self, client: TestClient, tmp_path) -> None:
        """29 天前的 PREAUTH 未超 30 天阈值，夜审不释放，仍 AUTHORIZED。"""
        ctx = _seed(client)
        bk, _ = _booking_bill(client, ctx)
        recent = datetime.now(timezone.utc) - timedelta(days=29)
        dep_id = asyncio.run(_insert_preauth(ctx["t"]["code"], ctx["h"]["id"], bk["id"], recent))

        r = client.post(
            f"/api/v1/tenants/{ctx['t']['code']}/night-audit",
            json={"hotel_id": ctx["h"]["id"], "business_date": "2026-12-01"},
        )
        assert r.status_code in (200, 201), r.text

        d = _get_deposit(client, ctx, dep_id)
        assert d["status"] == "AUTHORIZED"


# ----------------------------- §E1 路由权限守卫 -----------------------------
def _is_perm_dep(dep) -> bool:  # noqa: ANN001
    fn = getattr(dep, "call", None) or getattr(dep, "dependency", None)
    if fn is None:
        return False
    return (
        getattr(fn, "__name__", "") == "require_perm"
        and getattr(fn, "__module__", "") == "app.api.routes"
    )


class TestDepositRouteGuards:
    def test_E1_all_eight_deposit_routes_declare_require_perm(self) -> None:
        """8 条押金路由全部声明 require_perm（依赖注入层守卫）。"""
        expected = {
            ("POST", "/tenants/{tenant_id}/deposits"),
            ("POST", "/tenants/{tenant_id}/deposits/{deposit_id}/apply"),
            ("POST", "/tenants/{tenant_id}/deposits/{deposit_id}/refund"),
            ("POST", "/tenants/{tenant_id}/deposits/{deposit_id}/void"),
            ("POST", "/tenants/{tenant_id}/deposits/{deposit_id}/release"),
            ("POST", "/tenants/{tenant_id}/deposits/auto-release"),
            ("GET", "/tenants/{tenant_id}/deposits"),
            ("GET", "/tenants/{tenant_id}/deposits/{deposit_id}"),
        }
        found: set[tuple[str, str]] = set()
        for route in api_router.routes:
            if not hasattr(route, "methods") or not hasattr(route, "path"):
                continue
            deps = getattr(route, "dependencies", None) or []
            has_perm = any((d is require_perm) or _is_perm_dep(d) for d in deps)
            if not has_perm:
                continue
            for method in route.methods:
                if method in {"HEAD", "OPTIONS"}:
                    continue
                full = route.path
                if full.startswith("/tenants/{tenant_id}/deposits"):
                    found.add((method, full))
        missing = expected - found
        assert not missing, f"以下押金路由缺失 require_perm 守卫: {missing}"
        assert expected <= found
