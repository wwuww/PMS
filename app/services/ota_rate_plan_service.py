"""OTA 渠道价服务（M29，A6）：upsert / list / 解析。

- effective_date 可空（null = 永久默认价）；
- resolve_price(tenant_id, hotel_id, channel, pms_room_type_id, date)
  → 优先按日期匹配，否则取 effective_date IS NULL 的永久默认价；
  否则回退 PMS RoomType.base_price。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChannelRatePlan, OtaChannelConfig, RoomType


class OtaRatePlanError(Exception):
    """OTA 渠道价业务异常（路由层转 4xx）。"""


class OtaRatePlanService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self,
        tenant_id: str,
        *,
        hotel_id: int,
        channel: str,
        pms_room_type_id: int,
        effective_date: date | None,
        price_cents: int,
        enabled: bool = True,
    ) -> ChannelRatePlan:
        if price_cents <= 0:
            raise OtaRatePlanError("price_cents 必须 > 0")

        cfg = (
            await self.session.execute(
                select(OtaChannelConfig).where(
                    OtaChannelConfig.tenant_id == tenant_id,
                    OtaChannelConfig.channel == channel,
                )
            )
        ).scalar_one_or_none()
        if cfg is None:
            raise OtaRatePlanError(f"渠道未接入：{channel}")

        rt = await self.session.get(RoomType, pms_room_type_id)
        if rt is None or rt.tenant_id != tenant_id:
            raise OtaRatePlanError(f"PMS 房型不存在：{pms_room_type_id}")

        stmt = select(ChannelRatePlan).where(
            ChannelRatePlan.tenant_id == tenant_id,
            ChannelRatePlan.hotel_id == hotel_id,
            ChannelRatePlan.channel == channel,
            ChannelRatePlan.pms_room_type_id == pms_room_type_id,
            ChannelRatePlan.effective_date == effective_date,
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = ChannelRatePlan(
                tenant_id=tenant_id,
                hotel_id=hotel_id,
                channel=channel,
                pms_room_type_id=pms_room_type_id,
                effective_date=effective_date,
            )
            self.session.add(row)
        row.price_cents = price_cents
        row.enabled = 1 if enabled else 0
        await self.session.flush()
        return row

    async def list_plans(
        self,
        tenant_id: str,
        *,
        hotel_id: int | None = None,
        channel: str | None = None,
        pms_room_type_id: int | None = None,
    ) -> list[ChannelRatePlan]:
        stmt = select(ChannelRatePlan).where(ChannelRatePlan.tenant_id == tenant_id)
        if hotel_id is not None:
            stmt = stmt.where(ChannelRatePlan.hotel_id == hotel_id)
        if channel:
            stmt = stmt.where(ChannelRatePlan.channel == channel)
        if pms_room_type_id is not None:
            stmt = stmt.where(ChannelRatePlan.pms_room_type_id == pms_room_type_id)
        stmt = stmt.order_by(
            ChannelRatePlan.channel,
            ChannelRatePlan.pms_room_type_id,
            ChannelRatePlan.effective_date.is_(None),  # 永久默认价置后
            ChannelRatePlan.effective_date,
        )
        return list((await self.session.execute(stmt)).scalars())

    async def delete(self, tenant_id: str, plan_id: int) -> bool:
        row = await self.session.get(ChannelRatePlan, plan_id)
        if row is None or row.tenant_id != tenant_id:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def resolve_price(
        self,
        tenant_id: str,
        hotel_id: int,
        channel: str,
        pms_room_type_id: int,
        query_date: date | None = None,
    ) -> int | None:
        """解析渠道价：日期优先 → 永久默认 → None（回退 PMS base_price）。"""
        stmt = (
            select(ChannelRatePlan)
            .where(
                ChannelRatePlan.tenant_id == tenant_id,
                ChannelRatePlan.hotel_id == hotel_id,
                ChannelRatePlan.channel == channel,
                ChannelRatePlan.pms_room_type_id == pms_room_type_id,
                ChannelRatePlan.enabled == 1,
            )
        )
        rows = list((await self.session.execute(stmt)).scalars())

        # 1. 日期匹配
        if query_date is not None:
            for row in rows:
                if row.effective_date == query_date:
                    return row.price_cents
        # 2. 永久默认
        for row in rows:
            if row.effective_date is None:
                return row.price_cents
        return None
