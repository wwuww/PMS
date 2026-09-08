"""M32.18 权限回填脚本：把指定权限点授予所有 is_system=True 的默认角色。

**绝不**触碰 is_system=False 的自定义角色（避免静默扩权）。

**用法**
    cd F:/PMS/pms
    # 预览影响（不写库）
    ./.venv/Scripts/python.exe scripts/backfill_role_perms.py \\
        --perms billing.refund,billing.adjust --dry-run

    # 真正回填（全租户）
    ./.venv/Scripts/python.exe scripts/backfill_role_perms.py \\
        --perms billing.refund

    # 限定单个租户
    ./.venv/Scripts/python.exe scripts/backfill_role_perms.py \\
        --perms billing.deposit --tenant rbac1
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

logger = logging.getLogger(__name__)

# 系统默认三档角色的名称（与 ``permissions.DEFAULT_ROLES`` 一致）
DEFAULT_ROLE_NAMES: set[str] = {"管理员", "门店经理", "前台"}


async def backfill_role_perms(
    perms: list[str],
    tenant_code: str | None = None,
    dry_run: bool = True,
) -> dict:
    """把 ``perms`` 加入所有 ``is_system=True`` 的默认角色；自定义角色不受影响。

    Returns:
        一个 dict：``{"affected": int, "rows": [{"tenant_id", "name", "added": [...]}]}``
    """
    factory = db_session._session_factory
    if factory is None:
        db_session.get_engine()
        factory = db_session._session_factory
    if factory is None:
        raise RuntimeError("db_session factory not initialized")

    rows: list[dict] = []
    async with factory() as session:
        # tenant_code 是业务标识（Tenant.code），同时也是 Role.tenant_id 的取值。
        # 不需要先查 Tenant —— 字符串直接匹配多租户字段即可，更轻量。
        if tenant_code:
            stmt = select(Role).where(
                Role.is_system.is_(True), Role.tenant_id == tenant_code
            )
        else:
            stmt = select(Role).where(Role.is_system.is_(True))
        result = await session.execute(stmt)
        roles = list(result.scalars())
        target_perms = set(perms)
        for r in roles:
            if r.name not in DEFAULT_ROLE_NAMES:
                continue
            old = set(r.permissions or [])
            added = target_perms - old
            if not added:
                continue
            row = {
                "tenant_id": r.tenant_id,
                "name": r.name,
                "added": sorted(added),
            }
            if not dry_run:
                r.permissions = sorted(old | target_perms)
                session.add(r)
            rows.append(row)
        if not dry_run:
            await session.commit()
    return {"affected": len(rows), "rows": rows}

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--perms",
        required=True,
        help="逗号分隔的权限码列表，例如 billing.refund,billing.adjust",
    )
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
    perms = [p.strip() for p in args.perms.split(",") if p.strip()]
    if not perms:
        print("ERROR: --perms 不可为空", file=sys.stderr)
        return 2
    result = asyncio.run(
        backfill_role_perms(perms=perms, tenant_code=args.tenant, dry_run=args.dry_run)
    )
    if "skipped" in result:
        print(f"[backfill] {result['skipped']}")
        return 1
    for r in result["rows"]:
        print(f"  + tenant={r['tenant_id']} role={r['name']!r} add={r['added']}")
    if result["affected"] == 0 and tenant_code is not None:
        # 限定租户但无任何角色被影响：可能 tenant_code 不存在；提示而非静默
        print(
            f"[backfill] WARNING: 租户 {tenant_code!r} 没有可影响的系统角色（不存在？未播种？）",
            file=sys.stderr,
        )
        return 1
    print(
        f"[backfill] {'(dry-run) ' if args.dry_run else ''}affected {result['affected']} system roles"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
