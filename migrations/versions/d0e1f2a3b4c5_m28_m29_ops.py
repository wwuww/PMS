"""M28 A2 收尾 + M29 OTA 直连：投诉工单 / OTA 渠道配置 / 预订外部回链 / 库存查询索引。

- 新表 complaints（投诉，与住客/预订关联，处理流转）
- 新表 ota_channel_configs（每租户每渠道签名配置）
- bookings 加 external_channel / external_ref（OTA 幂等回链，SQLite 走 batch）
- bookings 加 ix_bookings_hotel_checkin（M30 可用性查询热点索引）

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "complaints",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("booking_id", sa.BigInteger(), sa.ForeignKey("bookings.id"), nullable=True),
        sa.Column("guest_name", sa.String(64), nullable=False),
        sa.Column("guest_phone", sa.String(32), nullable=True),
        sa.Column("room_no", sa.String(16), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="FRONT_DESK"),
        sa.Column("category", sa.String(32), nullable=False, server_default="SERVICE"),
        sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("description", sa.String(512), nullable=False, server_default=""),
        sa.Column("handler", sa.String(64), nullable=True),
        sa.Column("resolution", sa.String(512), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_complaints_hotel_id", "complaints", ["hotel_id"])
    op.create_index("ix_complaints_booking_id", "complaints", ["booking_id"])
    op.create_index("ix_complaints_guest_phone", "complaints", ["guest_phone"])
    op.create_index("ix_complaints_status", "complaints", ["status"])
    op.create_index("ix_complaints_tenant_id", "complaints", ["tenant_id"])

    op.create_table(
        "ota_channel_configs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("app_key", sa.String(64), nullable=False, server_default=""),
        sa.Column("secret", sa.String(128), nullable=False),
        sa.Column("push_enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("push_inventory_url", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "channel", name="uq_ota_tenant_channel"),
    )
    op.create_index("ix_ota_channel_configs_hotel_id", "ota_channel_configs", ["hotel_id"])
    op.create_index("ix_ota_channel_configs_tenant_id", "ota_channel_configs", ["tenant_id"])

    # bookings：OTA 幂等回链（无 FK，纯列，SQLite batch 安全）
    with op.batch_alter_table("bookings") as batch:
        batch.add_column(sa.Column("external_channel", sa.String(32), nullable=True))
        batch.add_column(sa.Column("external_ref", sa.String(64), nullable=True))
    op.create_index("ix_bookings_external_channel", "bookings", ["external_channel"])
    op.create_index("ix_bookings_external_ref", "bookings", ["external_ref"])
    # M30：可用性热点查询索引（hotel_id + 入住日）
    op.create_index("ix_bookings_hotel_checkin", "bookings", ["hotel_id", "check_in_date"])


def downgrade() -> None:
    op.drop_index("ix_bookings_hotel_checkin", table_name="bookings")
    op.drop_index("ix_bookings_external_ref", table_name="bookings")
    op.drop_index("ix_bookings_external_channel", table_name="bookings")
    with op.batch_alter_table("bookings") as batch:
        batch.drop_column("external_ref")
        batch.drop_column("external_channel")
    op.drop_index("ix_ota_channel_configs_tenant_id", table_name="ota_channel_configs")
    op.drop_index("ix_ota_channel_configs_hotel_id", table_name="ota_channel_configs")
    op.drop_table("ota_channel_configs")
    op.drop_index("ix_complaints_tenant_id", table_name="complaints")
    op.drop_index("ix_complaints_status", table_name="complaints")
    op.drop_index("ix_complaints_guest_phone", table_name="complaints")
    op.drop_index("ix_complaints_booking_id", table_name="complaints")
    op.drop_index("ix_complaints_hotel_id", table_name="complaints")
    op.drop_table("complaints")
