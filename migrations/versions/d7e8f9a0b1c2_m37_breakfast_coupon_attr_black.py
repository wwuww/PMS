"""M37-④ 早餐券 + 优惠券(模板/实例) + 房间属性 + 黑名单 五表。

对齐维也纳 PMS 数据字典：Breakfast(17→16) / OrderCoupon(11→实例表，另加模板表)
/ RoomAttribute+RoomDescript 合并 / BlackGuest(5→11)。
``down_revision`` 指向 ③ ``9a1b2c3d4e5f``。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d7e8f9a0b1c2"
down_revision = "9a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- 1) room_attributes ----------
    op.create_table(
        "room_attributes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("room_id", sa.BigInteger(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("room_no", sa.String(length=16), nullable=False),
        sa.Column("attribute_code", sa.String(length=16), nullable=False),
        sa.Column("attribute_name", sa.String(length=64), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("operator", sa.String(length=64), nullable=False, server_default="front_desk"),
        sa.Column("memo", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "room_id", "attribute_code", name="uq_room_attr_tenant_room_code"
        ),
    )
    op.create_index("ix_room_attributes_tenant_id", "room_attributes", ["tenant_id"])
    op.create_index(
        "ix_room_attr_tenant_room", "room_attributes", ["tenant_id", "room_no"]
    )
    op.create_index(
        "ix_room_attr_tenant_code",
        "room_attributes",
        ["tenant_id", "attribute_code", "is_valid"],
    )

    # ---------- 2) black_guests ----------
    op.create_table(
        "black_guests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("id_no", sa.String(length=64), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("operator", sa.String(length=64), nullable=False, server_default="front_desk"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_black_guests_tenant_id", "black_guests", ["tenant_id"])
    op.create_index("ix_black_tenant_name", "black_guests", ["tenant_id", "name"])
    op.create_index("ix_black_tenant_idno", "black_guests", ["tenant_id", "id_no"])
    op.create_index("ix_black_tenant_phone", "black_guests", ["tenant_id", "phone"])
    op.create_index(
        "ix_black_tenant_valid_level",
        "black_guests",
        ["tenant_id", "is_valid", "level"],
    )

    # ---------- 3) breakfast_tickets ----------
    op.create_table(
        "breakfast_tickets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("ticket_no", sa.String(length=32), nullable=False),
        sa.Column("booking_id", sa.BigInteger(), sa.ForeignKey("bookings.id"), nullable=True),
        sa.Column("room_no", sa.String(length=16), nullable=True),
        sa.Column("card_type", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ticket_type", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ticket_type_name", sa.String(length=64), nullable=True),
        sa.Column("valid_from", sa.String(length=10), nullable=True),
        sa.Column("valid_to", sa.String(length=10), nullable=True),
        sa.Column("used_business_date", sa.String(length=10), nullable=True),
        sa.Column("is_used", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("shift_id", sa.BigInteger(), nullable=True),
        sa.Column("operator", sa.String(length=64), nullable=False, server_default="front_desk"),
        sa.Column("memo", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "ticket_no", name="uq_bf_tenant_ticket_no"
        ),
    )
    op.create_index("ix_breakfast_tickets_tenant_id", "breakfast_tickets", ["tenant_id"])
    op.create_index(
        "ix_bf_tenant_booking", "breakfast_tickets", ["tenant_id", "booking_id"]
    )
    op.create_index("ix_bf_tenant_type", "breakfast_tickets", ["tenant_id", "ticket_type"])
    op.create_index(
        "ix_bf_tenant_used", "breakfast_tickets", ["tenant_id", "is_used", "valid_to"]
    )

    # ---------- 4) coupon_templates ----------
    op.create_table(
        "coupon_templates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("ticket_type", sa.String(length=8), nullable=False, server_default="VOUCHER"),
        sa.Column("discount_type", sa.String(length=16), nullable=False, server_default="AMOUNT"),
        sa.Column("discount_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_from", sa.String(length=10), nullable=False),
        sa.Column("valid_to", sa.String(length=10), nullable=False),
        sa.Column("total_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("issued_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("operator", sa.String(length=64), nullable=False, server_default="front_desk"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "code", name="uq_coupon_tpl_tenant_code"
        ),
    )
    op.create_index("ix_coupon_templates_tenant_id", "coupon_templates", ["tenant_id"])
    op.create_index(
        "ix_coupon_tpl_tenant_valid", "coupon_templates", ["tenant_id", "is_valid"]
    )

    # ---------- 5) coupons ----------
    op.create_table(
        "coupons",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column(
            "template_id",
            sa.BigInteger(),
            sa.ForeignKey("coupon_templates.id"),
            nullable=True,
        ),
        sa.Column("coupon_no", sa.String(length=32), nullable=False),
        sa.Column("ticket_type", sa.String(length=8), nullable=False, server_default="VOUCHER"),
        sa.Column("discount_type", sa.String(length=16), nullable=False, server_default="AMOUNT"),
        sa.Column("discount_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("valid_from", sa.String(length=10), nullable=False),
        sa.Column("valid_to", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ISSUED"),
        sa.Column("booking_id", sa.BigInteger(), sa.ForeignKey("bookings.id"), nullable=True),
        sa.Column("bill_id", sa.BigInteger(), sa.ForeignKey("bills.id"), nullable=True),
        sa.Column("used_at", sa.String(length=32), nullable=True),
        sa.Column(
            "is_cover_other_discount",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "is_transfer_to_account",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("operator", sa.String(length=64), nullable=False, server_default="front_desk"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "coupon_no", name="uq_coupons_tenant_coupon_no"
        ),
    )
    op.create_index("ix_coupons_tenant_id", "coupons", ["tenant_id"])
    op.create_index("ix_coupons_tenant_status", "coupons", ["tenant_id", "status"])
    op.create_index(
        "ix_coupons_tenant_valid", "coupons", ["tenant_id", "status", "valid_to"]
    )
    op.create_index("ix_coupons_tenant_booking", "coupons", ["tenant_id", "booking_id"])
    op.create_index("ix_coupons_tenant_template", "coupons", ["tenant_id", "template_id"])


def downgrade() -> None:
    op.drop_index("ix_coupons_tenant_template", table_name="coupons")
    op.drop_index("ix_coupons_tenant_booking", table_name="coupons")
    op.drop_index("ix_coupons_tenant_valid", table_name="coupons")
    op.drop_index("ix_coupons_tenant_status", table_name="coupons")
    op.drop_index("ix_coupons_tenant_id", table_name="coupons")
    op.drop_table("coupons")

    op.drop_index("ix_coupon_tpl_tenant_valid", table_name="coupon_templates")
    op.drop_index("ix_coupon_templates_tenant_id", table_name="coupon_templates")
    op.drop_table("coupon_templates")

    op.drop_index("ix_bf_tenant_used", table_name="breakfast_tickets")
    op.drop_index("ix_bf_tenant_type", table_name="breakfast_tickets")
    op.drop_index("ix_bf_tenant_booking", table_name="breakfast_tickets")
    op.drop_index("ix_breakfast_tickets_tenant_id", table_name="breakfast_tickets")
    op.drop_table("breakfast_tickets")

    op.drop_index("ix_black_tenant_valid_level", table_name="black_guests")
    op.drop_index("ix_black_tenant_phone", table_name="black_guests")
    op.drop_index("ix_black_tenant_idno", table_name="black_guests")
    op.drop_index("ix_black_tenant_name", table_name="black_guests")
    op.drop_index("ix_black_guests_tenant_id", table_name="black_guests")
    op.drop_table("black_guests")

    op.drop_index("ix_room_attr_tenant_code", table_name="room_attributes")
    op.drop_index("ix_room_attr_tenant_room", table_name="room_attributes")
    op.drop_index("ix_room_attributes_tenant_id", table_name="room_attributes")
    op.drop_table("room_attributes")
