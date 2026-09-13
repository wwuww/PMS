"""M0/D1 多店隔离回归：房型与价格的「门店维度」收口。

背景
----
D1 之前 `RoomType` / `PriceCalendar` 没有 `hotel_id`，导致两个必现缺陷：
1. **房量串店**：`availability()` 按 `tenant_id + room_type_id` 聚合，不过滤门店
   → 二店开业当天算上一店的房量（超售）。
2. **价格串店**：两店共享房型定义与价格覆盖 → 改一店房价二店跟着变（收入损失）。

本用例锁定 D1 修复成果：
- `RoomType.hotel_id` / `PriceCalendar.hotel_id` 为 NOT NULL，且唯一约束升到门店级
  （同租户两店可各建同名房型，如都叫 STD）。
- `availability()` 只统计**本门店**房间。
- `PriceCalendar` 覆盖只作用于**本门店**房型。

隔离要点（重要）
----------------
本文件**不使用** `conftest.py` 的 `client` fixture（那是 HTTP 层）。
服务层测试必须自建**独立 SQLite 文件库**并 `reset_engine()`，
否则会连到真实 `pms_dev.db` 并污染其它用例（实测会导致全量套件 448 errors）。
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.snowflake import next_id
from app.models import Base, Hotel, PriceCalendar, Room, RoomType
from app.services.price_service import PriceService

TENANT = "DEMO2026"
DATE = "2026-09-16"


@pytest.fixture()
async def store(tmp_path, monkeypatch):
    """独立 SQLite 库 + 已建表引擎，yield 一个 session 工厂。"""
    from app.core.config import get_settings
    from app.db import session as db_session

    monkeypatch.setenv("PMS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/multistore.db")
    get_settings.cache_clear()
    db_session.reset_engine()

    engine = db_session.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()
        get_settings.cache_clear()
        db_session.reset_engine()


async def _seed_two_stores(factory, rooms_a: int, rooms_b: int):
    """建一店/二店各一个同名 STD 房型 + 房间数。返回 (rt1, rt2, h1, h2)。"""
    async with factory() as s:
        h1 = Hotel(id=next_id(), tenant_id=TENANT, code="STORE_A", name="一店")
        h2 = Hotel(id=next_id(), tenant_id=TENANT, code="STORE_B", name="二店")
        s.add_all([h1, h2])
        await s.flush()

        rt1 = RoomType(
            id=next_id(), tenant_id=TENANT, hotel_id=h1.id, code="STD",
            name="标准大床房", base_price=30000, bed_number=1,
        )
        rt2 = RoomType(
            id=next_id(), tenant_id=TENANT, hotel_id=h2.id, code="STD",
            name="标准大床房", base_price=28000, bed_number=1,
        )
        s.add_all([rt1, rt2])
        await s.flush()

        for i in range(1, rooms_a + 1):
            s.add(Room(id=next_id(), tenant_id=TENANT, hotel_id=h1.id,
                       room_type_id=rt1.id, room_no=f"A{i:03d}", floor="1"))
        for i in range(1, rooms_b + 1):
            s.add(Room(id=next_id(), tenant_id=TENANT, hotel_id=h2.id,
                       room_type_id=rt2.id, room_no=f"B{i:03d}", floor="1"))
        await s.commit()
        return rt1.id, rt2.id, h1.id, h2.id


@pytest.mark.asyncio
async def test_same_room_type_code_allowed_across_hotels(store):
    """同租户下两店可各建同名房型（约束已升门店级）。"""
    _, _, h1, h2 = await _seed_two_stores(store, 1, 1)
    async with store() as s:
        count = (
            await s.execute(
                select(RoomType).where(
                    RoomType.tenant_id == TENANT, RoomType.code == "STD"
                )
            )
        ).scalars().all()
        assert len(count) == 2, "两店应各有一个 STD 房型"
        assert {c.hotel_id for c in count} == {h1, h2}


@pytest.mark.asyncio
async def test_availability_scoped_to_hotel(store):
    """availability() 只统计本门店房间，两店房量互不串扰。"""
    rt1, rt2, _, _ = await _seed_two_stores(store, 11, 6)
    async with store() as s:
        svc = PriceService(s)
        a1 = await svc.availability(TENANT, rt1, DATE)
        a2 = await svc.availability(TENANT, rt2, DATE)
        assert a1["total"] == 11, f"一店房量应 11，实际 {a1['total']}"
        assert a2["total"] == 6, f"二店房量应 6，实际 {a2['total']}（疑似串店）"


@pytest.mark.asyncio
async def test_price_calendar_isolated_by_hotel(store):
    """二店价格覆盖不影响一店（同名房型独立定价）。"""
    rt1, rt2, _, h2 = await _seed_two_stores(store, 3, 3)
    async with store() as s:
        s.add(
            PriceCalendar(
                id=next_id(), tenant_id=TENANT, hotel_id=h2,
                room_type_id=rt2, date=DATE, price=49000,
            )
        )
        await s.commit()

        svc = PriceService(s)
        p1 = await svc.resolve(rt1, DATE)
        p2 = await svc.resolve(rt2, DATE)
        assert p1 == 30000, f"一店应走基准价 30000，实际 {p1}"
        assert p2 == 49000, f"二店应命中覆盖价 49000，实际 {p2}"
        assert p1 != p2, "两店价格相同，独立定价失败"


@pytest.mark.asyncio
async def test_room_type_hotel_id_required(store):
    """`hotel_id` 为 NOT NULL：缺门店的房型不得落库。"""
    from sqlalchemy.exc import IntegrityError

    async with store() as s:
        s.add(
            RoomType(
                id=next_id(), tenant_id=TENANT, code="NOHOTEL",
                name="无门店房型", base_price=10000, bed_number=1,
            )
        )
        with pytest.raises(IntegrityError):
            await s.flush()
        await s.rollback()
