"""M29 OTA 直连：房型映射 + 渠道价 + 推送日志三张表。

设计文档：``deliverables/architecture/design-m29-ota-2026-09-07.md`` §3。

revision: i7d8e9f0a1b2
down_revision: h6c7d8e9f0a1  （M32.18 押金与预授权）
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "i7d8e9f0a1b2"
down_revision = "h6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- 1) channel_room_mappings 房型映射 ----------
    op.create_table(
        "channel_room_mappings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("pms_room_type_id", sa.BigInteger(), nullable=False),
        sa.Column("external_room_type_code", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "hotel_id", "channel", "pms_room_type_id",
            name="uq_chmap_tenant_hotel_channel_pms",
        ),
    )
    op.create_index(
        "ix_channel_room_mappings_tenant_id", "channel_room_mappings", ["tenant_id"]
    )
    op.create_index(
        "ix_channel_room_mappings_hotel_id", "channel_room_mappings", ["hotel_id"]
    )
    op.create_index(
        "ix_channel_room_mappings_pms_room_type_id",
        "channel_room_mappings",
        ["pms_room_type_id"],
    )
    # 反查唯一索引：webhook 注入时按 external_code 反查 PMS 房型
    op.create_index(
        "ix_chmap_lookup",
        "channel_room_mappings",
        ["tenant_id", "hotel_id", "channel", "external_room_type_code"],
    )

    # ---------- 2) channel_rate_plans 渠道价 ----------
    op.create_table(
        "channel_rate_plans",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("pms_room_type_id", sa.BigInteger(), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "hotel_id", "channel", "pms_room_type_id", "effective_date",
            name="uq_rate_tenant_hotel_channel_pms_date",
        ),
    )
    op.create_index(
        "ix_channel_rate_plans_tenant_id", "channel_rate_plans", ["tenant_id"]
    )
    op.create_index(
        "ix_channel_rate_plans_hotel_id", "channel_rate_plans", ["hotel_id"]
    )
    op.create_index(
        "ix_channel_rate_plans_pms_room_type_id",
        "channel_rate_plans",
        ["pms_room_type_id"],
    )

    # ---------- 3) channel_push_logs 推送日志 ----------
    op.create_table(
        "channel_push_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="SUCCESS"),
        sa.Column("trace_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("response_summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("error_message", sa.String(length=512), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("operator", sa.String(length=64), nullable=False, server_default="admin"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_channel_push_logs_tenant_id", "channel_push_logs", ["tenant_id"]
    )
    op.create_index(
        "ix_channel_push_logs_hotel_id", "channel_push_logs", ["hotel_id"]
    )
    op.create_index(
        "ix_channel_push_logs_channel", "channel_push_logs", ["channel"]
    )
    op.create_index(
        "ix_push_log_tenant_created",
        "channel_push_logs",
        ["tenant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_push_log_tenant_created", table_name="channel_push_logs")
    op.drop_index("ix_channel_push_logs_channel", table_name="channel_push_logs")
    op.drop_index("ix_channel_push_logs_hotel_id", table_name="channel_push_logs")
    op.drop_index("ix_channel_push_logs_tenant_id", table_name="channel_push_logs")
    op.drop_table("channel_push_logs")

    op.drop_index(
        "ix_channel_rate_plans_pms_room_type_id", table_name="channel_rate_plans"
    )
    op.drop_index(
        "ix_channel_rate_plans_hotel_id", table_name="channel_rate_plans"
    )
    op.drop_index(
        "ix_channel_rate_plans_tenant_id", table_name="channel_rate_plans"
    )
    op.drop_table("channel_rate_plans")

    op.drop_index("ix_chmap_lookup", table_name="channel_room_mappings")
    op.drop_index(
        "ix_channel_room_mappings_pms_room_type_id", table_name="channel_room_mappings"
    )
    op.drop_index(
        "ix_channel_room_mappings_hotel_id", table_name="channel_room_mappings"
    )
    op.drop_index(
        "ix_channel_room_mappings_tenant_id", table_name="channel_room_mappings"
    )
    op.drop_table("channel_room_mappings")
