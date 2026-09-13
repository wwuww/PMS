"""价格库存中心（FR-JG 全量，DEC-01 唯一房价房量源）。

职责：
1. resolve()：基准价 → 价格日历覆盖 → RateCode 五维折扣解析，输出最终价（各触点统一入口）。
2. availability()：按房型 × 日期聚合房量占用（总房数 - 在订数），库存由聚合推导，无独立计数器。
3. batch_availability() / batch_resolve()：M30 B4 批量化版本，
   一次房型 × N 个日期 → 固定查询数（替代 N 次串行调用，详见各方法 docstring）。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingStatus, PriceCalendar, RateCode, Room, RoomType


class PriceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _base_price(self, room_type: RoomType, date: str) -> int:
        """基准价：优先价格日历当日覆盖，否则房型基准价。"""
        cal = await self.session.execute(
            select(PriceCalendar).where(
                PriceCalendar.tenant_id == room_type.tenant_id,
                PriceCalendar.room_type_id == room_type.id,
                PriceCalendar.date == date,
            )
        )
        row = cal.scalar_one_or_none()
        return row.price if row else room_type.base_price

    async def resolve(
        self,
        room_type_id: int,
        date: str,
        channel: str = "direct",
        member_level: str = "none",
        agreement_type: str = "none",
        rate_code_code: str | None = None,
    ) -> int:
        """解析某房型在某日、某渠道/会员/协议维度下的最终价（分）。"""
        room_type = await self.session.get(RoomType, room_type_id)
        if not room_type:
            raise ValueError("room_type 不存在")
        base = await self._base_price(room_type, date)

        if rate_code_code:
            rc = await self.session.execute(
                select(RateCode).where(
                    RateCode.tenant_id == room_type.tenant_id, RateCode.code == rate_code_code
                )
            )
            rate_code = rc.scalar_one_or_none()
            if rate_code:
                return rate_code.resolve_price(base)
            return base

        # 无指定 RateCode：选最匹配的五维价格码
        matches = await self.session.execute(
            select(RateCode).where(
                RateCode.tenant_id == room_type.tenant_id,
                (RateCode.room_type_id.is_(None)) | (RateCode.room_type_id == room_type_id),
                RateCode.channel == channel,
                RateCode.member_level == member_level,
                RateCode.agreement_type == agreement_type,
            )
        )
        codes = list(matches.scalars())
        if not codes:
            return base
        # 优先房型专属（更具体），其次通用
        specific = [c for c in codes if c.room_type_id is not None]
        best = specific[0] if specific else codes[0]
        return best.resolve_price(base)

    async def availability(
        self, tenant_id: str, room_type_id: int, date: str
    ) -> dict[str, int]:
        """房型 × 日期房量占用聚合。

        D1（M0 多店）：房量必须按**门店**隔离——房型归属门店（``RoomType.hotel_id``），
        房量聚合加 ``Room.hotel_id == <该房型所属门店>``。否则二店的房量会算上一店的房间
        （跨店超售）。门店从房型推导（不新增参数），保证所有调用点自动正确。
        """
        hotel_id = await self._room_type_hotel_id(room_type_id)
        total = await self.session.execute(
            select(func.count()).select_from(Room).where(
                Room.tenant_id == tenant_id,
                Room.room_type_id == room_type_id,
                Room.hotel_id == hotel_id,  # D1：门店隔离
            )
        )
        total_n = int(total.scalar() or 0)

        booked = await self.session.execute(
            select(func.count()).select_from(Booking).where(
                Booking.tenant_id == tenant_id,
                Booking.room_type_id == room_type_id,
                Booking.hotel_id == hotel_id,  # D1：门店隔离
                Booking.status.in_([BookingStatus.CREATED.value, BookingStatus.CHECKED_IN.value]),
                Booking.check_in_date <= date,
                Booking.check_out_date > date,
                # M32.17：钟点房不占用当天过夜房的可售房量
                Booking.stay_type != "hourly",
            )
        )
        booked_n = int(booked.scalar() or 0)
        return {"total": total_n, "booked": booked_n, "available": max(total_n - booked_n, 0)}

    async def _room_type_hotel_id(self, room_type_id: int) -> int:
        """取房型所属门店 id（D1 门店隔离的依据）。

        房型不存在时抛 ``ValueError``——调用方本就在查该房型的房量，
        房型不存在属非法输入，静默返回 0 会掩盖问题。
        """
        rt = await self.session.get(RoomType, room_type_id)
        if rt is None:
            raise ValueError("room_type 不存在")
        return rt.hotel_id

    # ---- M30 B4 批量化版本（与逐晚版本语义等价） ----

    async def batch_availability(
        self,
        tenant_id: str,
        room_type_id: int,
        dates: list[str],
    ) -> dict[str, dict[str, int]]:
        """批量房型 × 日期房量占用聚合。返回 {date: {"total","booked","available"}}。

        语义等价于逐晚调用 ``availability``：每个 date 的 total/booked/available
        与逐晚版本逐字段一致（``ci <= d < co`` 占用判断保留；``status IN (CREATED, CHECKED_IN)``
        与 ``stay_type != "hourly"`` 保留）。

        D1（M0 多店）：与逐晚版一致地按房型所属门店隔离（``Room/Booking.hotel_id``）。

        查询次数：原逐晚版 ``len(dates) * 2``（每晚 1 COUNT(Room) + 1 COUNT(Booking)）；
        批量版固定 **2 次**（1 COUNT(Room) + 1 SELECT(Booking) → Python 端按日聚合）。
        """
        if not dates:
            return {}
        hotel_id = await self._room_type_hotel_id(room_type_id)
        # 1. 房型总房数（门店隔离）
        total = await self.session.execute(
            select(func.count()).select_from(Room).where(
                Room.tenant_id == tenant_id,
                Room.room_type_id == room_type_id,
                Room.hotel_id == hotel_id,  # D1：门店隔离
            )
        )
        total_n = int(total.scalar() or 0)

        # 2. 一次性取所有可能与 [min_d, max_d] 区间重叠的 booking 的 (ci, co)。
        #    重叠条件（与原版 ci<=d<co 等价于对所有 d∈dates）：
        #      booking.check_out_date > min_d   → 离店晚于我们最早的查询日
        #      booking.check_in_date  <= max_d  → 入住不晚于我们最晚的查询日
        min_d, max_d = min(dates), max(dates)
        rows = await self.session.execute(
            select(Booking.check_in_date, Booking.check_out_date).where(
                Booking.tenant_id == tenant_id,
                Booking.room_type_id == room_type_id,
                Booking.hotel_id == hotel_id,  # D1：门店隔离
                Booking.status.in_([
                    BookingStatus.CREATED.value, BookingStatus.CHECKED_IN.value
                ]),
                Booking.stay_type != "hourly",  # M32.17：钟点房不占过夜
                Booking.check_out_date > min_d,
                Booking.check_in_date <= max_d,
            )
        )
        bookings = list(rows.all())  # list[(check_in_date, check_out_date)]

        # 3. 按每个 date 聚合 booked 数（语义与逐晚 COUNT 完全一致）
        out: dict[str, dict[str, int]] = {}
        for d in dates:
            booked = sum(1 for ci, co in bookings if ci <= d < co)
            out[d] = {
                "total": total_n,
                "booked": booked,
                "available": max(total_n - booked, 0),
            }
        return out

    async def batch_resolve(
        self,
        room_type_id: int,
        dates: list[str],
        channel: str = "direct",
        member_level: str = "none",
        agreement_type: str = "none",
        rate_code_code: str | None = None,
    ) -> dict[str, int]:
        """批量解析房型在多个日期、某渠道/会员/协议维度下的最终价（分）。

        语义等价于逐晚调用 ``resolve``：所有日期共用同一 RateCode 折扣（同房型下，
        逐晚版每次 resolve 找的也是同房型同渠道的 RateCode）；基准价逻辑相同
        （PriceCalendar 当日覆盖，否则 ``rt.base_price``）；RateCode 选取优先级
        相同（房型专属 > 通用）；``rate_code_code`` 指定时按 code 查（与原版一致）。

        查询次数：原逐晚版 ``len(dates) * (2~3)``；批量版固定 **3 次**
        （1 GET RoomType + 1 SELECT(PriceCalendar) IN dates + 1 SELECT(RateCode)）。
        """
        if not dates:
            return {}
        # 1. 一次性取 RoomType
        rt = await self.session.get(RoomType, room_type_id)
        if rt is None or rt.tenant_id is None:
            raise ValueError("room_type 不存在")
        tenant_id = rt.tenant_id

        # 2. 一次性取 PriceCalendar（覆盖 dates 的）
        cal_map: dict[tuple[int, str], int] = {
            (c.room_type_id, c.date): c.price
            for c in (
                await self.session.execute(
                    select(PriceCalendar).where(
                        PriceCalendar.tenant_id == tenant_id,
                        PriceCalendar.room_type_id == room_type_id,
                        PriceCalendar.date.in_(dates),
                    )
                )
            ).scalars()
        }

        # 3. 一次性取 RateCode（按 code 或五维匹配；房型专属+通用同查，由 Python 端选最优）
        if rate_code_code:
            rc = (
                await self.session.execute(
                    select(RateCode).where(
                        RateCode.tenant_id == tenant_id, RateCode.code == rate_code_code
                    )
                )
            ).scalar_one_or_none()
            rate_codes: list[RateCode] = [rc] if rc else []
        else:
            rate_codes = list(
                (
                    await self.session.execute(
                        select(RateCode).where(
                            RateCode.tenant_id == tenant_id,
                            (RateCode.room_type_id.is_(None))
                            | (RateCode.room_type_id == room_type_id),
                            RateCode.channel == channel,
                            RateCode.member_level == member_level,
                            RateCode.agreement_type == agreement_type,
                        )
                    )
                ).scalars()
            )

        # 优先房型专属（更具体），其次通用 —— 与逐晚 resolve 完全一致
        specific = [c for c in rate_codes if c.room_type_id is not None]
        generic = [c for c in rate_codes if c.room_type_id is None]
        best = specific[0] if specific else (generic[0] if generic else None)

        # 应用到所有日期
        return {
            d: (
                best.resolve_price(cal_map.get((room_type_id, d), rt.base_price))
                if best
                else cal_map.get((room_type_id, d), rt.base_price)
            )
            for d in dates
        }
