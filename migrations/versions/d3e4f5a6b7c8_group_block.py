"""团队 / 会议排房（M15，FR-GROUP）

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_blocks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("arrival_date", sa.String(length=10), nullable=False),
        sa.Column("departure_date", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_group_blocks_tenant_id", "group_blocks", ["tenant_id"])
    op.create_index("ix_group_blocks_hotel_id", "group_blocks", ["hotel_id"])

    op.create_table(
        "group_allocations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("block_id", sa.BigInteger(), sa.ForeignKey("group_blocks.id"), nullable=False),
        sa.Column("room_id", sa.BigInteger(), sa.ForeignKey("rooms.id"), nullable=False),
        sa.Column("room_no", sa.String(length=16), nullable=False),
        sa.Column("room_type_id", sa.BigInteger(), sa.ForeignKey("room_types.id"), nullable=False),
        sa.Column("guest_name", sa.String(length=64), nullable=True),
        sa.Column("guest_phone", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="assigned"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_group_allocations_tenant_id", "group_allocations", ["tenant_id"])
    op.create_index("ix_group_allocations_block_id", "group_allocations", ["block_id"])


def downgrade() -> None:
    op.drop_index("ix_group_allocations_block_id", table_name="group_allocations")
    op.drop_index("ix_group_allocations_tenant_id", table_name="group_allocations")
    op.drop_table("group_allocations")
    op.drop_index("ix_group_blocks_hotel_id", table_name="group_blocks")
    op.drop_index("ix_group_blocks_tenant_id", table_name="group_blocks")
    op.drop_table("group_blocks")
