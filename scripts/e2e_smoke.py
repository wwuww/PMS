#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PMS 端到端冒烟脚本（可复用回归工具）
================================================

用途
----
把「手动 curl 验证关键链路」固化为一键可跑的回归套件，覆盖：
  - 服务存活 / 登录鉴权
  - 通知中心点击跳转深链（link 字段、unread-count、read/read-all 幂等）
  - 房态 / 收益规则 / 收益建议 / 夜审报表 等核心读链路
  - WebSocket 订阅鉴权（无 token 必须拒绝、带 token 必须订阅成功）

设计原则
--------
  - 零三方依赖：HTTP 用标准库 urllib，WS 用 websockets（无则跳过 WS 项）。
  - 自动绕过沙箱透明代理：显式清空 http(s)_proxy 并设 NO_PROXY=*，
    避免 POST 被代理重放造成「假 500」。
  - 自带后端生命周期：默认复用已在 8000 监听的实例；无实例且 --spawn 时
    用当前 venv 拉起 uvicorn，跑完自动回收（仅自建的才回收）。
  - 非破坏性：默认只读，不影响演示库未读角标；--mutate 才验证写操作
    （标记已读 / 全部已读），用于完整闭环回归。

退出码
------
  0 = 全部通过；1 = 存在失败项。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

# ---- 1. 禁用代理（必须在任何网络调用前）------------------------------------
for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

try:
    import websockets  # type: ignore
    _HAVE_WS = True
except ImportError:  # pragma: no cover
    _HAVE_WS = False


# ---- 2. 配置 ----------------------------------------------------------------
PMD_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # pms/ 根
DEFAULT_BASE = "http://127.0.0.1:8000"
DEFAULT_TENANT = "DEMO2026"
DEFAULT_USER = "admin"
DEFAULT_PASS = "admin123"

RESET = "\033[0m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BOLD = "\033[1m"


def _c(code: int) -> str:
    return f"{code}"


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
    json_body: dict | None = None,
    expect: tuple[int, ...] = (200, 201),
    timeout: int = 15,
) -> tuple[int, object, str]:
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
    except urllib.error.HTTPError as exc:  # 4xx/5xx 视为正常响应（带码）
        code = exc.code
        raw = exc.read().decode("utf-8", "replace")
    except Exception as exc:  # 网络层错误
        return -1, None, f"neterr:{exc}"
    try:
        parsed = json.loads(raw) if raw else None
    except Exception:
        parsed = raw
    ok = code in expect
    return code, parsed, ("" if ok else f"http {code}")


def is_up(base: str) -> bool:
    code, _, _ = http_req(base, "GET", "/health", expect=(200,))
    return code == 200


# ---- 4. 后端生命周期 --------------------------------------------------------
def ensure_server(base: str, spawn: bool) -> subprocess.Popen | None:
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
        cwd=PMD_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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


# ---- 5. WebSocket 鉴权 ------------------------------------------------------
async def _ws_no_token(base: str, tenant: str) -> tuple[bool, str]:
    ws_url = f"ws://{base.split('://',1)[-1]}/ws/rooms?tenant_id={tenant}"
    try:
        async with websockets.connect(ws_url, open_timeout=5, close_timeout=3) as ws:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=4)
                # 服务器先 accept 再发 error 后 close(4401) —— 收到 error 即拒绝生效
                if isinstance(msg, str) and ("error" in msg or "unauthor" in msg.lower()):
                    return True, f"拒绝生效（收到鉴权错误: {msg}）"
                if isinstance(msg, str) and "subscribed" in msg:
                    return False, f"无 token 却订阅成功: {msg}"
                return False, f"无 token 收到非预期消息: {msg}"
            except asyncio.TimeoutError:
                return False, "无 token 但连接保持且无响应（未拒绝）"
    except websockets.exceptions.ConnectionClosed as exc:
        return True, f"连接被拒绝 (close code={exc.code})"
    except Exception as exc:  # 握手直接失败也算拒绝生效
        return True, f"连接被拒绝: {exc}"


async def _ws_with_token(base: str, tenant: str, token: str) -> tuple[bool, str]:
    ws_url = f"ws://{base.split('://',1)[-1]}/ws/rooms?tenant_id={tenant}&token={token}"
    try:
        async with websockets.connect(ws_url, open_timeout=5, close_timeout=3) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            if isinstance(msg, str) and "subscribed" in msg:
                return True, "收到 subscribed"
            return False, f"收到非预期消息: {msg}"
    except Exception as exc:
        return False, f"连接失败: {exc}"


