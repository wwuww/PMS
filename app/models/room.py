"""房型、房间与房态事件（M1）。"""

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, String, UniqueConstraint
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
    # 批次② 字段补全（维也纳字典对齐，全 additive）
    bed_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 床数
    short_name: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 简称
    en_name: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 英文名
    descript: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 房型描述
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 是否启用


class Room(IntPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "rooms"
    # M30 性能：复合索引以 tenant_id 为前导（ShardingSphere 分片键 = tenant_id，
    # 无前导列会跨片广播）。均按 audit docs/M30-performance-audit.md 建议。
    __table_args__ = (
        UniqueConstraint("tenant_id", "room_no"),
        Index("ix_rooms_tenant_building", "tenant_id", "building_id"),
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
    # 批次② 字段补全（维也纳字典对齐，全 additive）
    building_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 楼栋（纯编码，不建表）
    telephone: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 电话分机
    room_card_no: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 房卡号
    room_name: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 房间名/别名
    memo: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 备注
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 是否有效（停用房不参与排房）


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


class RoomChange(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """换房记录（M37-③）。

    每次 ``booking_service.change_room`` 落一条 WORM 记录（不删不改为营改/审计刚需）。
    ``price_diff_cents = to_price - from_price``，> 0 时由 service 写 ``BillItem(ROOM_CHARGE)``
    差价入账并累加 ``Bill.balance``（与夜审房费过账口径一致）。
    """

    __tablename__ = "room_changes"

    __table_args__ = (
        UniqueConstraint("tenant_id", "change_no", name="uq_room_changes_tenant_change_no"),
        Index("ix_room_changes_tenant_booking", "tenant_id", "booking_id"),
        Index("ix_room_changes_tenant_from_room", "tenant_id", "from_room_no"),
        Index("ix_room_changes_tenant_bizdate", "tenant_id", "business_date"),
    )

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False)
    change_no: Mapped[str] = mapped_column(String(32), nullable=False)  # 变更号（租户内唯一）
    booking_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("bookings.id"), nullable=False)
    bill_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("bills.id"), nullable=True)
    from_room_no: Mapped[str | None] = mapped_column(String(16), nullable=True)
    to_room_no: Mapped[str | None] = mapped_column(String(16), nullable=True)
    from_room_type_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    to_room_type_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    from_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_diff_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)  # 换房原因（审计刚需）
    business_date: Mapped[str] = mapped_column(String(10), nullable=False)  # 营业日
    operator: Mapped[str] = mapped_column(String(64), nullable=False, default="front_desk")


class RoomAttribute(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """房间属性（M37-④）。

    维也纳 ``RoomAttribute``(9) + ``RoomDescript``(6) 合并为一张表：后者用
    ``attribute_code`` 的 ``DESC:*`` 命名空间区分（两表结构同构，拆表只增加 JOIN 成本）。
    ``room_no`` 冗余存储以避免排房时 JOIN；``UQ(tenant_id, room_id, attribute_code)``
    保证同房间同属性不重复。
    """

    __tablename__ = "room_attributes"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "room_id", "attribute_code", name="uq_room_attr_tenant_room_code"
        ),
        Index("ix_room_attr_tenant_room", "tenant_id", "room_no"),
        Index("ix_room_attr_tenant_code", "tenant_id", "attribute_code", "is_valid"),
    )

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False)
    room_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("rooms.id"), nullable=False)
    room_no: Mapped[str] = mapped_column(String(16), nullable=False)
    attribute_code: Mapped[str] = mapped_column(String(16), nullable=False)  # SMOKE_FREE/BIG_BED/WINDOW/DESC:* 等
    attribute_name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    operator: Mapped[str] = mapped_column(String(64), nullable=False, default="front_desk")
    memo: Mapped[str | None] = mapped_column(String(128), nullable=True)
