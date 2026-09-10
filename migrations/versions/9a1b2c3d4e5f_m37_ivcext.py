"""M37-③ 发票 + 换房记录 + 续住记录 三表。

对齐维也纳 PMS 数据字典：invoices（18+4）、room_changes（12+2）、stay_extensions（6+4）。
``down_revision`` 指向 ② ``3a7b9c2d4e6f``，使 revision 链「改老表→建新表」自然顺序。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "9a1b2c3d4e5f"
down_revision = "3a7b9c2d4e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- 1) invoices ----------
    op.create_table(
        "invoices",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("invoice_no", sa.String(length=32), nullable=False),
        sa.Column("bill_id", sa.BigInteger(), sa.ForeignKey("bills.id"), nullable=True),
        sa.Column("booking_id", sa.BigInteger(), sa.ForeignKey("bookings.id"), nullable=True),
        sa.Column("room_no", sa.String(length=16), nullable=True),
        sa.Column("guest_name", sa.String(length=128), nullable=True),
        sa.Column("agreement_no", sa.String(length=32), nullable=True),
        sa.Column("check_in_at", sa.String(length=32), nullable=True),
        sa.Column("check_out_at", sa.String(length=32), nullable=False),
        sa.Column("check_in_type", sa.String(length=16), nullable=True),
        sa.Column("consume_amount_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invoice_amount_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("invoice_type", sa.String(length=16), nullable=False, server_default="NORMAL"),
        sa.Column("title", sa.String(length=128), nullable=True),
        sa.Column("tax_no", sa.String(length=64), nullable=True),
        sa.Column("approver", sa.String(length=64), nullable=True),
        sa.Column("work_shift", sa.String(length=50), nullable=True),
        sa.Column("flag", sa.String(length=1), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ISSUED"),
        sa.Column("operator", sa.String(length=64), nullable=False, server_default="front_desk"),
        sa.Column("memo", sa.String(length=255), nullable=True),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "invoice_no", name="uq_invoices_tenant_invoice_no"),
    )
    op.create_index("ix_invoices_tenant_id", "invoices", ["tenant_id"])
    op.create_index(
        "ix_invoices_tenant_bill", "invoices", ["tenant_id", "bill_id"]
    )
    op.create_index(
        "ix_invoices_tenant_booking", "invoices", ["tenant_id", "booking_id"]
    )
    op.create_index(
        "ix_invoices_tenant_status", "invoices", ["tenant_id", "status"]
    )

    # ---------- 2) room_changes ----------
    op.create_table(
        "room_changes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("change_no", sa.String(length=32), nullable=False),
        sa.Column("booking_id", sa.BigInteger(), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("bill_id", sa.BigInteger(), sa.ForeignKey("bills.id"), nullable=True),
        sa.Column("from_room_no", sa.String(length=16), nullable=True),
        sa.Column("to_room_no", sa.String(length=16), nullable=True),
        sa.Column("from_room_type_id", sa.BigInteger(), nullable=True),
        sa.Column("to_room_type_id", sa.BigInteger(), nullable=True),
        sa.Column("from_price_cents", sa.Integer(), nullable=True),
        sa.Column("to_price_cents", sa.Integer(), nullable=True),
        sa.Column("price_diff_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("business_date", sa.String(length=10), nullable=False),
        sa.Column("operator", sa.String(length=64), nullable=False, server_default="front_desk"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "change_no", name="uq_room_changes_tenant_change_no"),
    )
    op.create_index("ix_room_changes_tenant_id", "room_changes", ["tenant_id"])
    op.create_index(
        "ix_room_changes_tenant_booking", "room_changes", ["tenant_id", "booking_id"]
    )
    op.create_index(
        "ix_room_changes_tenant_from_room", "room_changes", ["tenant_id", "from_room_no"]
    )
    op.create_index(
        "ix_room_changes_tenant_bizdate", "room_changes", ["tenant_id", "business_date"]
    )

    # ---------- 3) stay_extensions ----------
    op.create_table(
        "stay_extensions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("booking_id", sa.BigInteger(), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("room_no", sa.String(length=16), nullable=True),
        sa.Column("bill_id", sa.BigInteger(), sa.ForeignKey("bills.id"), nullable=True),
        sa.Column("business_date", sa.String(length=10), nullable=False),
        sa.Column("start_date", sa.String(length=10), nullable=False),
        sa.Column("end_date", sa.String(length=10), nullable=False),
        sa.Column("nights", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("added_amount_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("operator", sa.String(length=64), nullable=False, server_default="front_desk"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_stay_extensions_tenant_id", "stay_extensions", ["tenant_id"])
    op.create_index(
        "ix_stay_ext_tenant_booking", "stay_extensions", ["tenant_id", "booking_id"]
    )
    op.create_index(
        "ix_stay_ext_tenant_bizdate", "stay_extensions", ["tenant_id", "business_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_stay_ext_tenant_bizdate", table_name="stay_extensions")
    op.drop_index("ix_stay_ext_tenant_booking", table_name="stay_extensions")
    op.drop_index("ix_stay_extensions_tenant_id", table_name="stay_extensions")
    op.drop_table("stay_extensions")

    op.drop_index("ix_room_changes_tenant_bizdate", table_name="room_changes")
    op.drop_index("ix_room_changes_tenant_from_room", table_name="room_changes")
    op.drop_index("ix_room_changes_tenant_booking", table_name="room_changes")
    op.drop_index("ix_room_changes_tenant_id", table_name="room_changes")
    op.drop_table("room_changes")

    op.drop_index("ix_invoices_tenant_status", table_name="invoices")
    op.drop_index("ix_invoices_tenant_booking", table_name="invoices")
    op.drop_index("ix_invoices_tenant_bill", table_name="invoices")
    op.drop_index("ix_invoices_tenant_id", table_name="invoices")
    op.drop_table("invoices")
