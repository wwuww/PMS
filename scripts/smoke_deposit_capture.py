#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""预授权请款（capture）端到端冒烟脚本（可复用回归工具）
================================================================

用途
----
验证「刷预授权(AUTHORIZED) → 请款(CAPTURED) → 冲抵到账单」这条链在**真实 HTTP
服务**上跑得通，而不只是单测绿。补齐「469 个单测全过但没人真跑过一遍业务流」
的缺口。

覆盖 12 项断言
--------------
 1. 鉴权：不带 token 调 ``POST /deposits/{id}/capture`` → 401
 2. 刷预授权：``kind=PREAUTH`` → ``status=AUTHORIZED``
 3. 对照：未请款的预授权调 apply → 409 ``DEPOSIT_NOT_HELD``
 4. 部分请款：capture 10000/30000 → ``CAPTURED``, amount 收敛, captured_at 非空, version+1
 5. ⚠ 请款不重复计营收：capture 前后 ``bill.balance`` **完全相等**（且 Payment 不增）
 6. 请款后可冲抵：apply → balance 减少、status=APPLIED、applied_cents 正确
 7. 超额请款 → 409 ``DEPOSIT_CAPTURE_EXCEEDS``
 8. 实收押金请款 → 409 ``DEPOSIT_NOT_PREAUTH``
 9. 已请款不能释放 → 409 ``DEPOSIT_PREAUTH_CAPTURED``
10. 未误伤：AUTHORIZED 正常 release → ``RELEASED``
11. 请款后可退款：refund 带 note → 成功；不带 note 被拒（审计强制）
12. P1 回归：``?status=CAPTURED`` 能筛出 / ``?status=HELD`` 不含它（筛选静默失效不复发）

设计原则（照搬 ``scripts/e2e_smoke.py``）
------------------------------------------
  - 零三方依赖：HTTP 用标准库 ``urllib``。
  - **自动绕过沙箱透明代理**：显式清掉 ``http(s)_proxy`` 并设 ``NO_PROXY=*``。
    本机存在 ``http_proxy=127.0.0.1:53683``，不清的话访问 127.0.0.1 会返回 502 假失败。
  - 自带后端生命周期：默认复用已在目标端口监听的实例；``--spawn`` 时用 venv 拉起
    uvicorn，跑完自动回收（**仅回收自建的**）。
  - 每次运行新建独立租户，互不干扰、可重复执行。

用法
----
  python scripts/smoke_deposit_capture.py                       # 复用 127.0.0.1:8000
  python scripts/smoke_deposit_capture.py --spawn               # 自起 uvicorn 跑完自毁
  python scripts/smoke_deposit_capture.py --base-url http://127.0.0.1:8011 --spawn

退出码
------
  0 = 全部通过；1 = 存在失败项（含准备阶段失败）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# ---- 1. 禁用代理（必须在任何网络调用前）------------------------------------
for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

PMS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # pms/ 根

DEFAULT_BASE = "http://127.0.0.1:8000"
DEFAULT_USER = "admin"
DEFAULT_PASS = "admin123"

RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"

# 业务常量（分）
PREAUTH_AMOUNT = 30000      # 主链路预授权额度 300.00 元
CAPTURE_AMOUNT = 10000      # 部分请款 100.00 元
ROOM_CHARGE = 50000         # 挂一笔房费，让账单余额为正（更贴近真实场景）


# ---- 2. 结果收集 ------------------------------------------------------------
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


# ---- 3. HTTP 助手 -----------------------------------------------------------
def http_req(
    base: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    json_body: Any = None,
    timeout: int = 20,
) -> tuple[int, Any, str]:
    """发请求，返回 ``(code, parsed_body, err)``。4xx/5xx 也视为正常响应（带码）。"""
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
    except urllib.error.HTTPError as exc:  # 4xx/5xx
        code = exc.code
        raw = exc.read().decode("utf-8", "replace")
    except Exception as exc:  # 网络层错误
        return -1, None, f"neterr:{exc}"
    try:
        parsed = json.loads(raw) if raw else None
    except Exception:
        parsed = raw
    return code, parsed, ""


