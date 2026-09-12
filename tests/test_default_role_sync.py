"""M37 权限同步（登录惰性对账）测试：DEFAULT_ROLES 新增权限点必须到达存量租户。

背景（M37 实测漂移）：``seed_default_roles`` 只在租户开通时执行、对已存在角色
直接跳过，导致后期加入 DEFAULT_ROLES 的新权限点（如 invoice.manage）永远到不了
存量租户——admin 登录只拿到 14 个权限，发票/优惠券/早餐/黑名单页面全被门控拦掉。

修复：登录成功路径调用 ``RbacService.sync_default_roles``：
- 幂等（进程内每租户只跑一次，见 routes._DEFAULT_ROLE_SYNCED）
- 只增不减（不回收系统角色任何既有权限）
- 绝不触碰 is_system=False 自定义角色（安全红线，见 test_backfill_role_perms.py）

⚠️ 测试码必须用默认三档**没有**的虚拟点，勿复用 ALL_PERMISSIONS 里的码。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

# 默认三档绝对没有的虚拟权限点（用于「额外授权不被回收」的断言）
TEST_PERM = "loyalty.grant"


def _seed(client: TestClient, code: str) -> dict:
    t = client.post("/api/v1/tenants", json={"code": code, "name": "同步测试"}).json()
    user = client.post(
        f"/api/v1/tenants/{t['code']}/users",
        json={"username": "alice", "password": "secret1", "display_name": "阿丽"},
    ).json()
    roles = client.get(f"/api/v1/tenants/{t['code']}/roles").json()
    admin = next(r for r in roles if r["name"] == "管理员")
    client.post(
        f"/api/v1/tenants/{t['code']}/users/{user['id']}/roles",
        json={"role_id": admin["id"]},
    )
    return t


def _clear_sync_cache(tenant_code: str) -> None:
    """清掉进程内「已同步」标记，强制下一次登录真正执行对账。"""
    from app.api.routes import _DEFAULT_ROLE_SYNCED

    _DEFAULT_ROLE_SYNCED.discard(tenant_code)


def _login(client: TestClient, code: str) -> dict:
    return client.post(
        f"/api/v1/tenants/{code}/auth/login",
        json={"username": "alice", "password": "secret1"},
    ).json()


async def _admin_role_perms(code: str) -> list[str]:
    from app.db.session import get_engine
    from app.models.rbac import Role

    factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with factory() as s:
        role = (
            await s.execute(
                select(Role).where(Role.tenant_id == code, Role.name == "管理员")
            )
        ).scalar_one()
        return list(role.permissions or [])


async def _set_admin_role_perms(code: str, perms: list[str]) -> None:
    """直接改库模拟「旧快照」角色（无角色更新 API，只能绕过接口层）。"""
    from app.db.session import get_engine
    from app.models.rbac import Role

    factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    async with factory() as s:
        role = (
            await s.execute(
                select(Role).where(Role.tenant_id == code, Role.name == "管理员")
            )
        ).scalar_one()
        role.permissions = list(perms)
        await s.commit()


@pytest.mark.asyncio
async def test_login_syncs_drifted_system_role(client: TestClient) -> None:
    """系统角色被人为漂移后（模拟旧快照），登录应补回 DEFAULT_ROLES 定义的权限。"""
    t = _seed(client, "t_sync_drift")
    code = t["code"]

    # 制造漂移：管理员只留 1 个权限（大面积落后于 DEFAULT_ROLES）
    await _set_admin_role_perms(code, ["billing.discount"])

    _clear_sync_cache(code)
    login = _login(client, code)
    assert login["status"] == "ok"
    perms = set(login["permissions"])
    # 原有的不丢
    assert "billing.discount" in perms
    # DEFAULT_ROLES 定义的补回来（含 M37 新点与此前漂移的点）
    for expected in ("invoice.manage", "coupon.manage", "breakfast.manage", "blacklist.manage", "deposit.manage", "night_audit.run"):
        assert expected in perms, f"登录权限缺 {expected}"


@pytest.mark.asyncio
async def test_sync_is_additive_never_revokes(client: TestClient) -> None:
    """同步只增不减：系统角色上 DEFAULT_ROLES 之外的既有权限不得被回收。"""
    t = _seed(client, "t_sync_add")
    code = t["code"]

    before = await _admin_role_perms(code)
    drifted = [*before, TEST_PERM]
    await _set_admin_role_perms(code, drifted)

    _clear_sync_cache(code)
    assert _login(client, code)["status"] == "ok"

    after = await _admin_role_perms(code)
    assert TEST_PERM in after, f"同步不应回收既有权限，丢失了 {TEST_PERM}"
    assert set(before) <= set(after)


@pytest.mark.asyncio
async def test_sync_never_touches_custom_roles(client: TestClient) -> None:
    """自定义角色（is_system=False）零变化——绝不自动扩权。"""
    t = _seed(client, "t_sync_custom")
    custom = client.post(
        f"/api/v1/tenants/{t['code']}/roles",
        json={"name": "专属管家", "level": "STAFF", "permissions": ["fnb.manage"]},
    ).json()
    assert custom["is_system"] is False

    _clear_sync_cache(t["code"])
    assert _login(client, t["code"])["status"] == "ok"

    after = next(
        r
        for r in client.get(f"/api/v1/tenants/{t['code']}/roles").json()
        if r["id"] == custom["id"]
    )
    assert after["permissions"] == ["fnb.manage"]


@pytest.mark.asyncio
async def test_sync_idempotent_second_login_no_change(client: TestClient) -> None:
    """同步幂等：对账一次后角色权限即与 DEFAULT_ROLES 对齐，再次登录不再变化。"""
    t = _seed(client, "t_sync_idem")
    code = t["code"]
    await _set_admin_role_perms(code, ["billing.discount"])

    _clear_sync_cache(code)
    assert _login(client, code)["status"] == "ok"
    first = await _admin_role_perms(code)

    _clear_sync_cache(code)
    assert _login(client, code)["status"] == "ok"
    second = await _admin_role_perms(code)
    assert first == second
