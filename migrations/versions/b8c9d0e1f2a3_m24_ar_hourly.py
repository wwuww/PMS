"""M24 前台深度 II：AR 协议单位挂账 + 时租房字段。

- 新表 ar_accounts（协议单位）、ar_repayments（还款流水）
- bills 加 ar_account_id（挂账关联，SQLite ADD COLUMN 原生支持 REFERENCES）
- room_types 加 hourly_rate（时租价，分/小时）
- bookings 加 stay_type（daily|hourly）、hourly_hours

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ar_accounts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tenant_id", sa.String(32), nullable=False, index=True),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("contact", sa.String(64), nullable=True),
        sa.Column("contact_phone", sa.String(32), nullable=True),
        sa.Column("credit_limit_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("balance_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_ar_accounts_tenant_name"),
    )
    op.create_index("ix_ar_accounts_hotel_id", "ar_accounts", ["hotel_id"])
    op.create_table(
        "ar_repayments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("tenant_id", sa.String(32), nullable=False, index=True),
        sa.Column("ar_account_id", sa.BigInteger(), sa.ForeignKey("ar_accounts.id"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(16), nullable=False, server_default="BANK"),
        sa.Column("operator", sa.String(64), nullable=False, server_default="front_desk"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ar_repayments_ar_account_id", "ar_repayments", ["ar_account_id"])

    # SQLite 不支持裸 ALTER 加约束 → batch（copy-and-move）重建，需命名约定为反射出的匿名约束命名
    with op.batch_alter_table(
        "bills",
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        },
    ) as batch:
        batch.add_column(
            sa.Column(
                "ar_account_id",
                sa.BigInteger(),
                sa.ForeignKey(
                    "ar_accounts.id", name="fk_bills_ar_account_id_ar_accounts"
                ),
                nullable=True,
            )
        )
    op.create_index("ix_bills_ar_account_id", "bills", ["ar_account_id"])
    op.add_column("room_types", sa.Column("hourly_rate", sa.Integer(), nullable=True))
    op.add_column(
        "bookings",
        sa.Column("stay_type", sa.String(8), nullable=False, server_default="daily"),
    )
    op.add_column("bookings", sa.Column("hourly_hours", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "hourly_hours")
    op.drop_column("bookings", "stay_type")
    op.drop_column("room_types", "hourly_rate")
    op.drop_index("ix_bills_ar_account_id", table_name="bills")
    with op.batch_alter_table(
        "bills",
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        },
    ) as batch:
        batch.drop_column("ar_account_id")
    op.drop_index("ix_ar_repayments_ar_account_id", table_name="ar_repayments")
    op.drop_table("ar_repayments")
    op.drop_index("ix_ar_accounts_hotel_id", table_name="ar_accounts")
    op.drop_table("ar_accounts")
