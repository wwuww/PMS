"""扫描 FastAPI 路由并生成 ``routes_perm.allowlist.json``（M32.18 P0-2 渐进方案）。

**为什么需要这份台账？**
代码库现状：195 条路由里只有 ~30 条显式 ``require_perm``，其余约 165 条
（含约 100 条写路由）只要任意登录态即可访问；测试因 admin 旁路永远测不出
这个缺口。一次性全量补权限会引发大面积 403，故本 Sprint 走「显性化 + 防恶化」：
先把所有无权限路由登记到 allowlist，把隐性债务变成可度量、可逐条消化的显性
台账；下个 Sprint 再照单施工。

**用法**
    cd F:/PMS/pms
    ./.venv/Scripts/python.exe scripts/gen_route_perm_baseline.py \
        --output routes_perm.allowlist.json

    # 或者不传 --output，默认写到仓库根。

**输出格式（JSON）**
    {
      "generated_at": "2026-09-07T...",
      "total_routes": 195,
      "protected_count": 30,
      "unprotected_count": 165,
      "unprotected_writes_count": 97,
      "items": [
        {"method": "POST", "path": "/api/v1/tenants/{tenant_id}/...", "has_perm": false, "is_write": true},
        ...
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path


WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SKIP_METHODS = {"HEAD", "OPTIONS"}


def _is_perm_dep(dep) -> bool:  # noqa: ANN001
    """判断一个 FastAPI ``Depends`` 是否是 ``require_perm`` 装饰器。"""
    fn = getattr(dep, "call", None) or getattr(dep, "dependency", None)
    if fn is None:
        return False
    return (
        getattr(fn, "__name__", "") == "require_perm"
        and getattr(fn, "__module__", "") == "app.api.routes"
    )


def collect() -> list[dict]:
    """扫描 ``app.api.routes.router`` 的所有路由，输出每条路由的鉴权状态。

    说明：直接扫描 ``app.api.routes.router``（``APIRouter`` 实例），其内部
    ``routes`` 列表里的 path 形如 ``/tenants/{tenant_id}/...``，尚未叠加
    ``/api/v1`` 前缀。**真实 path 需手动加 prefix** 便于和 OpenAPI 一致。
    """
    # 让脚本既能从仓库根跑也能从 pms/ 目录跑
    repo_root = Path(__file__).resolve().parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from app.api.routes import router as api_router, require_perm  # noqa: WPS433
    from app.core.config import get_settings  # noqa: WPS433

    settings = get_settings()
    prefix = settings.api_v1_prefix or ""

    items: list[dict] = []
    for route in api_router.routes:
        if not hasattr(route, "methods") or not hasattr(route, "path"):
            continue
        deps = getattr(route, "dependencies", None) or []
        has_perm = any(
            (d is require_perm) or _is_perm_dep(d) for d in deps
        )
        full_path = f"{prefix}{route.path}"
        for method in route.methods - SKIP_METHODS:
            items.append(
                {
                    "method": method,
                    "path": full_path,
                    "has_perm": has_perm,
                    "is_write": method in WRITE_METHODS,
                }
            )
    # 稳定排序：按 path 字母序，再 method
    items.sort(key=lambda x: (x["path"], x["method"]))
    return items


def summarize(items: list[dict]) -> dict:
    unprotected_writes = [i for i in items if (not i["has_perm"]) and i["is_write"]]
    unprotected_reads = [i for i in items if (not i["has_perm"]) and (not i["is_write"])]
    protected = [i for i in items if i["has_perm"]]
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "total_routes": len(items),
        "protected_count": len(protected),
        "unprotected_count": len(items) - len(protected),
        "unprotected_writes_count": len(unprotected_writes),
        "unprotected_reads_count": len(unprotected_reads),
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 routes_perm.allowlist.json")
    parser.add_argument(
        "--output",
        default="routes_perm.allowlist.json",
        help="输出文件路径（相对仓库根或绝对路径）",
    )
    args = parser.parse_args()

    items = collect()
    summary = summarize(items)

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = Path(__file__).resolve().parent.parent / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        f"[route-perm-baseline] wrote {output_path} | total={summary['total_routes']} "
        f"protected={summary['protected_count']} unprotected={summary['unprotected_count']} "
        f"unprotected_writes={summary['unprotected_writes_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
