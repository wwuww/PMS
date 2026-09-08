"""A6/M30 轻量压测：对热点读端点并发打点，输出 p50/p95/p99。

用法（需先起后端，或 --spawn 自起）：
  python scripts/load_test.py --spawn --concurrency 20 --requests 200
默认打点端点：
  GET /api/v1/tenants/{t}/rooms           （已有 Sprint15 热点缓存）
  GET /api/v1/tenants/{t}/analytics/dashboard （M30 新增热点缓存）

只做只读打点，不污染业务数据。退出码 0=成功（失败请求为 0）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import statistics
import subprocess
import sys
import time
import urllib.request

import httpx

BASE = "http://127.0.0.1:8000"


async def login_token(tenant: str) -> str:
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as cli:
        r = await cli.post(f"/api/v1/tenants/{tenant}/auth/login", json={"username": "admin", "password": "admin123"})
        r.raise_for_status()
        return r.json()["token"]


async def hit(cli: httpx.AsyncClient, path: str, headers: dict, latencies: list, errors: list) -> None:
    t0 = time.perf_counter()
    try:
        r = await cli.get(path, headers=headers)
        if r.status_code != 200:
            errors.append(f"{r.status_code} {path}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{type(exc).__name__} {path}")
    finally:
        latencies.append((time.perf_counter() - t0) * 1000)


async def bench(path: str, headers: dict, concurrency: int, total: int) -> dict:
    latencies: list[float] = []
    errors: list[str] = []
    per_task = total // concurrency
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as cli:
        t0 = time.perf_counter()
        await asyncio.gather(*[
            asyncio.gather(*[hit(cli, path, headers, latencies, errors) for _ in range(per_task)])
            for _ in range(concurrency)
        ])
        wall = time.perf_counter() - t0
    latencies.sort()

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        idx = min(len(latencies) - 1, int(len(latencies) * p))
        return latencies[idx]

    return {
        "path": path,
        "count": len(latencies),
        "errors": len(errors),
        "wall_s": round(wall, 2),
        "rps": round(len(latencies) / wall, 1) if wall else 0,
        "p50_ms": round(pct(0.50), 1),
        "p95_ms": round(pct(0.95), 1),
        "p99_ms": round(pct(0.99), 1),
        "mean_ms": round(statistics.mean(latencies), 1) if latencies else 0,
        "error_detail": errors[:3],
    }


def spawn_backend() -> subprocess.Popen:
    env = dict(os.environ)
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        env.pop(k, None)
    env["NO_PROXY"] = "*"
    proc = subprocess.Popen(
        [".venv/Scripts/python.exe", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env,
    )
    for _ in range(40):
        try:
            with urllib.request.urlopen(BASE + "/health", timeout=2) as r:
                if r.status == 200:
                    return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError("backend failed to start")


async def main_async(args: argparse.Namespace) -> int:
    # 建独立租户做只读压测（预订流程不做写入，避免污染）
    stamp = str(int(time.time()))
    async with httpx.AsyncClient(base_url=BASE, timeout=10) as cli:
        r = await cli.post("/api/v1/tenants", json={"code": f"load-{stamp}", "name": "压测"})
        tenant = r.json()["code"]
    token = await login_token(tenant)
    headers = {"Authorization": f"Bearer {token}"}

    results = []
    for path in (f"/api/v1/tenants/{tenant}/rooms", f"/api/v1/tenants/{tenant}/analytics/dashboard?hotel_id=0"):
        results.append(await bench(path, headers, args.concurrency, args.requests))

    print(f"{'端点':<52}{'请求数':>6}{'错误':>6}{'RPS':>8}{'p50':>8}{'p95':>8}{'p99':>8}")
    for r in results:
        print(f"{r['path'][:50]:<52}{r['count']:>6}{r['errors']:>6}{r['rps']:>8}{r['p50_ms']:>8}{r['p95_ms']:>8}{r['p99_ms']:>8}")
        if r["errors"]:
            print("  错误样例:", r["error_detail"])
    total_errors = sum(r["errors"] for r in results)
    print(f"\nload test: {sum(r['count'] for r in results)} requests, {total_errors} errors")
    return 0 if total_errors == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--requests", type=int, default=200)
    ap.add_argument("--spawn", action="store_true")
    args = ap.parse_args()
    proc = spawn_backend() if args.spawn else None
    try:
        return asyncio.run(main_async(args))
    finally:
        if proc:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    sys.exit(main())
