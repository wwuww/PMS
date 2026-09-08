"""M23 前台运营深度：NoShow 原因列 + 交班三口径列

- bookings.noshow_reason：NoShow 原因（夜审自动 / 前台手动）
- shift_handovers.received_cents：班内实收合计（全支付方式）
- shift_handovers.receivable_cents：班内应收合计

对应验收清单 #3（NoShow 自动处理并记录原因）与 #11（交班现金流/实收/应收三模式）。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("bookings") as batch_op:
        batch_op.add_column(sa.Column("noshow_reason", sa.String(length=255), nullable=True))

    with op.batch_alter_table("shift_handovers") as batch_op:
        batch_op.add_column(
            sa.Column("received_cents", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("receivable_cents", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("shift_handovers") as batch_op:
        batch_op.drop_column("receivable_cents")
        batch_op.drop_column("received_cents")

    with op.batch_alter_table("bookings") as batch_op:
        batch_op.drop_column("noshow_reason")