def detail_of(body: Any) -> str:
    """FastAPI 错误体 → 可读字符串（无 detail 时退回紧凑 JSON，便于排障）。"""
    if isinstance(body, dict):
        if isinstance(body.get("detail"), str):
            return body["detail"]
        return json.dumps(body, ensure_ascii=False)[:160]
    return str(body)


def is_up(base: str) -> bool:
    code, _, _ = http_req(base, "GET", "/health", timeout=5)
    return code == 200


# ---- 4. 后端生命周期 --------------------------------------------------------
def _python_exe() -> str:
    """优先用项目 venv 解释器（Windows / POSIX 两种布局）。"""
    for rel in (".venv/Scripts/python.exe", ".venv/bin/python"):
        cand = os.path.join(PMS_ROOT, *rel.split("/"))
        if os.path.exists(cand):
            return cand
    return sys.executable


def ensure_server(base: str, spawn: bool) -> subprocess.Popen | None:
    if is_up(base):
        print(f"{YELLOW}· 复用已有服务 {base}{RESET}")
        return None
    if not spawn:
        print(f"{RED}· 服务未运行且未指定 --spawn：{base}{RESET}")
        return None
    host = urllib.parse.urlparse(base).hostname or "127.0.0.1"
    port = urllib.parse.urlparse(base).port or 8000
    print(f"{YELLOW}· 启动后端（uvicorn {host}:{port}）…{RESET}")
    proc = subprocess.Popen(
        [_python_exe(), "-m", "uvicorn", "app.main:app",
         "--host", host, "--port", str(port)],
        cwd=PMS_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=os.environ,
    )
    for _ in range(60):
        if is_up(base):
            print(f"{GREEN}· 后端就绪{RESET}")
            return proc
        time.sleep(0.5)
    print(f"{RED}· 后端启动超时{RESET}")
    proc.terminate()
    return None


def _finish(res: Results, proc: subprocess.Popen | None) -> None:
    total = len(res.items)
    failed = res.failed
    print("\n" + "=" * 62)
    print(
        f"{BOLD}结果：{total - failed}/{total} 通过"
        + (f"，{failed} 失败{RESET}" if failed else f"{RESET}")
    )
    print("=" * 62 + "\n")
    if proc:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()


# ---- 5. 主流程 --------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="预授权请款 capture 端到端冒烟")
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--username", default=DEFAULT_USER)
    ap.add_argument("--password", default=DEFAULT_PASS)
    ap.add_argument("--spawn", action="store_true", help="无实例时自动拉起后端，跑完回收")
    args = ap.parse_args()

    global BASE
    BASE = args.base_url

    print(f"\n{BOLD}PMS 预授权请款（capture）端到端冒烟 · {BASE}{RESET}\n")

    proc = ensure_server(BASE, args.spawn)
    if not is_up(BASE):
        print(f"{RED}后端不可达，冒烟中止。{RESET}")
        if proc:
            proc.terminate()
        return 1

    res = Results()
    try:
        return _run(args, res, proc)
    finally:
        # 自建实例必须回收，异常路径也不能留残留进程
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=8)
            except Exception:
                proc.kill()


