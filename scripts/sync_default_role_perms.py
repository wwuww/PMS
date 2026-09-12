"""按 ``permissions.DEFAULT_ROLES`` 定义，把既有租户的系统角色权限补齐到最新。

与 ``backfill_role_perms.py`` 的区别
------------------------------------
``backfill_role_perms.py`` 把 ``--perms`` **一视同仁**地加给所有系统角色。这在
补齐「三档都有」的权限时没问题，但遇到**按档位差异化**的权限就会**越权扩权**——
例如 ``blacklist.manage`` 按设计仅授予「管理员 / 门店经理」，用旧脚本补会给
「前台」也加上，属于安全事故。

本脚本改为**以 ``DEFAULT_ROLES`` 为唯一真值来源**，逐角色补齐其定义内的权限：

- 只增不减：不撤销角色上已有的任何权限（避免动到人工额外授予的项）
- 不越权：绝不授予 ``DEFAULT_ROLES`` 对该角色未定义的权限
- 只碰系统角色：``is_system=True`` 且角色名属于默认三档；``is_system=False``
  的自定义角色**完全不触碰**

用法
----
    cd F:/PMS/pms

    # 预览（不写库）
    ./.venv/Scripts/python.exe scripts/sync_default_role_perms.py --dry-run

    # 真正同步（全租户）
    ./.venv/Scripts/python.exe scripts/sync_default_role_perms.py

    # 限定单个租户
    ./.venv/Scripts/python.exe scripts/sync_default_role_perms.py --tenant DEMO2026
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# 让脚本能 ``import app``
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from sqlalchemy import select  # noqa: E402

from app.db import session as db_session  # noqa: E402
from app.models.rbac import Role  # noqa: E402
from app.services.permissions import DEFAULT_ROLES  # noqa: E402

logger = logging.getLogger(__name__)

# 默认三档角色名（与 permissions.DEFAULT_ROLES 的名称列一致）
DEFAULT_ROLE_NAMES: set[str] = {"管理员", "门店经理", "前台"}


def _expected_perms_by_role() -> dict[str, set[str]]:
    """从 ``DEFAULT_ROLES`` 读出「角色名 → 应有权限集合」。

    ``DEFAULT_ROLES`` 的结构是 ``(name, code, is_hotel_scoped, perms)`` 四元组。
    """
    return {name: set(perms) for name, _code, _scoped, perms in DEFAULT_ROLES}


async def sync_default_role_perms(
    tenant_code: str | None = None,
    dry_run: bool = True,
) -> dict:
    """把各系统角色的权限补齐到 ``DEFAULT_ROLES`` 的定义（只增不减）。"""
    factory = db_session._session_factory
    if factory is None:
        db_session.get_engine()
        factory = db_session._session_factory
    if factory is None:
        raise RuntimeError("db_session factory not initialized")

    expected_by_role = _expected_perms_by_role()
    rows: list[dict] = []
    async with factory() as session:
        if tenant_code:
            stmt = select(Role).where(
                Role.is_system.is_(True), Role.tenant_id == tenant_code
            )
        else:
            stmt = select(Role).where(Role.is_system.is_(True))
        result = await session.execute(stmt)
        roles = list(result.scalars())

        for r in roles:
            if r.name not in DEFAULT_ROLE_NAMES:
                continue
            expected = expected_by_role.get(r.name)
            if not expected:
                # DEFAULT_ROLES 里没定义该名称 —— 不猜，跳过并记录
                logger.warning("角色 %r 不在 DEFAULT_ROLES 中，跳过", r.name)
                continue
            old = set(r.permissions or [])
            added = expected - old
            if not added:
                continue
            rows.append(
                {
                    "tenant_id": r.tenant_id,
                    "name": r.name,
                    "added": sorted(added),
                    # 兜底自检：理论上恒为空，非空说明脚本逻辑与预期不符
                    "would_exceed": sorted((old | expected) - expected),
                }
            )
            if not dry_run:
                r.permissions = sorted(old | expected)
                session.add(r)
        if not dry_run:
            await session.commit()
    return {"affected": len(rows), "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tenant",
        default=None,
        help="限定租户 code；不传则所有租户",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印影响，不写库",
    )
    args = ap.parse_args()

    result = asyncio.run(
        sync_default_role_perms(tenant_code=args.tenant, dry_run=args.dry_run)
    )

    # 自检：不应出现「补齐后超出该角色定义」的情况
    exceeded = [r for r in result["rows"] if r["would_exceed"]]
    if exceeded:
        print("[sync] ERROR: 检测到越权补齐，终止：", file=sys.stderr)
        for r in exceeded:
            print(
                f"  ! tenant={r['tenant_id']} role={r['name']!r} "
                f"越权项={r['would_exceed']}",
                file=sys.stderr,
            )
        return 2

    for r in result["rows"]:
        print(f"  + tenant={r['tenant_id']} role={r['name']!r} add={r['added']}")
    print(
        f"[sync] {'(dry-run) ' if args.dry_run else ''}"
        f"affected {result['affected']} system roles"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
