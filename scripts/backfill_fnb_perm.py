#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
权限回填（一次性数据修正）
================================================
M21 新增 F&B 模块，权限点 `fnb.manage` 已写入 DEFAULT_ROLES，
但 `seed_default_roles` 对**已存在**角色是幂等跳过的（不更新旧权限），
导致 M21 之前 seed 的租户（如 DEMO2026）其「管理员/门店经理/前台」角色
缺少 `fnb.manage`，访问 F&B 端点返回 403。

本脚本对指定租户（默认全部租户）的既有角色做**增量回填**：
仅当角色权限集中不含 `fnb.manage` 时才追加，绝不删除既有权限。
非破坏性、幂等、可重复运行。

用法：
  .venv/Scripts/python.exe scripts/backfill_fnb_perm.py            # 全部租户
  .venv/Scripts/python.exe scripts/backfill_fnb_perm.py DEMO2026   # 指定租户
"""

from __future__ import annotations

import os
import sys

# 确保 pms/ 根在 sys.path（脚本位于 scripts/ 下，直接运行不会自动加入 pms/）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.session import get_engine
from app.models.rbac import Role
from app.services.permissions import FNB_MANAGE


async def backfill(tenant_filter: str | None = None) -> dict:
    stats = {"roles_checked": 0, "roles_updated": 0, "tenants": set()}
    engine = get_engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        stmt = select(Role)
        if tenant_filter:
            stmt = stmt.where(Role.tenant_id == tenant_filter)
        roles = (await session.execute(stmt)).scalars().all()
        for role in roles:
            stats["roles_checked"] += 1
            stats["tenants"].add(role.tenant_id)
            perms = set(role.permissions or [])
            if FNB_MANAGE not in perms:
                perms.add(FNB_MANAGE)
                role.permissions = sorted(perms)
                stats["roles_updated"] += 1
                print(f"  + [{role.tenant_id}] {role.name}({role.level}) ← 追加 {FNB_MANAGE}")
        await session.commit()
    stats["tenants"] = sorted(stats["tenants"])
    return stats


def main() -> int:
    tenant = sys.argv[1] if len(sys.argv) > 1 else None
    print(f"权限回填：fnb.manage → 既有角色（租户={'全部' if tenant is None else tenant}）\n")
    import asyncio
    stats = asyncio.run(backfill(tenant))
    print(f"\n完成：检查 {stats['roles_checked']} 个角色，更新 {stats['roles_updated']} 个。")
    print(f"涉及租户：{', '.join(stats['tenants']) or '无'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