def _run(args: argparse.Namespace, res: Results, proc: subprocess.Popen | None) -> int:

    def req(method: str, path: str, *, token: str | None = None, body: Any = None):
        return http_req(BASE, method, path, token=token, json_body=body)

    # ================= 准备阶段 =================
    print(f"{BOLD}[准备]{RESET}")
    stamp = f"{int(time.time())}"
    tenant = f"cap-{stamp}"

    code, body, err = req("POST", "/api/v1/tenants", body={"code": tenant, "name": "请款冒烟"})
    if not res.add("开租户", code == 201, f"http {code} {tenant}"):
        _finish(res, proc)
        return 1

    code, body, err = req(
        "POST", f"/api/v1/tenants/{tenant}/auth/login",
        body={"username": args.username, "password": args.password},
    )
    token = body.get("token") if isinstance(body, dict) else None
    if not res.add("管理员登录", code == 200 and bool(token), f"http {code}"):
        _finish(res, proc)
        return 1

    code, hotel, _ = req("POST", f"/api/v1/tenants/{tenant}/hotels", token=token,
                         body={"code": "H1", "name": "请款冒烟店"})
    if not res.add("建门店", code == 201, f"http {code}"):
        _finish(res, proc)
        return 1
    hid = hotel["id"]

    code, rt, _ = req("POST", f"/api/v1/tenants/{tenant}/room-types", token=token,
                      body={"code": "STD", "name": "标间", "base_price": 30000})
    if not res.add("建房型", code == 201, f"http {code}"):
        _finish(res, proc)
        return 1
    rtid = rt["id"]

    code, rooms, _ = req("POST", f"/api/v1/hotels/{hid}/rooms", token=token, body=[
        {"room_type_id": rtid, "room_no": "0101", "floor": "1"},
        {"room_type_id": rtid, "room_no": "0102", "floor": "1"},
    ])
    if not res.add("建房间", code == 201, f"http {code}, {len(rooms or [])} 间"):
        _finish(res, proc)
        return 1

    code, bk, _ = req("POST", f"/api/v1/tenants/{tenant}/bookings", token=token, body={
        "hotel_id": hid, "room_type_id": rtid, "guest_name": "请款客",
        "guest_phone": "13900001111",
        "check_in_date": "2026-10-01", "check_out_date": "2026-10-05", "room_no": "0101",
    })
    if not res.add("建订单", code in (200, 201), f"http {code} {detail_of(bk)[:120]}"):
        _finish(res, proc)
        return 1
    booking_id = bk["id"]

    code, ci, _ = req("POST", f"/api/v1/tenants/{tenant}/bookings/{booking_id}/check-in",
                      token=token, body={"room_no": "0101"})
    if not res.add("办理入住", code == 200, f"http {code} {detail_of(ci)[:120]}"):
        _finish(res, proc)
        return 1

    # 入住自动开账 → 反查 bill_id
    code, bills, _ = req("GET", f"/api/v1/tenants/{tenant}/bills?source=BOOKING", token=token)
    bill = next((b for b in (bills or []) if str(b.get("booking_id")) == str(booking_id)), None)
    if not res.add("开账（入住联动）", bill is not None, f"http {code}, bills={len(bills or [])}"):
        _finish(res, proc)
        return 1
    bill_id = bill["id"]

    # 挂一笔房费，让账单余额为正（贴近真实场景，也让「apply 后 balance 减少」可读）
    code, _, _ = req("POST", f"/api/v1/tenants/{tenant}/bills/{bill_id}/charges", token=token,
                     body={"charge_type": "ROOM_CHARGE", "amount": ROOM_CHARGE,
                           "description": "房费", "operator": "front_desk"})
    res.add(f"挂房费 {ROOM_CHARGE} 分", code == 200, f"http {code}")

    def get_bill() -> dict:
        c, b, _ = req("GET", f"/api/v1/tenants/{tenant}/bills/{bill_id}", token=token)
        return b if isinstance(b, dict) else {}

    def mk_deposit(kind: str, method: str, amount: int, note: str | None = None) -> dict:
        c, b, _ = req("POST", f"/api/v1/tenants/{tenant}/deposits", token=token, body={
            "hotel_id": hid, "booking_id": booking_id, "room_no": "0101",
            "bill_id": bill_id, "kind": kind, "method": method,
            "amount": amount, "operator": "front_desk", "note": note,
        })
        return (b if isinstance(b, dict) else {"_code": c, "_err": detail_of(b)})

    print(f"\n{BOLD}[验证]{RESET}")

    # ---------- 1. 鉴权 ----------
    code, body, _ = req("POST", f"/api/v1/tenants/{tenant}/deposits/1/capture", body={"amount": 1})
    res.add("1. 无 token 调 capture 必须 401", code == 401, f"http {code}")

    # ---------- 2. 刷预授权 ----------
    a = mk_deposit("PREAUTH", "UNIONPAY", PREAUTH_AMOUNT, note="预授权冻结")
    a_id = a.get("id")
    res.add(
        "2. 刷预授权 → AUTHORIZED",
        a.get("status") == "AUTHORIZED" and a.get("amount_cents") == PREAUTH_AMOUNT,
        f"id={a_id} status={a.get('status')} amount={a.get('amount_cents')} v={a.get('version')}",
    )
    if not a_id:
        _finish(res, proc)
        return 1
    v_before = int(a.get("version") or 0)

    # ---------- 3. 未请款不能冲抵（对照组） ----------
    code, body, _ = req("POST", f"/api/v1/tenants/{tenant}/deposits/{a_id}/apply",
                        token=token, body={"amount": 1000})
    res.add(
        "3. 未请款冲抵被拒（409 DEPOSIT_NOT_HELD）",
        code == 409 and "DEPOSIT_NOT_HELD" in detail_of(body),
        f"http {code} {detail_of(body)[:80]}",
    )

    # ---------- 5 的前置：capture 前账单快照 ----------
    bill_before = get_bill()
    bal_before = int(bill_before.get("balance") or 0)
    pay_before = len(bill_before.get("payments") or [])

    # ---------- 4. 部分请款 ----------
    code, cap, _ = req("POST", f"/api/v1/tenants/{tenant}/deposits/{a_id}/capture",
                       token=token, body={"amount": CAPTURE_AMOUNT})
    res.add(
        f"4. 部分请款 {CAPTURE_AMOUNT}/{PREAUTH_AMOUNT} → CAPTURED",
        code == 200
        and cap.get("status") == "CAPTURED"
        and cap.get("amount_cents") == CAPTURE_AMOUNT
        and bool(cap.get("captured_at"))
        and int(cap.get("version") or 0) == v_before + 1,
        f"http {code} status={cap.get('status')} amount={cap.get('amount_cents')} "
        f"captured_at={cap.get('captured_at')} v={v_before}→{cap.get('version')}",
    )

    # ---------- 5. ⚠ 请款不重复计营收 ----------
    bill_after = get_bill()
    bal_after = int(bill_after.get("balance") or 0)
    pay_after = len(bill_after.get("payments") or [])
    res.add(
        "5. ⚠ 请款不重复计营收（balance 不变 / 未写 Payment）",
        bal_before == bal_after and pay_before == pay_after,
        f"balance {bal_before} → {bal_after}；payments {pay_before} → {pay_after}",
    )

    # ---------- 6. 请款后可冲抵 ----------
    code, ap_out, _ = req("POST", f"/api/v1/tenants/{tenant}/deposits/{a_id}/apply",
                          token=token,
                          body={"amount": CAPTURE_AMOUNT, "target_bill_id": bill_id})
    bill_applied = get_bill()
    bal_applied = int(bill_applied.get("balance") or 0)
    res.add(
        "6. 请款后可冲抵（balance 减少 / APPLIED）",
        code == 200
        and ap_out.get("status") == "APPLIED"
        and ap_out.get("applied_cents") == CAPTURE_AMOUNT
        and bal_applied == bal_after - CAPTURE_AMOUNT,
        f"http {code} status={ap_out.get('status')} applied={ap_out.get('applied_cents')} "
        f"balance {bal_after} → {bal_applied}（应 -{CAPTURE_AMOUNT}）",
    )

    # ---------- 7. 超额请款被拒 ----------
    b = mk_deposit("PREAUTH", "UNIONPAY", 5000, note="超额用例")
    b_id = b.get("id")
    code, body, _ = req("POST", f"/api/v1/tenants/{tenant}/deposits/{b_id}/capture",
                        token=token, body={"amount": 5001})
    res.add(
        "7. 超额请款被拒（409 DEPOSIT_CAPTURE_EXCEEDS）",
        code == 409 and "DEPOSIT_CAPTURE_EXCEEDS" in detail_of(body),
        f"http {code} {detail_of(body)[:80]}",
    )

    # ---------- 8. 实收押金请款被拒 ----------
    c = mk_deposit("DEPOSIT", "CASH", 8000, note="实收押金")
    c_id = c.get("id")
    res.add(
        "8-pre. 收实收押金 → HELD",
        c.get("status") == "HELD",
        f"id={c_id} status={c.get('status')}",
    )
    code, body, _ = req("POST", f"/api/v1/tenants/{tenant}/deposits/{c_id}/capture",
                        token=token, body={"amount": 8000})
    res.add(
        "8. 实收押金请款被拒（409 DEPOSIT_NOT_PREAUTH）",
        code == 409 and "DEPOSIT_NOT_PREAUTH" in detail_of(body),
        f"http {code} {detail_of(body)[:80]}",
    )

    # ---------- 9. 已请款不能再释放 ----------
    d = mk_deposit("PREAUTH", "UNIONPAY", 6000, note="释放/退款用例")
    d_id = d.get("id")
    code, d_cap, _ = req("POST", f"/api/v1/tenants/{tenant}/deposits/{d_id}/capture",
                         token=token, body={})  # 空体 = 全额请款
    res.add(
        "9-pre. 全额请款（amount 缺省）→ CAPTURED",
        code == 200 and d_cap.get("status") == "CAPTURED" and d_cap.get("amount_cents") == 6000,
        f"http {code} status={d_cap.get('status')} amount={d_cap.get('amount_cents')}",
    )
    code, body, _ = req("POST", f"/api/v1/tenants/{tenant}/deposits/{d_id}/release",
                        token=token, body={})
    res.add(
        "9. 已请款不能再释放（409 DEPOSIT_PREAUTH_CAPTURED）",
        code == 409 and "DEPOSIT_PREAUTH_CAPTURED" in detail_of(body),
        f"http {code} {detail_of(body)[:80]}",
    )

    # ---------- 10. 未误伤：正常释放仍可用 ----------
    e = mk_deposit("PREAUTH", "UNIONPAY", 4000, note="正常释放用例")
    e_id = e.get("id")
    code, rel, _ = req("POST", f"/api/v1/tenants/{tenant}/deposits/{e_id}/release",
                       token=token, body={})
    res.add(
        "10. 未误伤：AUTHORIZED 正常释放 → RELEASED",
        code == 200 and rel.get("status") == "RELEASED",
        f"http {code} status={rel.get('status')} released_at={rel.get('released_at')}",
    )

    # ---------- 12. P1 回归：status 筛选未静默失效（先做，D 此时仍是 CAPTURED） ----------
    code, cap_list, _ = req("GET", f"/api/v1/tenants/{tenant}/deposits?status=CAPTURED",
                            token=token)
    cap_ids = [str(x.get("id")) for x in (cap_list or [])]
    code, held_list, _ = req("GET", f"/api/v1/tenants/{tenant}/deposits?status=HELD",
                             token=token)
    held_ids = [str(x.get("id")) for x in (held_list or [])]
    res.add(
        "12. P1 回归：?status=CAPTURED 筛出 / ?status=HELD 不含",
        str(d_id) in cap_ids
        and str(d_id) not in held_ids
        and str(c_id) in held_ids,  # HELD 非空才证明筛选真生效（不是空列表蒙对）
        f"CAPTURED={cap_ids}（含 {d_id}? {str(d_id) in cap_ids}）；"
        f"HELD={held_ids}（含实收押金 {c_id}? {str(c_id) in held_ids}；"
        f"误含已请款 {d_id}? {str(d_id) in held_ids}）",
    )

    # ---------- 11. 请款后可退款 ----------
    code, body, _ = req("POST", f"/api/v1/tenants/{tenant}/deposits/{d_id}/refund",
                        token=token, body={"amount": 6000})  # 故意不带 note
    res.add(
        "11a. 退款缺 note 被拒（审计强制留痕）",
        code in (400, 409) and "DEPOSIT_REASON_REQUIRED" in detail_of(body),
        f"http {code} {detail_of(body)[:80]}",
    )
    code, rf, _ = req("POST", f"/api/v1/tenants/{tenant}/deposits/{d_id}/refund",
                      token=token, body={"amount": 6000, "note": "客人退房，原路退回"})
    res.add(
        "11b. 已请款可退款（带 note）",
        code == 200 and rf.get("refunded_cents") == 6000 and rf.get("status") == "REFUNDED",
        f"http {code} status={rf.get('status')} refunded={rf.get('refunded_cents')}",
    )

    _finish(res, proc)
    return 0 if res.failed == 0 else 1


BASE = DEFAULT_BASE

if __name__ == "__main__":
    sys.exit(main())
