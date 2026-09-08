"""团队 / 会议排房模型（M15，FR-GROUP）。

绿云前台对旅游团、会议等批量到店客人提供「团队排房」：先把若干物理房间
作为一个 block 分配（锁房预留），到点一键批量入住。与会员 CRM、宾客档案、
预订引擎解耦——排房只是「房间分配 + 批量入住」的编排层，入住仍复用
``BookingService.check_in`` 的全部副作用（房态/PSB/开账/客史）。
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin

# 团队 block 状态
GROUP_BLOCK_DRAFT = "draft"  # 草稿（仅登记意向）
GROUP_BLOCK_ACTIVE = "active"  # 已生效（可排房/入住）
GROUP_BLOCK_CLOSED = "closed"  # 已关闭（入住完毕或取消）

# 房间分配状态
ALLOC_ASSIGNED = "assigned"  # 已排房（锁房预留）
ALLOC_CHECKED_IN = "checked_in"  # 已入住
ALLOC_CHECKED_OUT = "checked_out"  # 已退房


class GroupBlock(IntPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "group_blocks"

    hotel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hotels.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    arrival_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    departure_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=GROUP_BLOCK_ACTIVE)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class GroupAllocation(IntPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "group_allocations"

    block_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("group_blocks.id"), nullable=False, index=True
    )
    room_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("rooms.id"), nullable=False
    )
    room_no: Mapped[str] = mapped_column(String(16), nullable=False)
    room_type_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("room_types.id"), nullable=False
    )
    guest_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    guest_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ALLOC_ASSIGNED)
