"""集团管控模型（M17，FR-R18 / FR-JG-05）：中央价格策略下发。"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class GroupPricePolicy(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """集团价格策略（M17-2，中央房价下发）。

    租户级价格边界：门店改价（price-calendar）超出 [floor, ceiling] 即拦截
    （FR-JG-05 超权限改价拦截，集团模式下门店改价受总部策略约束）。
    hotel_id/room_type_id 为空表示全店/全房型生效；同维度重复下发覆盖（幂等）。
    """

    __tablename__ = "group_price_policies"

    hotel_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=True, index=True)
    room_type_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("room_types.id"), nullable=True, index=True)
    price_floor_cents: Mapped[int] = mapped_column(default=0)  # 分，最低价边界
    price_ceiling_cents: Mapped[int | None] = mapped_column(nullable=True)  # 分，最高价边界（空=不设上限）
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE", index=True)  # ACTIVE|INACTIVE
    issued_by: Mapped[str] = mapped_column(String(64), default="hq_admin")
    note: Mapped[str] = mapped_column(String(256), default="")
