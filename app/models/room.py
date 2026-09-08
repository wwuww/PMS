"""房型、房间与房态事件（M1）。"""

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.room_state import RoomState
from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class RoomType(IntPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "room_types"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    base_price: Mapped[int] = mapped_column(Integer, default=0)  # 分
    hourly_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)  # M24：时租价（分/小时），空则按日价 1/4 折算


class Room(IntPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "rooms"
    # M30 性能：复合索引以 tenant_id 为前导（ShardingSphere 分片键 = tenant_id，
    # 无前导列会跨片广播）。均按 audit docs/M30-performance-audit.md 建议。
    __table_args__ = (
        UniqueConstraint("tenant_id", "room_no"),
        # 覆盖排房 / 夜审在住房 / 房态分布 group_by / 房态盘按店过滤（一次覆盖 4 类查询）
        Index("ix_rooms_tenant_hotel_state", "tenant_id", "hotel_id", "state"),
        # 覆盖房型房量 COUNT
        Index("ix_rooms_tenant_type", "tenant_id", "room_type_id"),
    )

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    room_type_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("room_types.id"), nullable=False)
    room_no: Mapped[str] = mapped_column(String(16), nullable=False)
    floor: Mapped[int] = mapped_column(String(8), default="")
    state: Mapped[str] = mapped_column(
        String(24), default=RoomState.VACANT_CLEAN.value, nullable=False, index=True
    )
    dnd: Mapped[int] = mapped_column(Integer, default=0)  # M31：免打扰 0/1（不影响可售，清扫派单守卫）


class RoomStateEvent(IntPkMixin, TenantMixin, Base):
    """房态事件流水（事件溯源底账，供查询/审计/补偿重放）。"""

    __tablename__ = "room_state_events"

    room_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("rooms.id"), nullable=False, index=True)
    room_no: Mapped[str] = mapped_column(String(16), nullable=False)
    from_state: Mapped[str] = mapped_column(String(24), nullable=False)
    to_state: Mapped[str] = mapped_column(String(24), nullable=False)
    trigger: Mapped[str] = mapped_column(String(24), nullable=False)
    operator: Mapped[str] = mapped_column(String(64), default="system")
    occurred_at: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
