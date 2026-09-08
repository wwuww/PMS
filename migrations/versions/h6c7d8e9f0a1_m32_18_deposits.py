"""M32.18 押金与预授权：deposits / deposit_transactions 两表 + shift / daily_report 三栏。

设计文档：``deliverables/architecture/design-m32-18-deposit-2026-09-07.md`` §3.2 / §3.3。

revision: h6c7d8e9f0a1
down_revision: g5b6c7d8e9f0  （M32.18 阶段一：users.pwd_algo）
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "h6c7d8e9f0a1"
down_revision = "g5b6c7d8e9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- 1) deposits 主表 ----------
    op.create_table(
        "deposits",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("hotel_id", sa.BigInteger(), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("deposit_no", sa.String(length=32), nullable=False),
        sa.Column("booking_id", sa.BigInteger(), sa.ForeignKey("bookings.id"), nullable=True),
        sa.Column("room_no", sa.String(length=16), nullable=True),
        sa.Column("bill_id", sa.BigInteger(), sa.ForeignKey("bills.id"), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("applied_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refunded_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("forfeited_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_cents", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="HELD"),
        sa.Column("release_cause", sa.String(length=16), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="CNY"),
        sa.Column("ref_no", sa.String(length=64), nullable=True),
        sa.Column(
            "payment_id",
            sa.BigInteger(),
            sa.ForeignKey("payments.id"),
            nullable=True,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("risk_flag", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("aging_flag", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("refund_channel_override", sa.String(length=32), nullable=True),
        sa.Column(
            "post_checkout_refund",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("forfeit_reason", sa.String(length=255), nullable=True),
        sa.Column(
            "operator", sa.String(length=64), nullable=False, server_default="front_desk"
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.String(length=32), nullable=True),
        sa.Column("released_at", sa.String(length=32), nullable=True),
        sa.Column("captured_at", sa.String(length=32), nullable=True),
        sa.Column("voided_at", sa.String(length=32), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "deposit_no", name="uq_deposits_tenant_deposit_no"),
    )
    op.create_index("ix_deposits_tenant_id", "deposits", ["tenant_id"])
    op.create_index("ix_deposits_hotel_id", "deposits", ["hotel_id"])
    op.create_index("ix_deposits_booking_id", "deposits", ["booking_id"])
    op.create_index("ix_deposits_bill_id", "deposits", ["bill_id"])
    op.create_index("ix_deposits_payment_id", "deposits", ["payment_id"])
    op.create_index(
        "ix_deposits_tenant_status", "deposits", ["tenant_id", "status"]
    )
    op.create_index(
        "ix_deposits_booking", "deposits", ["tenant_id", "booking_id"]
    )
    op.create_index(
        "ix_deposits_preauth_expiry",
        "deposits",
        ["tenant_id", "kind", "status", "created_at"],
    )

    # ---------- 2) deposit_transactions 流水 ----------
    op.create_table(
        "deposit_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column(
            "deposit_id", sa.BigInteger(), sa.ForeignKey("deposits.id"), nullable=False
        ),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("ref_no", sa.String(length=64), nullable=True),
        sa.Column("bill_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "operator", sa.String(length=64), nullable=False, server_default="front_desk"
        ),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_deposit_transactions_tenant_id", "deposit_transactions", ["tenant_id"]
    )
    op.create_index(
        "ix_deposit_transactions_deposit_id", "deposit_transactions", ["deposit_id"]
    )
    op.create_index(
        "ix_dep_txn_deposit",
        "deposit_transactions",
        ["deposit_id", "created_at"],
    )
    op.create_index(
        "ix_dep_txn_shift",
        "deposit_transactions",
        ["tenant_id", "action", "created_at"],
    )

    # ---------- 3) shift_handovers 三栏（team-lead 裁决，对齐 PM §6.5） ----------
    with op.batch_alter_table("shift_handovers") as batch:
        batch.add_column(
            sa.Column(
                "deposit_in_cents",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "deposit_out_cents",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "deposit_held_cents",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    # ---------- 4) daily_reports 三栏（与 shift_handovers 对齐） ----------
    with op.batch_alter_table("daily_reports") as batch:
        batch.add_column(
            sa.Column(
                "deposit_in_cents",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "deposit_out_cents",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "deposit_held_cents",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("daily_reports") as batch:
        batch.drop_column("deposit_held_cents")
        batch.drop_column("deposit_out_cents")
        batch.drop_column("deposit_in_cents")
    with op.batch_alter_table("shift_handovers") as batch:
        batch.drop_column("deposit_held_cents")
        batch.drop_column("deposit_out_cents")
        batch.drop_column("deposit_in_cents")

    op.drop_index("ix_dep_txn_shift", table_name="deposit_transactions")
    op.drop_index("ix_dep_txn_deposit", table_name="deposit_transactions")
    op.drop_index(
        "ix_deposit_transactions_deposit_id", table_name="deposit_transactions"
    )
    op.drop_index(
        "ix_deposit_transactions_tenant_id", table_name="deposit_transactions"
    )
    op.drop_table("deposit_transactions")

    op.drop_index("ix_deposits_preauth_expiry", table_name="deposits")
    op.drop_index("ix_deposits_booking", table_name="deposits")
    op.drop_index("ix_deposits_tenant_status", table_name="deposits")
    op.drop_index("ix_deposits_payment_id", table_name="deposits")
    op.drop_index("ix_deposits_bill_id", table_name="deposits")
    op.drop_index("ix_deposits_booking_id", table_name="deposits")
    op.drop_index("ix_deposits_hotel_id", table_name="deposits")
    op.drop_index("ix_deposits_tenant_id", table_name="deposits")
    op.drop_table("deposits")