# ---- 6. 主流程 --------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="PMS E2E 冒烟脚本")
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--tenant", default=DEFAULT_TENANT)
    ap.add_argument("--username", default=DEFAULT_USER)
    ap.add_argument("--password", default=DEFAULT_PASS)
    ap.add_argument("--spawn", action="store_true", help="无实例时自动拉起后端")
    ap.add_argument("--mutate", action="store_true", help="额外验证写操作（标已读/全部已读）")
    args = ap.parse_args()

    base = args.base_url
    print(f"\n{BOLD}PMS E2E 冒烟 · {base}{RESET}")
    print(f"租户={args.tenant} 用户={args.username}  mutate={args.mutate}\n")

    proc = ensure_server(base, args.spawn)
    if not is_up(base):
        print(f"{RED}后端不可达，冒烟中止。{RESET}")
        if proc:
            proc.terminate()
        return 1

    res = Results()
    tenant = args.tenant

    # 1) 健康
    code, _, _ = http_req(base, "GET", "/health", expect=(200,))
    res.add("服务存活 /health", code == 200, f"http {code}")

    # 2) 登录
    code, body, err = http_req(
        base, "POST", f"/api/v1/tenants/{tenant}/auth/login",
        json_body={"username": args.username, "password": args.password},
        expect=(200,),
    )
    token = (body or {}).get("token") if isinstance(body, dict) else None
    res.add("登录获取 token", bool(token) and code == 200,
            f"http {code}" if token else f"无 token ({err})")
    if not token:
        _finish(res, proc)
        return 0 if res.failed == 0 else 1

    # 3) 通知列表（含 link 字段）
    code, body, _ = http_req(base, "GET", f"/api/v1/tenants/{tenant}/notifications", token=token)
    notes = body if isinstance(body, list) else []
    link_ok = bool(notes) and all(("link" in n for n in notes))
    sample_link = notes[0].get("link") if notes else None
    res.add("通知列表含 link 字段", code == 200 and link_ok,
            f"共 {len(notes)} 条, 样例 link={sample_link}")

    # 4) 未读计数
    code, body, _ = http_req(base, "GET", f"/api/v1/tenants/{tenant}/notifications/unread-count", token=token)
    cnt = (body or {}).get("unread") if isinstance(body, dict) else None
    res.add("未读计数 unread-count", code == 200 and isinstance(cnt, int), f"unread={cnt}")

    # 5) 房态
    code, body, _ = http_req(base, "GET", f"/api/v1/tenants/{tenant}/rooms", token=token)
    rooms = body if isinstance(body, list) else []
    res.add("房态列表 rooms", code == 200 and isinstance(rooms, list), f"共 {len(rooms)} 间")

    # 6) 收益规则
    code, _, _ = http_req(base, "GET", f"/api/v1/tenants/{tenant}/yield/rules", token=token)
    res.add("收益规则 yield/rules", code == 200, f"http {code}")

    # 7) 收益建议
    code, body, _ = http_req(base, "GET", f"/api/v1/tenants/{tenant}/yield/pricing/recommendations", token=token)
    recs = body if isinstance(body, list) else []
    res.add("收益建议列表", code == 200, f"http {code}, 条数={len(recs)}")

    # 8) 夜审报表（夜审链路可读）
    code, body, _ = http_req(base, "GET", f"/api/v1/tenants/{tenant}/daily-reports", token=token)
    reps = body if isinstance(body, list) else []
    res.add("夜审日报 daily-reports", code == 200, f"http {code}, 条数={len(reps)}")

    # 9) WebSocket 鉴权
    if _HAVE_WS:
        ok, detail = asyncio.run(_ws_no_token(base, tenant))
        res.add("WS 无 token 必须拒绝", ok, detail)
        ok, detail = asyncio.run(_ws_with_token(base, tenant, token))
        res.add("WS 带 token 订阅成功", ok, detail)
    else:
        res.add("WS 鉴权（跳过）", True, "未安装 websockets")

    # 10) 写操作（--mutate）
    if args.mutate:
        if notes:
            nid = notes[-1]["id"]
            code, body, _ = http_req(
                base, "POST", f"/api/v1/tenants/{tenant}/notifications/{nid}/read",
                token=token, expect=(200,),
            )
            rl = (body or {}).get("link") if isinstance(body, dict) else None
            res.add("点击消息标记已读+回传 link", code == 200 and rl is not None,
                    f"http {code}, link={rl}")
        code, _, _ = http_req(base, "POST", f"/api/v1/tenants/{tenant}/notifications/read-all", token=token)
        code2, body2, _ = http_req(base, "GET", f"/api/v1/tenants/{tenant}/notifications/unread-count", token=token)
        cnt0 = (body2 or {}).get("unread") if isinstance(body2, dict) else None
        res.add("全部已读 read-all 幂等归零", code == 200 and code2 == 200 and cnt0 == 0,
                f"read-all http {code}, count={cnt0}")
        # 再次 read-all 仍 200（幂等）
        code3, _, _ = http_req(base, "POST", f"/api/v1/tenants/{tenant}/notifications/read-all", token=token)
        res.add("read-all 二次调用幂等", code3 == 200, f"http {code3}")
        if cnt0 == 0:
            print(f"{YELLOW}  ⚠ --mutate 已清空未读，演示库角标归零；如需演示未读请重新 seed。{RESET}")

    _finish(res, proc)
    return 0 if res.failed == 0 else 1


def _finish(res: Results, proc: subprocess.Popen | None) -> None:
    total = len(res.items)
    failed = res.failed
    print("\n" + "=" * 56)
    print(f"{BOLD}结果：{total - failed}/{total} 通过" + (f"，{failed} 失败{RESET}" if failed else f"{RESET}"))
    print("=" * 56 + "\n")
    if proc:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
