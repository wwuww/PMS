"""餐饮 POS（F&B，M21）

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "menu_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_menu_items_tenant_id", "menu_items", ["tenant_id"])
    op.create_index("ix_menu_items_hotel_id", "menu_items", ["hotel_id"])

    op.create_table(
        "dining_tables",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("table_no", sa.String(length=16), nullable=False),
        sa.Column("seats", sa.Integer(), nullable=False),
        sa.Column("zone", sa.String(length=32), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_dining_tables_tenant_id", "dining_tables", ["tenant_id"])
    op.create_index("ix_dining_tables_hotel_id", "dining_tables", ["hotel_id"])

    op.create_table(
        "pos_orders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("table_id", sa.BigInteger(), sa.ForeignKey("dining_tables.id"), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("settle_type", sa.String(length=16), nullable=True),
        sa.Column("room_no", sa.String(length=16), nullable=True),
        sa.Column("booking_id", sa.BigInteger(), sa.ForeignKey("bookings.id"), nullable=True),
        sa.Column("guest_name", sa.String(length=64), nullable=True),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_pos_orders_tenant_id", "pos_orders", ["tenant_id"])
    op.create_index("ix_pos_orders_hotel_id", "pos_orders", ["hotel_id"])
    op.create_index("ix_pos_orders_table_id", "pos_orders", ["table_id"])
    op.create_index("ix_pos_orders_booking_id", "pos_orders", ["booking_id"])

    op.create_table(
        "pos_order_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("order_id", sa.BigInteger(), sa.ForeignKey("pos_orders.id"), nullable=False),
        sa.Column("item_id", sa.BigInteger(), sa.ForeignKey("menu_items.id"), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False),
    )
    op.create_index("ix_pos_order_items_tenant_id", "pos_order_items", ["tenant_id"])
    op.create_index("ix_pos_order_items_order_id", "pos_order_items", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_pos_order_items_order_id", table_name="pos_order_items")
    op.drop_index("ix_pos_order_items_tenant_id", table_name="pos_order_items")
    op.drop_table("pos_order_items")
    op.drop_index("ix_pos_orders_booking_id", table_name="pos_orders")
    op.drop_index("ix_pos_orders_table_id", table_name="pos_orders")
    op.drop_index("ix_pos_orders_hotel_id", table_name="pos_orders")
    op.drop_index("ix_pos_orders_tenant_id", table_name="pos_orders")
    op.drop_table("pos_orders")
    op.drop_index("ix_dining_tables_hotel_id", table_name="dining_tables")
    op.drop_index("ix_dining_tables_tenant_id", table_name="dining_tables")
    op.drop_table("dining_tables")
    op.drop_index("ix_menu_items_hotel_id", table_name="menu_items")
    op.drop_index("ix_menu_items_tenant_id", table_name="menu_items")
    op.drop_table("menu_items")
