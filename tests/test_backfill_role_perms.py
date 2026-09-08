"""M32.18 权限回填脚本测试：自定义角色绝对不被静默扩权。

M8-1 经验教训：F&B 功能上线时因新增权限点没回填到存量租户的角色，
出现大面积 403。本脚本（``scripts/backfill_role_perms.py``）是「显性扩权」
的唯一入口——本测试确保它只动 ``is_system=True`` 的默认三档，自定义角色
零变化。

注意：选测试权限码时必须用默认三档**没有**的（如 ``deposit.manage``），
否则 ``added = target - old`` 为空，脚本正确地返回 0 affected，测试
就错把「正确行为」当 bug。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# 一个**确定不在**默认三档权限集合里的虚拟权限点，用于触发回填路径。
# ⚠️ 每次新增 Sprint 必须校验：切勿复用本 Sprint 已加进 ``ALL_PERMISSIONS`` 的码
# （如 M32.18 T02 加了 deposit.manage/deposit.refund），否则 ``added = target - old``
# 为空、回填正确地返回 0 affected，测试会把「正确行为」误判成 bug。
TEST_PERM = "billing.reconcile"


def _seed(client: TestClient, code: str) -> dict:
    t = client.post("/api/v1/tenants", json={"code": code, "name": "回填测试"}).json()
    return t


def _read_role(client, tenant_id: str, name: str) -> dict:
    res = client.get(f"/api/v1/tenants/{tenant_id}/roles")
    return next(r for r in res.json() if r["name"] == name)


@pytest.mark.asyncio
async def test_backfill_does_not_touch_custom_roles(
    client: TestClient, tmp_path
) -> None:
    """回填只动系统默认三档；自定义角色零变化。"""
    from scripts.backfill_role_perms import backfill_role_perms

    t = _seed(client, "t_backfill1")

    # 创建 1 个自定义角色（is_system=False）
    custom = client.post(
        f"/api/v1/tenants/{t['code']}/roles",
        json={"name": "专属管家", "level": "STAFF", "permissions": ["fnb.manage"]},
    ).json()
    assert custom["is_system"] is False

    # 跑回填：把 TEST_PERM 加到系统默认角色
    result = await backfill_role_perms(
        perms=[TEST_PERM], tenant_code=t["code"], dry_run=False
    )
    # 命中三档：管理员/门店经理/前台
    assert result["affected"] >= 3, result
    role_names = {r["name"] for r in result["rows"]}
    assert role_names == {"管理员", "门店经理", "前台"}
    # 自定义角色不应出现在 affected 列表
    assert "专属管家" not in role_names

    # 落库复核
    custom_after = next(
        r for r in client.get(f"/api/v1/tenants/{t['code']}/roles").json()
        if r["name"] == "专属管家"
    )
    assert TEST_PERM not in custom_after["permissions"]
    assert custom_after["permissions"] == ["fnb.manage"]

    # 系统三档必须有 TEST_PERM
    for name in ("管理员", "门店经理", "前台"):
        r = _read_role(client, t["code"], name)
        assert TEST_PERM in r["permissions"], f"{name} 没拿到 {TEST_PERM}"


@pytest.mark.asyncio
async def test_backfill_dry_run_does_not_persist(
    client: TestClient, tmp_path
) -> None:
    """dry-run 必须零写入。"""
    from scripts.backfill_role_perms import backfill_role_perms

    t = _seed(client, "t_backfill_dry")

    # 拿到前台角色初始权限
    staff_before = _read_role(client, t["code"], "前台")
    initial = list(staff_before["permissions"])

    # dry-run 一次（用 default 三档一定没有的虚拟码触发 affected > 0）
    result = await backfill_role_perms(
        perms=["billing.reconcile"], tenant_code=t["code"], dry_run=True
    )
    assert result["affected"] >= 1  # 至少前台会被计入 dry-run

    # 落库复核：权限没变
    staff_after = _read_role(client, t["code"], "前台")
    assert staff_after["permissions"] == initial
    assert "billing.reconcile" not in staff_after["permissions"]


@pytest.mark.asyncio
async def test_backfill_unknown_tenant_returns_zero(client: TestClient, tmp_path) -> None:
    """租户 code 不存在时：返回 0 affected，不抛异常。"""
    from scripts.backfill_role_perms import backfill_role_perms

    result = await backfill_role_perms(
        perms=[TEST_PERM], tenant_code="nonexistent-tenant-9999", dry_run=False
    )
    assert result["affected"] == 0
    assert result["rows"] == []
