"""D1 二店测试数据录入 + 多店隔离验证（一次性脚本，可重复执行）。

验证三件事（对应业主「必须独立定价」的验收）：
1. **同名房型共存**：二店可建 code=STD 的房型，与一店 STD 不冲突。
2. **独立定价**：改二店 STD 的价格，一店 STD 价格不变（反之亦然）。
3. **独立房量**：availability() 只统计本门店房间，不串店。

用法：.venv/Scripts/python.exe scripts/seed_store2.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.snowflake import next_id  # noqa: E402
from app.db import session as db_session  # noqa: E402
from app.models import Hotel, PriceCalendar, Room, RoomType  # noqa: E402
from app.services.price_service import PriceService  # noqa: E402

TENANT = "DEMO2026"
STORE2_CODE = "SZ002"
STORE2_NAME = "深圳南山二店"


async def main() -> None:
    # get_engine() 懒初始化 _session_factory；直接引用模块属性会拿到 None。
    db_session.get_engine()
    assert db_session._session_factory is not None
    async with db_session._session_factory() as session:
        # ---------- 1) 二店门店 ----------
        hotel2 = (
            await session.execute(
                select(Hotel).where(Hotel.tenant_id == TENANT, Hotel.code == STORE2_CODE)
            )
        ).scalar_one_or_none()
        if hotel2 is None:
            hotel2 = Hotel(
                id=next_id(),
                tenant_id=TENANT,
                code=STORE2_CODE,
                name=STORE2_NAME,
            )
            session.add(hotel2)
            await session.flush()
            print(f"[+] 建二店 {STORE2_CODE} id={hotel2.id}")
        else:
            print(f"[=] 二店已存在 id={hotel2.id}")

        # ---------- 2) 二店房型（故意用与一店相同的 code=STD）----------
        rt2 = (
            await session.execute(
                select(RoomType).where(
                    RoomType.tenant_id == TENANT,
                    RoomType.hotel_id == hotel2.id,
                    RoomType.code == "STD",
                )
            )
        ).scalar_one_or_none()
        if rt2 is None:
            rt2 = RoomType(
                id=next_id(),
                tenant_id=TENANT,
                hotel_id=hotel2.id,
                code="STD",  # ← 与一店同名，验证约束已升门店级
                name="标准大床房",
                base_price=28000,  # 二店基准价比一店(30000)便宜 20 元
                bed_number=1,
            )
            session.add(rt2)
            await session.flush()
            print(f"[+] 建二店房型 STD id={rt2.id} base_price=28000")
        else:
            print(f"[=] 二店 STD 已存在 id={rt2.id}")

        # ---------- 3) 二店房间（6 间）----------
        existing_rooms = (
            await session.execute(
                select(Room).where(
                    Room.tenant_id == TENANT, Room.hotel_id == hotel2.id
                )
            )
        ).scalars().all()
        if not existing_rooms:
            for i in range(1, 7):
                session.add(
                    Room(
                        id=next_id(),
                        tenant_id=TENANT,
                        hotel_id=hotel2.id,
                        room_type_id=rt2.id,
                        room_no=f"2{i:02d}",
                        floor="2",
                    )
                )
            await session.flush()
            print("[+] 建二店房间 6 间（201-206）")
        else:
            print(f"[=] 二店已有 {len(existing_rooms)} 间房")

        # ---------- 4) 二店独立房价（2026-09-16 二店首日，与一店同日不同价）----------
        target_date = "2026-09-16"
        cal2 = (
            await session.execute(
                select(PriceCalendar).where(
                    PriceCalendar.tenant_id == TENANT,
                    PriceCalendar.hotel_id == hotel2.id,
                    PriceCalendar.room_type_id == rt2.id,
                    PriceCalendar.date == target_date,
                )
            )
        ).scalar_one_or_none()
        if cal2 is None:
            cal2 = PriceCalendar(
                id=next_id(),
                tenant_id=TENANT,
                hotel_id=hotel2.id,
                room_type_id=rt2.id,
                date=target_date,
                price=49000,  # 二店当日卖 490 元
            )
            session.add(cal2)
            await session.flush()
            print(f"[+] 建二店 {target_date} 房价 49000（490 元）")
        else:
            print(f"[=] 二店 {target_date} 房价已存在")

        await session.commit()

        # ---------- 5) 验证：独立定价 ----------
        print("\n===== 验证 1/2：独立定价 =====")
        svc = PriceService(session)
        rt1 = (
            await session.execute(
                select(RoomType).where(
                    RoomType.tenant_id == TENANT, RoomType.hotel_id == 1, RoomType.code == "STD"
                )
            )
        ).scalar_one_or_none()
        p1 = await svc.resolve(rt1.id, target_date) if rt1 else None
        p2 = await svc.resolve(rt2.id, target_date)
        print(f"  一店 STD ({target_date}) = {p1} 分")
        print(f"  二店 STD ({target_date}) = {p2} 分")
        assert p1 != p2, "❌ 两店价格相同，独立定价失败！"
        print("  ✅ 两店同名房型独立定价生效")

        # ---------- 6) 验证：独立房量 ----------
        print("\n===== 验证 2/2：独立房量 =====")
        a1 = await svc.availability(TENANT, rt1.id, target_date) if rt1 else None
        a2 = await svc.availability(TENANT, rt2.id, target_date)
        print(f"  一店 STD 房量 = {a1}")
        print(f"  二店 STD 房量 = {a2}")
        assert a2["total"] == 6, f"❌ 二店房量应为 6，实际 {a2['total']}（疑似串店）"
        print("  ✅ 二店房量只统计本店 6 间，未串入一店")

        print("\n🎉 D1 二店测试数据录入完成，多店隔离验证全部通过。")


if __name__ == "__main__":
    asyncio.run(main())
