"""M30 性能基线：高频列表接口在规模化数据下的响应耗时。

设计意图
--------
作为 M30 性能优化的**相对基线**：SQLite/单进程的绝对值不代表生产（MySQL +
ShardingSphere 分库分表），但**同一环境下优化前后对比**可直接证明收益。

不进默认 CI 跑批（造规模数据耗时），需显式执行：

    pytest -m perf tests/test_perf_baseline.py -s -v

产物
----
结果同时打印到 stdout 并落盘 ``.perf_baseline.json``（已在 .gitignore），
供优化后 diff 对比。
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.session import get_engine, init_db

# 规模：单租户 3 门店 × 10 房型 → 1000 间房；2000 条预订
SCALE = {
    "hotels": 3,
    "room_types": 10,
    "rooms": 1000,
    "bookings": 2000,
}

TENANT_CODE = "PERF1"
BASELINE_FILE = Path(__file__).resolve().parents[1] / ".perf_baseline.json"

# 每个接口采样次数（前 3 次预热不计入统计）
SAMPLES = 20
WARMUP = 3


def _stats(samples: list[float]) -> dict[str, float]:
    """把毫秒采样转为 p50/p95/max/mean（保留 2 位小数）。"""
    return {
        "p50": round(statistics.median(samples), 2),
        "p95": round(sorted(samples)[max(0, int(len(samples) * 0.95) - 1)], 2),
        "max": round(max(samples), 2),
        "mean": round(statistics.fmean(samples), 2),
    }


@pytest.fixture()
async def seeded(monkeypatch) -> dict[str, Any]:  # noqa: ANN001
    """造规模数据（幂等：已存在则复用，避免每次重建拖慢迭代）。

    使用独立 ``_perf.db``（已 gitignore）承载压测数据，避免污染开发库 pms_dev.db。

    M30 第二批：旧 _perf.db 与新迁移漂移时（模型加列），自动删旧库重建保证 schema 最新，
    避免「旧库 + create_all 只建新表」导致 OperationalError。
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.core.config import get_settings
    from app.db import session as db_session
    from app.models import Booking, Hotel, Room, RoomType, Tenant

    perf_db = Path(__file__).resolve().parents[1] / "_perf.db"
    # M30 第二批：检测到 _perf.db 比最近的迁移文件旧时，删旧库让 init_db 重建（避免 schema 漂移）
    latest_migration = max(
        (Path(__file__).resolve().parents[1] / "migrations" / "versions").glob("*.py"),
        default=None,
        key=lambda p: p.stat().st_mtime,
    )
    if perf_db.exists() and latest_migration is not None:
        if perf_db.stat().st_mtime < latest_migration.stat().st_mtime:
            perf_db.unlink()
            print(f"[perf fixture] 检测到 _perf.db 比最新迁移旧，已删除重建（migration={latest_migration.name}）")
    monkeypatch.setenv("PMS_DATABASE_URL", f"sqlite+aiosqlite:///{perf_db.as_posix()}")
    get_settings.cache_clear()
    db_session.reset_engine()

    await init_db()
    sm = async_sessionmaker(get_engine(), expire_on_commit=False)

    async with sm() as s:
        t = (
            await s.execute(select(Tenant).where(Tenant.code == TENANT_CODE))
        ).scalar_one_or_none()
        if t is None:
            t = Tenant(code=TENANT_CODE, name="性能测试租户")
            s.add(t)
            await s.flush()

        hotels = (
            (await s.execute(select(Hotel).where(Hotel.tenant_id == TENANT_CODE)))
            .scalars()
            .all()
        )
        if not hotels:
            hotels = [
                Hotel(tenant_id=TENANT_CODE, name=f"压测店{i + 1}", code=f"PH{i + 1}")
                for i in range(SCALE["hotels"])
            ]
            s.add_all(hotels)
            await s.flush()

        room_types = (
            (await s.execute(select(RoomType).where(RoomType.tenant_id == TENANT_CODE)))
            .scalars()
            .all()
        )
        if not room_types:
            room_types = [
                RoomType(
                    tenant_id=TENANT_CODE,
                    hotel_id=hotels[i % len(hotels)].id,  # D1（M0 多店）：按店轮流归属
                    code=f"PRT{i + 1}",
                    name=f"压测房型{i + 1}",
                    base_price=30000 + i * 1000,
                )
                for i in range(SCALE["room_types"])
            ]
            s.add_all(room_types)
            await s.flush()

        existing_rooms = (
            await s.execute(
                select(Room.id).where(Room.tenant_id == TENANT_CODE).limit(1)
            )
        ).scalar_one_or_none()
        if existing_rooms is None:
            rooms: list[Room] = []
            for i in range(SCALE["rooms"]):
                rooms.append(
                    Room(
                        tenant_id=TENANT_CODE,
                        hotel_id=hotels[i % len(hotels)].id,
                        room_type_id=room_types[i % len(room_types)].id,
                        room_no=f"{1000 + i}",
                        floor=str(1 + (i // 20)),
                        state=["VACANT_CLEAN", "VACANT_DIRTY", "OCCUPIED", "MAINTENANCE"][
                            i % 4
                        ],
                        dnd=0,
                    )
                )
            s.add_all(rooms)
            await s.flush()

        existing_bk = (
            await s.execute(
                select(Booking.id).where(Booking.tenant_id == TENANT_CODE).limit(1)
            )
        ).scalar_one_or_none()
        if existing_bk is None:
            bookings: list[Booking] = []
            for i in range(SCALE["bookings"]):
                bookings.append(
                    Booking(
                        tenant_id=TENANT_CODE,
                        hotel_id=hotels[i % len(hotels)].id,
                        room_type_id=room_types[i % len(room_types)].id,
                        guest_name=f"压测客人{i}",
                        guest_phone=f"138{i:08d}",
                        check_in_date="2026-09-10",
                        check_out_date="2026-09-12",
                        room_no=str(1000 + (i % SCALE["rooms"])),
                        status=["CREATED", "CHECKED_IN", "CHECKED_OUT"][i % 3],
                        total_price=60000,
                        extra_bed_count=0,
                    )
                )
            s.add_all(bookings)
            await s.flush()

        await s.commit()

    yield {"tenant": TENANT_CODE, "scale": SCALE}

    get_settings.cache_clear()
    db_session.reset_engine()


async def _measure(client: AsyncClient, url: str) -> dict[str, float]:
    """对单个接口采样：先预热，再统计 N 次耗时（毫秒）。"""
    for _ in range(WARMUP):
        await client.get(url)

    samples: list[float] = []
    for _ in range(SAMPLES):
        t0 = time.perf_counter()
        resp = await client.get(url)
        samples.append((time.perf_counter() - t0) * 1000)
        assert resp.status_code == 200, f"{url} -> {resp.status_code}: {resp.text[:200]}"
    return _stats(samples)


@pytest.mark.perf
async def test_perf_baseline(seeded: dict[str, Any]) -> None:
    """高频列表接口基线：rooms（房态盘核心）/ bookings / housekeeping-tasks。"""
    from app.main import app

    tid = seeded["tenant"]
    base = f"/api/v1/tenants/{tid}"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://perf") as client:
        # /health 无鉴权无 DB，作为「ASGI 传输地板」：
        # 业务接口耗时 − 地板 = 真实业务开销（避免把 httpx/ASGI 固定成本误判为业务瓶颈）
        targets = {
            "GET /health (传输地板)": "/health",
            "GET /rooms (房态盘核心)": f"{base}/rooms",
            "GET /bookings": f"{base}/bookings",
            "GET /bookings?limit=50 (分页后)": f"{base}/bookings?limit=50",
            "GET /housekeeping-tasks": f"{base}/housekeeping-tasks",
        }
        results: dict[str, Any] = {"scale": seeded["scale"], "endpoints": {}}
        for label, url in targets.items():
            results["endpoints"][label] = await _measure(client, url)

    # 落盘供优化后 diff
    BASELINE_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    floor_p50 = results["endpoints"].get("GET /health (传输地板)", {}).get("p50", 0.0)

    print("\n" + "=" * 74)
    print(f"M30 性能基线  规模={seeded['scale']}  采样={SAMPLES}次")
    print("=" * 74)
    print(f"{'接口':<34}{'p50':>9}{'p95':>9}{'净开销(p50-地板)':>20}")
    print("-" * 74)
    for label, st in results["endpoints"].items():
        net = st["p50"] - floor_p50
        print(f"{label:<34}{st['p50']:>9.2f}{st['p95']:>9.2f}{net:>16.2f} ms")
    print("=" * 74)
    print(f"传输地板 /health p50 = {floor_p50:.2f} ms（ASGI+httpx 固定成本，非业务开销）")
    print(f"基线已落盘：{BASELINE_FILE}")

    # 回归护栏：单接口 p95 不应劣化到 3 秒以上（SQLite+ASGI 单进程下的宽松上限）
    for label, st in results["endpoints"].items():
        assert st["p95"] < 3000, f"{label} p95={st['p95']}ms 超出护栏 3000ms"
