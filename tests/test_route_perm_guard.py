"""M32.18 权限守卫测试：阻止「新增写路由跳过 require_perm」被悄悄引入。

**门禁语义（M32.18 P0-2 渐进方案）**
- 基线台账 ``routes_perm.allowlist.json`` 登记当前所有「无 require_perm 的
  写路由」，作为可度量的隐性债务台账。
- 本测试**只允许债务减少**（新代码补了 require_perm），**不允许债务增加**
  （新增写路由必须带 require_perm，或显式登记到 allowlist）。
- 违反时列出 method + path，便于补权限或更新台账。

**注意**：更新台账后请把改动一起 commit，否则 CI 立刻挂。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.api.routes import router as api_router, require_perm  # noqa: WPS433
from app.core.config import get_settings  # noqa: WPS433

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SKIP_METHODS = {"HEAD", "OPTIONS"}

# 把仓库根加进 path，让 ``routes_perm.allowlist.json`` 在 CI 工作目录里找得到
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

ALLOWLIST_PATH = _REPO_ROOT / "routes_perm.allowlist.json"


def _is_perm_dep(dep) -> bool:  # noqa: ANN001
    fn = getattr(dep, "call", None) or getattr(dep, "dependency", None)
    if fn is None:
        return False
    return (
        getattr(fn, "__name__", "") == "require_perm"
        and getattr(fn, "__module__", "") == "app.api.routes"
    )


def _scan_current_unprotected_writes() -> set[tuple[str, str]]:
    """扫当前 ``api_router``，返回所有 (method, full_path) 的无权限写路由。"""
    settings = get_settings()
    prefix = settings.api_v1_prefix or ""
    out: set[tuple[str, str]] = set()
    for route in api_router.routes:
        if not hasattr(route, "methods") or not hasattr(route, "path"):
            continue
        deps = getattr(route, "dependencies", None) or []
        has_perm = any(
            (d is require_perm) or _is_perm_dep(d) for d in deps
        )
        if has_perm:
            continue
        full_path = f"{prefix}{route.path}"
        for method in route.methods - SKIP_METHODS:
            if method in WRITE_METHODS:
                out.add((method, full_path))
    return out


def _load_baseline_unprotected_writes() -> set[tuple[str, str]]:
    assert ALLOWLIST_PATH.exists(), (
        f"基线台账缺失：{ALLOWLIST_PATH}。请跑："
        f"python scripts/gen_route_perm_baseline.py --output routes_perm.allowlist.json"
    )
    data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    out: set[tuple[str, str]] = set()
    for item in data.get("items", []):
        if (not item["has_perm"]) and item["is_write"]:
            out.add((item["method"], item["path"]))
    return out


class TestRoutePermGuard:
    def test_no_new_unprotected_write_routes_outside_baseline(self) -> None:
        """新增写路由必须带 ``require_perm``，否则必须显式登记到 allowlist。"""
        baseline = _load_baseline_unprotected_writes()
        current = _scan_current_unprotected_writes()

        # 只允许减少（补了 require_perm），不允许新增
        new_offenders = current - baseline
        if new_offenders:
            lines = "\n".join(f"  - {m} {p}" for m, p in sorted(new_offenders))
            pytest.fail(
                "检测到新增的「无 require_perm 的写路由」未登记到基线台账：\n"
                f"{lines}\n\n"
                "请二选一：\n"
                "  1) 给路由加 ``dependencies=[Security(require_perm, scopes=[PERM])]``；\n"
                "  2) 若确实需要放开，重跑 ``scripts/gen_route_perm_baseline.py`` 重新生成台账并 commit。"
            )

    def test_baseline_allowlist_is_well_formed(self) -> None:
        """台账 schema 完整性：所有 items 都有 method/path/has_perm/is_write。"""
        data = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
        for key in ("generated_at", "total_routes", "protected_count", "items"):
            assert key in data, f"台账缺少 {key}"
        for i, item in enumerate(data["items"]):
            assert {"method", "path", "has_perm", "is_write"} <= set(item), (
                f"items[{i}] 缺字段: {item}"
            )
            assert isinstance(item["has_perm"], bool)
            assert isinstance(item["is_write"], bool)
            assert item["method"] in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
