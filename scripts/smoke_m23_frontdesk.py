#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M23 前台运营深度 · 真实栈端到端冒烟
================================================

覆盖（对应验收清单 #3 / #4 / #11）：
  1. 服务存活 / 建租户 / 登录
  2. 客人检索：证件号 / 订单号 维度
  3. NoShow：手动标记（释放预分配锁房）+ 夜审自动标记
  4. 交班三口径：现金流 / 实收（全方式）/ 应收（正向条目）

设计：零三方依赖（urllib）；自动绕过代理；默认复用 8000 实例，
无实例且 --spawn 时自建并回收。隔离租户 m23-smoke-<ts>，不污染演示库。
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

for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

PMD_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BASE = "http://127.0.0.1:8000"

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


def http_req(base, method, path, *, token=None, json_body=None, expect=(200, 201), timeout=20):
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


def main() -> int:
    ap = argparse.ArgumentParser(description="M23 前台运营深度冒烟")
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--spawn", action="store_true")
    args = ap.parse_args()
    base = args.base_url

    print(f"\n{BOLD}M23 前台运营深度冒烟 · {base}{RESET}\n")
    proc = ensure_server(base, args.spawn)
    if not is_up(base):
        print(f"{RED}后端不可达，冒烟中止。{RESET}")
        if proc:
            proc.terminate()
        return 1

    res = Results()
    ts = int(time.time())
    tenant_code = f"m23-smoke-{ts}"

    # 1) 建租户 + 登录
    code, t, _ = http_req(base, "POST", "/api/v1/tenants",
                          json_body={"code": tenant_code, "name": "M23冒烟"})
    res.add("建隔离租户", code in (200, 201) and bool(t), f"{tenant_code}")
    code, body, _ = http_req(
        base, "POST", f"/api/v1/tenants/{tenant_code}/auth/login",
        json_body={"username": "admin", "password": "admin123"},
    )
    token = (body or {}).get("token")
    res.add("登录 admin/admin123", bool(token), f"http {code}")
    if not token:
        _finish(res, proc)
        return 0 if res.failed == 0 else 1
    hdr_note = ""

    # 2) 门店 / 房型 / 客房
    code, h, _ = http_req(base, "POST", f"/api/v1/tenants/{tenant_code}/hotels",
                          token=token, json_body={"code": "H", "name": "冒烟店"})
    res.add("建门店", code in (200, 201) and bool(h), hdr_note)
    code, rt, _ = http_req(base, "POST", f"/api/v1/tenants/{tenant_code}/room-types",
                           token=token,
                           json_body={"code": "STD", "name": "标间", "base_price": 30000})
    res.add("建房型", code in (200, 201) and bool(rt), "")
    http_req(base, "POST", f"/api/v1/hotels/{h['id']}/rooms", token=token,
             json_body=[{"room_type_id": rt["id"], "room_no": "0101"},
                        {"room_type_id": rt["id"], "room_no": "0102"}])

    def rooms() -> list[dict]:
        _, rr, _ = http_req(base, "GET", f"/api/v1/tenants/{tenant_code}/rooms", token=token)
        return rr if isinstance(rr, list) else []

    def state_of(no: str) -> str:
        return next((r.get("state") for r in rooms() if r.get("room_no") == no), "?")

    # 3) 清单#4 客人检索：证件号
    http_req(base, "POST", f"/api/v1/tenants/{tenant_code}/guests", token=token,
             json_body={"hotel_id": h["id"], "name": "张三", "phone": "13800001111",
                        "id_no": "440301199001011234"})
    code, rows, _ = http_req(base, "GET",
                             f"/api/v1/tenants/{tenant_code}/guests/search"
                             f"?id_no=440301199001011234", token=token)
    res.add("清单#4 按证件号检索", code == 200 and len(rows or []) == 1
            and rows[0]["name"] == "张三", f"http {code}, 命中 {len(rows or [])} 条")

    # 4) 清单#3 手动 NoShow（释放锁房）
    code, bk, _ = http_req(base, "POST", f"/api/v1/tenants/{tenant_code}/bookings",
                           token=token,
                           json_body={"hotel_id": h["id"], "room_type_id": rt["id"],
                                      "guest_name": "张三", "guest_phone": "13800001111",
                                      "check_in_date": "2026-10-01",
                                      "check_out_date": "2026-10-02", "room_no": "0101"})
    ok_lock = state_of("0101") == "arrival_locked"
    res.add("预订锁房 arrival_locked", ok_lock, f"state={state_of('0101')}")
    code, noshowed, _ = http_req(base, "POST",
                                 f"/api/v1/tenants/{tenant_code}/bookings/{bk['id']}/noshow",
                                 token=token, json_body={"reason": "客人来电告知无法到店"})
    res.add("清单#3 手动标记 NoShow", code == 200 and noshowed.get("status") == "noshow"
            and noshowed.get("noshow_reason") == "客人来电告知无法到店",
            f"http {code}, reason={noshowed.get('noshow_reason')}")
    res.add("清单#3 NoShow 释放锁房→vacant_clean",
            state_of("0101") == "vacant_clean", f"state={state_of('0101')}")

    # 5) 清单#4 订单号检索（经预订反查客档）
    code, rows, _ = http_req(base, "GET",
                             f"/api/v1/tenants/{tenant_code}/guests/search"
                             f"?booking_id={bk['id']}", token=token)
    res.add("清单#4 按订单号检索", code == 200 and len(rows or []) == 1
            and rows[0]["name"] == "张三", f"http {code}, 命中 {len(rows or [])} 条")

    # 6) 清单#11 交班三口径
    code, shift, _ = http_req(base, "POST", f"/api/v1/tenants/{tenant_code}/shifts/open",
                              token=token,
                              json_body={"hotel_id": h["id"], "cashier": "erin",
                                         "opening_float_cents": 0})
    code, bill, _ = http_req(base, "POST", f"/api/v1/tenants/{tenant_code}/bills",
                             token=token, json_body={"hotel_id": h["id"], "guest_name": "Z"})
    http_req(base, "POST", f"/api/v1/tenants/{tenant_code}/bills/{bill['id']}/charges",
             token=token,
             json_body={"charge_type": "ROOM_CHARGE", "amount": 12000, "operator": "erin"})
    http_req(base, "POST", f"/api/v1/tenants/{tenant_code}/bills/{bill['id']}/payments",
             token=token, json_body={"method": "CASH", "amount": 8000, "operator": "erin"})
    http_req(base, "POST", f"/api/v1/tenants/{tenant_code}/bills/{bill['id']}/payments",
             token=token, json_body={"method": "WECHAT", "amount": 4000, "operator": "erin"})
    code, closed, _ = http_req(base, "POST",
                               f"/api/v1/tenants/{tenant_code}/shifts/{shift['id']}/close",
                               token=token, json_body={"counted_cash_cents": 8000})
    res.add("清单#11 交班现金流（备用金+班内现金）",
            code == 200 and closed.get("expected_cash_cents") == 8000
            and closed.get("discrepancy_cents") == 0,
            f"expected={closed.get('expected_cash_cents')}, diff={closed.get('discrepancy_cents')}")
    res.add("清单#11 班内实收（全支付方式）=12000",
            closed.get("received_cents") == 12000, f"received={closed.get('received_cents')}")
    res.add("清单#11 班内应收（正向条目）=12000",
            closed.get("receivable_cents") == 12000, f"receivable={closed.get('receivable_cents')}")

    # 7) 清单#3 夜审自动 NoShow
    code, bk2, _ = http_req(base, "POST", f"/api/v1/tenants/{tenant_code}/bookings",
                            token=token,
                            json_body={"hotel_id": h["id"], "room_type_id": rt["id"],
                                       "guest_name": "王五", "guest_phone": "13800003333",
                                       "check_in_date": "2026-10-01",
                                       "check_out_date": "2026-10-02", "room_no": "0102"})
    code, rep, _ = http_req(base, "POST", f"/api/v1/tenants/{tenant_code}/night-audit",
                            token=token,
                            json_body={"hotel_id": h["id"], "business_date": "2026-10-02"})
    _, bl, _ = http_req(base, "GET", f"/api/v1/tenants/{tenant_code}/bookings", token=token)
    target = next((b for b in (bl or []) if b.get("id") == bk2.get("id")), {})
    res.add("清单#3 夜审自动 NoShow + 原因",
            rep is not None and target.get("status") == "noshow"
            and "逾期未到" in (target.get("noshow_reason") or ""),
            f"status={target.get('status')}, reason={target.get('noshow_reason')}")
    res.add("清单#3 夜审释放锁房→vacant_clean",
            state_of("0102") == "vacant_clean", f"state={state_of('0102')}")

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
