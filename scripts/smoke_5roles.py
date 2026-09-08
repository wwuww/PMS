#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PMS 5 角色功能验收 · 真实栈端点可达性冒烟
================================================

目的
----
把「5 角色功能验收评审」中对前台/店总/财务/客房/餐厅 5 类角色的
"文档交付" 结论升级为"实测端点可达"证据：登录一次，对每个角色取
**一条代表性读链路**（GET，无副作用），断言 200 且返回结构正确。

设计
----
  - 零三方依赖（标准库 urllib）。
  - 自动绕过沙箱透明代理（清 http(s)_proxy + NO_PROXY=*）。
  - 自带后端生命周期：复用 8000 实例；无实例且 --spawn 时自建。
  - 只读，不污染演示库。

退出码：0 = 全部通过；1 = 存在失败项。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

# 1. 禁用代理（必须在任何网络调用前）
for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

PMD_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BASE = "http://127.0.0.1:8000"
DEFAULT_TENANT = "DEMO2026"
DEFAULT_USER = "admin"
DEFAULT_PASS = "admin123"

RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"


class Results:
    def __init__(self) -> None:
        self.items: list[tuple[str, bool, str]] = []

    def add(self, name: str, ok: bool, detail: str = "") -> bool:
        self.items.append((name, ok, detail))
        mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        line = f"  [{mark}] {name}"
        if detail:
            line += f" — {detail}"
        print(line)
        return ok

    @property
    def failed(self) -> int:
        return sum(1 for _, ok, _ in self.items if not ok)


def http_req(base, method, path, *, token=None, json_body=None, expect=(200, 201), timeout=15):
    url = base.rstrip("/") + path
    data = json.dumps(json_body).encode() if json_body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.status
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        code = exc.code
        raw = exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa
        return -1, None, f"neterr:{exc}"
    try:
        parsed = json.loads(raw) if raw else None
    except Exception:
        parsed = raw
    return code, parsed, ("" if code in expect else f"http {code}")


def is_up(base: str) -> bool:
    code, _, _ = http_req(base, "GET", "/health", expect=(200,))
    return code == 200


def ensure_server(base: str, spawn: bool):
    if is_up(base):
        print(f"{YELLOW}· 复用已有服务 {base}{RESET}")
        return None
    if not spawn:
        print(f"{RED}· 服务未运行且未指定 --spawn：{base}{RESET}")
        return None
    print(f"{YELLOW}· 启动后端（uvicorn）…{RESET}")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", "8000"],
        cwd=PMD_ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=os.environ,
    )
    for _ in range(40):
        if is_up(base):
            print(f"{GREEN}· 后端就绪{RESET}")
            return proc
        time.sleep(0.5)
    print(f"{RED}· 后端启动超时{RESET}")
    proc.terminate()
    return None


# 5 角色 × 一条代表性读链路（GET，无副作用）
ROLE_ENDPOINTS = [
    ("前台经理 Front Desk",
     "预订/房态主读链路",
     "/api/v1/tenants/{t}/bookings",
     "list"),
    ("店总 GM",
     "经营看板 KPI",
     "/api/v1/tenants/{t}/analytics/dashboard?hotel_id={h}",
     "dict"),
    ("财务经理 Finance",
     "夜审日报 / 营业日",
     "/api/v1/tenants/{t}/daily-reports",
     "list"),
    ("客房经理 Housekeeping",
     "清扫/查房工单列表",
     "/api/v1/tenants/{t}/housekeeping-tasks",
     "list"),
    ("餐厅经理 Restaurant",
     "餐饮开单列表",
     "/api/v1/tenants/{t}/fnb/orders?hotel_id={h}",
     "list"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="PMS 5 角色端点可达性冒烟")
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--tenant", default=DEFAULT_TENANT)
    ap.add_argument("--username", default=DEFAULT_USER)
    ap.add_argument("--password", default=DEFAULT_PASS)
    ap.add_argument("--spawn", action="store_true")
    args = ap.parse_args()

    base = args.base_url
    print(f"\n{BOLD}PMS 5 角色端点可达性冒烟 · {base}{RESET}")
    print(f"租户={args.tenant} 用户={args.username}\n")

    proc = ensure_server(base, args.spawn)
    if not is_up(base):
        print(f"{RED}后端不可达，冒烟中止。{RESET}")
        if proc:
            proc.terminate()
        return 1

    res = Results()
    tenant = args.tenant

    code, _, _ = http_req(base, "GET", "/health", expect=(200,))
    res.add("服务存活 /health", code == 200, f"http {code}")

    code, body, _ = http_req(
        base, "POST", f"/api/v1/tenants/{tenant}/auth/login",
        expect=(200,),
        json_body={"username": args.username, "password": args.password},
    )
    token = (body or {}).get("token") if isinstance(body, dict) else None
    res.add("登录获取 token（5 角色共用鉴权）", bool(token) and code == 200,
            f"http {code}" if token else "无 token")
    if not token:
        _finish(res, proc)
        return 0 if res.failed == 0 else 1

    # 取一个 hotel_id 供店总看板等需要 hotel_id 的端点使用
    _, hotels_body, _ = http_req(base, "GET", f"/api/v1/tenants/{tenant}/hotels", token=token)
    hotels = hotels_body if isinstance(hotels_body, list) else []
    hotel_id = (hotels[0].get("id") if hotels else None) or 1
    print(f"  (演示库 hotel_id={hotel_id}, 共 {len(hotels)} 家门店)\n")

    print("")
    for role, scen, path, kind in ROLE_ENDPOINTS:
        url = path.format(t=tenant, h=hotel_id)
        code, body, _ = http_req(base, "GET", url, token=token)
        ok = code == 200
        if kind == "list":
            arr = body if isinstance(body, list) else []
            detail = f"http {code}, 返回 {len(arr)} 条" if ok else f"http {code}"
        elif kind == "dict":
            detail = f"http {code}, 字段数 {len(body) if isinstance(body, dict) else '?'}" if ok else f"http {code}"
        else:
            detail = f"http {code}"
        res.add(f"{role} · {scen}", ok, detail)

    _finish(res, proc)
    return 0 if res.failed == 0 else 1


def _finish(res: Results, proc) -> None:
    total = len(res.items)
    failed = res.failed
    print("\n" + "=" * 56)
    print(f"{BOLD}结果：{total - failed}/{total} 通过" +
          (f"，{failed} 失败{RESET}" if failed else f"{RESET}"))
    print("=" * 56 + "\n")
    if proc:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
