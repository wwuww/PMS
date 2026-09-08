"""M32 周报/月报快照：report_snapshots 表。

验收 #14：自动生成日报/周报/月报。夜审周期切换时固化 dashboard 聚合指标。

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def _snapshots_table() -> sa.Table:
    return sa.Table(
        "report_snapshots",
        sa.MetaData(),
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("period_type", sa.String(16), nullable=False, server_default="WEEKLY"),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("metrics", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("source", sa.String(16), nullable=False, server_default="AUTO"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "report_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("period_type", sa.String(16), nullable=False, server_default="WEEKLY"),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("metrics", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("source", sa.String(16), nullable=False, server_default="AUTO"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "tenant_id", "hotel_id", "period_type", "period_start",
            name="ix_report_snapshots_tenant_hotel_period",
        ),
    )
    op.create_index("ix_report_snapshots_hotel_id", "report_snapshots", ["hotel_id"])
    op.create_index("ix_report_snapshots_period_type", "report_snapshots", ["period_type"])
    op.create_index("ix_report_snapshots_tenant_id", "report_snapshots", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("report_snapshots")
