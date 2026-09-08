"""餐饮 POS（F&B，M21）。

最小可行闭环：菜品(menu_items) → 餐桌(dining_tables) → 餐饮账单(pos_orders)
+ 明细(pos_order_items)，支持「挂房账(room)」与「现金(cash)」两种结账，
复用既有 CashierService / Bill 入账，保证财务口径一致（余额 = Σ应收 − Σ实收）。

设计取舍（dev-plan）：
- 不新建独立账务体系，餐饮消费统一走房账/Bill，避免双账本漂移。
- 餐桌状态 free/occupied/cleaning 仅供前厅可视化，不影响账务。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class MenuItem(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """菜品（租户级，可按门店下架）。"""

    __tablename__ = "menu_items"

    hotel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hotels.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="其他")  # 热菜/凉菜/酒水/主食
    price_cents: Mapped[int] = mapped_column(Integer, default=0)  # 分
    is_active: Mapped[int] = mapped_column(Integer, default=1)  # 0/1
    sold_out: Mapped[int] = mapped_column(Integer, default=0)  # M27：沽清 0/1（当日售罄拒点）


class DiningTable(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """餐桌 / 桌台。"""

    __tablename__ = "dining_tables"

    hotel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hotels.id"), nullable=False, index=True
    )
    table_no: Mapped[str] = mapped_column(String(16), nullable=False)
    seats: Mapped[int] = mapped_column(Integer, default=2)
    zone: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 大厅/包厢
    state: Mapped[str] = mapped_column(
        String(16), default="free"
    )  # free|occupied|cleaning


class PosOrder(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """餐饮账单（开单 → 点菜 → 结账）。

    settle_type: room(挂房账) / cash(现金)；room 结账时 room_no/booking_id 关联客房。
    """

    __tablename__ = "pos_orders"

    # M30 性能：一个索引覆盖 list_orders 与营业报表两处；
    # 雪花 ID 与 created_at 同向递增，天然有序（分片键 tenant_id 前导）。
    __table_args__ = (
        Index(
            "ix_pos_orders_tenant_hotel_status_created",
            "tenant_id",
            "hotel_id",
            "status",
            "created_at",
        ),
    )

    hotel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hotels.id"), nullable=False, index=True
    )
    table_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("dining_tables.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|settled
    settle_type: Mapped[str | None] = mapped_column(String(16), nullable=True)  # room|cash
    room_no: Mapped[str | None] = mapped_column(String(16), nullable=True)
    booking_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("bookings.id"), nullable=True, index=True
    )
    guest_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_cents: Mapped[int] = mapped_column(Integer, default=0)  # 分（未折毛额）
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)  # M27：整单折扣（分）


class PosOrderItem(IntPkMixin, TenantMixin, Base):
    """餐饮账单明细（点菜行）。

    category：冗余自 MenuItem.category（手动加菜兜底"其他"），供品类销售报表免 join。
    kds_status：厨房出单状态 pending(待做) → ready(已出餐) → served(已上菜)。
    """

    __tablename__ = "pos_order_items"

    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pos_orders.id"), nullable=False, index=True
    )
    item_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("menu_items.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 热菜/凉菜/酒水/主食/其他
    qty: Mapped[int] = mapped_column(Integer, default=1)
    unit_price_cents: Mapped[int] = mapped_column(Integer, default=0)  # 分
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0)  # 分
    kds_status: Mapped[str] = mapped_column(
        String(16), default="pending"
    )  # pending|ready|served
    voided: Mapped[int] = mapped_column(Integer, default=0)  # M27：退菜 0/1
    void_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)  # M27：退菜原因
