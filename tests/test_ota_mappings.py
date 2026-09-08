"""M29 OTA 直连：房型映射 / 渠道价 / 推送日志 测试。

- 走 FastAPI TestClient 走真实路由 + 内存 SQLite；
- 覆盖：mapping upsert/list/delete + 反查；rate plan upsert/list/delete + 解析；
  push_inventory 写日志（含 dry_run / FAILED）；push_rates；push_logs list。
"""

from __future__ import annotations

import asyncio
import hmac
import hashlib
import json

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_engine, init_db
from app.main import app
from app.models import (
    Booking,
    ChannelPushLog,
    ChannelRatePlan,
    ChannelRoomMapping,
    Hotel,
    OtaChannelConfig,
    Room,
    RoomType,
    Tenant,
)


from contextlib import asynccontextmanager


@asynccontextmanager
async def s_ensure(sm):
    """Helper: 异步会话上下文（与 ``async with sm() as s`` 等价但可命名）。"""
    async with sm() as s:
        yield s



@pytest.fixture
async def tenant_and_hotel():
    """最小可用的租户+酒店+房型+房间 fixture（幂等：先查后建）。

    返回 (tenant_id_str, hotel_id, pms_room_type_id) —— tenant_id 走字符串形态
    （TenantMixin.tenant_id 是 String(32) 列，避免与 BigInteger id 混淆）。
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    sm = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with sm() as s:
        t = (
            await s.execute(select(Tenant).where(Tenant.code == "T29"))
        ).scalar_one_or_none()
        if t is None:
            t = Tenant(code="T29", name="M29 Tenant")
            s.add(t)
            await s.flush()
        h = (
            await s.execute(
                select(Hotel).where(Hotel.tenant_id == t.id, Hotel.code == "H29")
            )
        ).scalar_one_or_none()
        if h is None:
            h = Hotel(tenant_id=t.id, name="H29", code="H29")
            s.add(h)
            await s.flush()
        rt = (
            await s.execute(
                select(RoomType).where(
                    RoomType.tenant_id == t.id, RoomType.code == "STD29"
                )
            )
        ).scalar_one_or_none()
        if rt is None:
            rt = RoomType(
                tenant_id=t.id, code="STD29", name="标准间M29", base_price=30000
            )
            s.add(rt)
            await s.flush()
        await s.commit()
        tid_str = str(t.id)
        hid = h.id
        rtid = rt.id
    return tid_str, hid, rtid


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


async def _login(client: AsyncClient, tenant_id: str) -> str:
    """登录 admin：测试 fixture 必须显式 seed_default_roles + seed_default_admin
    （T29 不会走真实租户开通流程），并补齐 OTA_MANAGE/RATE_EDIT 权限。
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.models import Role, User, UserRole
    from app.services.permissions import ALL_PERMISSIONS
    from app.services.rbac_service import RbacService
    from sqlalchemy import select
    sm = async_sessionmaker(get_engine(), expire_on_commit=False)
    await init_db()

    async with s_ensure(sm) as s:
        # 1) seed 默认三档角色
        await RbacService(s).seed_default_roles(tenant_id)
        # 2) seed admin 用户（若已存在则跳过 user 创建，但不绑定 role，需手动补）
        try:
            await RbacService(s).seed_default_admin(tenant_id, "admin", "admin123")
        except Exception:
            pass
        await s.flush()
        # 3) 显式绑定 admin → 管理员 role（覆盖「已存在 user」路径）
        u = (await s.execute(
            select(User).where(User.tenant_id == tenant_id, User.username == "admin")
        )).scalar_one_or_none()
        admin_role = (
            await s.execute(
                select(Role).where(Role.tenant_id == tenant_id, Role.name == "管理员")
            )
        ).scalar_one_or_none()
        if u and admin_role:
            existing_bind = (await s.execute(
                select(UserRole).where(
                    UserRole.user_id == u.id, UserRole.role_id == admin_role.id,
                )
            )).scalar_one_or_none()
            if not existing_bind:
                await RbacService(s).assign_role(tenant_id, u.id, admin_role.id)
        # 4) 补齐 admin role 的 ALL_PERMISSIONS（含 OTA_MANAGE/RATE_EDIT）
        if admin_role is not None:
            cur = set(admin_role.permissions or [])
            missing = ALL_PERMISSIONS - cur
            if missing:
                admin_role.permissions = sorted(cur | ALL_PERMISSIONS)
        await s.commit()

    r = await client.post(
        f"/api/v1/tenants/{tenant_id}/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert r.status_code == 200, r.text
    token = r.json().get("token")
    if not token:
        raise RuntimeError(f"login returned no token: {r.text}")
    return token


# ---------- ChannelRoomMapping ----------


async def test_mapping_upsert_and_resolve(tenant_and_hotel, client):
    tid, hid, rtid = tenant_and_hotel
    tok = await _login(client, tid)
    H = {"Authorization": f"Bearer {tok}"}

    # 0) 先确保 OtaChannelConfig 存在（upsert config 才能 push）
    r = await client.put(
        f"/api/v1/tenants/{tid}/ota/configs",
        headers=H,
        json={
            "hotel_id": hid,
            "channel": "sandbox",
            "secret": "sandbox-secret-123",
            "push_enabled": True,
        },
    )
    assert r.status_code == 200, r.text

    # 1) 创建映射
    r = await client.post(
        f"/api/v1/tenants/{tid}/ota/mappings",
        headers=H,
        json={
            "hotel_id": hid,
            "channel": "sandbox",
            "pms_room_type_id": rtid,
            "external_room_type_code": "STD-X",
            "enabled": True,
        },
    )
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["external_room_type_code"] == "STD-X"

    # 2) 列表
    r = await client.get(
        f"/api/v1/tenants/{tid}/ota/mappings", headers=H, params={"channel": "sandbox"}
    )
    assert r.status_code == 200
    assert len(r.json()) == 1

    # 3) 删除
    r = await client.delete(
        f"/api/v1/tenants/{tid}/ota/mappings/{m['id']}", headers=H
    )
    assert r.status_code == 200
    assert r.json()["deleted"] is True


async def test_mapping_upsert_rejects_unknown_channel(tenant_and_hotel, client):
    tid, hid, rtid = tenant_and_hotel
    tok = await _login(client, tid)
    H = {"Authorization": f"Bearer {tok}"}

    r = await client.post(
        f"/api/v1/tenants/{tid}/ota/mappings",
        headers=H,
        json={
            "hotel_id": hid,
            "channel": "unknown_channel",
            "pms_room_type_id": rtid,
            "external_room_type_code": "X",
        },
    )
    assert r.status_code == 400


# ---------- ChannelRatePlan ----------


async def test_rate_plan_upsert_and_resolve(tenant_and_hotel, client):
    tid, hid, rtid = tenant_and_hotel
    tok = await _login(client, tid)
    H = {"Authorization": f"Bearer {tok}"}

    await client.put(
        f"/api/v1/tenants/{tid}/ota/configs",
        headers=H,
        json={
            "hotel_id": hid,
            "channel": "sandbox",
            "secret": "sandbox-secret-123",
            "push_enabled": True,
        },
    )

    # 永久默认价
    r = await client.post(
        f"/api/v1/tenants/{tid}/ota/rate-plans",
        headers=H,
        json={
            "hotel_id": hid,
            "channel": "sandbox",
            "pms_room_type_id": rtid,
            "effective_date": None,
            "price_cents": 28000,
        },
    )
    assert r.status_code == 200, r.text
    rp_id = r.json()["id"]

    # 列表
    r = await client.get(
        f"/api/v1/tenants/{tid}/ota/rate-plans", headers=H, params={"channel": "sandbox"}
    )
    assert r.status_code == 200
    assert len(r.json()) == 1

    # 删除
    r = await client.delete(
        f"/api/v1/tenants/{tid}/ota/rate-plans/{rp_id}", headers=H
    )
    assert r.status_code == 200


async def test_rate_plan_rejects_zero_price(tenant_and_hotel, client):
    tid, hid, rtid = tenant_and_hotel
    tok = await _login(client, tid)
    H = {"Authorization": f"Bearer {tok}"}

    await client.put(
        f"/api/v1/tenants/{tid}/ota/configs",
        headers=H,
        json={"hotel_id": hid, "channel": "sandbox", "secret": "sandbox-secret-123"},
    )

    r = await client.post(
        f"/api/v1/tenants/{tid}/ota/rate-plans",
        headers=H,
        json={
            "hotel_id": hid,
            "channel": "sandbox",
            "pms_room_type_id": rtid,
            "effective_date": None,
            "price_cents": 0,
        },
    )
    # Pydantic gt=0 → 422（业务校验）
    assert r.status_code == 422


# ---------- push_inventory + push_logs ----------


async def test_push_inventory_writes_log(tenant_and_hotel, client):
    tid, hid, rtid = tenant_and_hotel
    tok = await _login(client, tid)
    H = {"Authorization": f"Bearer {tok}"}

    await client.put(
        f"/api/v1/tenants/{tid}/ota/configs",
        headers=H,
        json={
            "hotel_id": hid,
            "channel": "sandbox",
            "secret": "sandbox-secret-123",
            "push_enabled": True,
        },
    )
    await client.post(
        f"/api/v1/tenants/{tid}/ota/mappings",
        headers=H,
        json={
            "hotel_id": hid,
            "channel": "sandbox",
            "pms_room_type_id": rtid,
            "external_room_type_code": "STD-X",
        },
    )

    # dry_run=True → 状态 = DRY_RUN
    r = await client.post(
        f"/api/v1/tenants/{tid}/ota/sandbox/inventory/push",
        headers=H,
        params={"days": 7, "dry_run": "true"},
    )
    assert r.status_code == 200, r.text
    ack = r.json()
    assert ack["dry_run"] is True
    # 找我们映射的 STD29（dev 库已有 STD 等其他房型）
    item = next(i for i in ack["items"] if i["pms_room_type_id"] == rtid)
    assert item["external_room_type_code"] == "STD-X"
    assert item["pms_room_type_code"] == "STD29"

    # 真实推送
    r = await client.post(
        f"/api/v1/tenants/{tid}/ota/sandbox/inventory/push",
        headers=H,
        params={"days": 7},
    )
    assert r.status_code == 200
    assert r.json()["dry_run"] is False

    # 日志列表：应至少有 2 条
    r = await client.get(
        f"/api/v1/tenants/{tid}/ota/push-logs", headers=H
    )
    assert r.status_code == 200
    logs = r.json()
    assert len(logs) >= 2
    statuses = {l["status"] for l in logs}
    assert "DRY_RUN" in statuses
    assert "SUCCESS" in statuses

    # 按状态过滤
    r = await client.get(
        f"/api/v1/tenants/{tid}/ota/push-logs",
        headers=H,
        params={"status": "SUCCESS"},
    )
    assert r.status_code == 200
    assert all(l["status"] == "SUCCESS" for l in r.json())


async def test_push_inventory_failed_when_disabled(tenant_and_hotel, client):
    tid, hid, rtid = tenant_and_hotel
    tok = await _login(client, tid)
    H = {"Authorization": f"Bearer {tok}"}

    await client.put(
        f"/api/v1/tenants/{tid}/ota/configs",
        headers=H,
        json={
            "hotel_id": hid,
            "channel": "sandbox",
            "secret": "sandbox-secret-123",
            "push_enabled": False,
        },
    )

    r = await client.post(
        f"/api/v1/tenants/{tid}/ota/sandbox/inventory/push",
        headers=H,
        params={"days": 7},
    )
    assert r.status_code == 400
    assert "推送已关闭" in r.text

    # 但日志里仍应有 FAILED 状态
    r = await client.get(
        f"/api/v1/tenants/{tid}/ota/push-logs",
        headers=H,
        params={"status": "FAILED"},
    )
    assert r.status_code == 200
    assert len(r.json()) >= 1


async def test_push_rates_resolves_channel_price(tenant_and_hotel, client):
    tid, hid, rtid = tenant_and_hotel
    tok = await _login(client, tid)
    H = {"Authorization": f"Bearer {tok}"}

    await client.put(
        f"/api/v1/tenants/{tid}/ota/configs",
        headers=H,
        json={
            "hotel_id": hid,
            "channel": "sandbox",
            "secret": "sandbox-secret-123",
            "push_enabled": True,
        },
    )
    await client.post(
        f"/api/v1/tenants/{tid}/ota/rate-plans",
        headers=H,
        json={
            "hotel_id": hid,
            "channel": "sandbox",
            "pms_room_type_id": rtid,
            "effective_date": None,
            "price_cents": 26000,
        },
    )

    r = await client.post(
        f"/api/v1/tenants/{tid}/ota/sandbox/rates/push",
        headers=H,
        params={"dry_run": "true"},
    )
    assert r.status_code == 200, r.text
    ack = r.json()
    item = next(i for i in ack["items"] if i["pms_room_type_id"] == rtid)
    assert item["channel_price_cents"] == 26000
    assert item["base_price_cents"] == 30000