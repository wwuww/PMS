"""OTA 房型映射服务（M29，A6）：CRUD + 反查解析。

- upsert / list / delete；
- resolve_external_code(tenant_id, hotel_id, channel, external_code) → PMS room_type_id，
  用于 webhook 注入与价格推送的反查。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChannelRoomMapping, OtaChannelConfig, RoomType


class OtaMappingError(Exception):
    """OTA 房型映射业务异常（路由层转 4xx）。"""


class OtaMappingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self,
        tenant_id: str,
        *,
        hotel_id: int,
        channel: str,
        pms_room_type_id: int,
        external_room_type_code: str,
        enabled: bool = True,
    ) -> ChannelRoomMapping:
        cfg = (
            await self.session.execute(
                select(OtaChannelConfig).where(
                    OtaChannelConfig.tenant_id == tenant_id,
                    OtaChannelConfig.channel == channel,
                )
            )
        ).scalar_one_or_none()
        if cfg is None:
            raise OtaMappingError(f"渠道未接入：{channel}")

        rt = await self.session.get(RoomType, pms_room_type_id)
        if rt is None or rt.tenant_id != tenant_id:
            raise OtaMappingError(f"PMS 房型不存在：{pms_room_type_id}")

        stmt = select(ChannelRoomMapping).where(
            ChannelRoomMapping.tenant_id == tenant_id,
            ChannelRoomMapping.hotel_id == hotel_id,
            ChannelRoomMapping.channel == channel,
            ChannelRoomMapping.pms_room_type_id == pms_room_type_id,
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = ChannelRoomMapping(
                tenant_id=tenant_id,
                hotel_id=hotel_id,
                channel=channel,
                pms_room_type_id=pms_room_type_id,
            )
            self.session.add(row)
        row.external_room_type_code = external_room_type_code
        row.enabled = 1 if enabled else 0
        await self.session.flush()
        return row

    async def list_mappings(
        self,
        tenant_id: str,
        *,
        hotel_id: int | None = None,
        channel: str | None = None,
    ) -> list[ChannelRoomMapping]:
        stmt = select(ChannelRoomMapping).where(ChannelRoomMapping.tenant_id == tenant_id)
        if hotel_id is not None:
            stmt = stmt.where(ChannelRoomMapping.hotel_id == hotel_id)
        if channel:
            stmt = stmt.where(ChannelRoomMapping.channel == channel)
        stmt = stmt.order_by(
            ChannelRoomMapping.channel,
            ChannelRoomMapping.hotel_id,
            ChannelRoomMapping.pms_room_type_id,
        )
        return list((await self.session.execute(stmt)).scalars())

    async def delete(self, tenant_id: str, mapping_id: int) -> bool:
        row = await self.session.get(ChannelRoomMapping, mapping_id)
        if row is None or row.tenant_id != tenant_id:
            return False
        await self.session.delete(row)
        await self.session.flush()
        return True

    async def resolve_pms_room_type_id(
        self,
        tenant_id: str,
        hotel_id: int,
        channel: str,
        external_room_type_code: str,
    ) -> int | None:
        """反查 OTA 房型码 → PMS 房型 id（启用 + 匹配）。"""
        stmt = select(ChannelRoomMapping).where(
            ChannelRoomMapping.tenant_id == tenant_id,
            ChannelRoomMapping.hotel_id == hotel_id,
            ChannelRoomMapping.channel == channel,
            ChannelRoomMapping.external_room_type_code == external_room_type_code,
            ChannelRoomMapping.enabled == 1,
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return row.pms_room_type_id if row else None

    async def resolve_external_code(
        self,
        tenant_id: str,
        hotel_id: int,
        channel: str,
        pms_room_type_id: int,
    ) -> str | None:
        """正查 PMS 房型 → OTA 房型码（推送用）。"""
        stmt = select(ChannelRoomMapping).where(
            ChannelRoomMapping.tenant_id == tenant_id,
            ChannelRoomMapping.hotel_id == hotel_id,
            ChannelRoomMapping.channel == channel,
            ChannelRoomMapping.pms_room_type_id == pms_room_type_id,
            ChannelRoomMapping.enabled == 1,
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        return row.external_room_type_code if row else None
