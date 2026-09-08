"""餐饮报表(F&B) + 厨房出单(KDS，M22)

Revision ID: f1a2b3c4d5e6
Revises: e4f5a6b7c8d9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pos_order_items", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("category", sa.String(length=32), nullable=True)
        )  # 品类销售报表冗余字段（热菜/凉菜/酒水/主食/其他）
        batch_op.add_column(
            sa.Column(
                "kds_status",
                sa.String(length=16),
                nullable=False,
                server_default="pending",
            )
        )  # pending|ready|served


def downgrade() -> None:
    with op.batch_alter_table("pos_order_items", schema=None) as batch_op:
        batch_op.drop_column("kds_status")
        batch_op.drop_column("category")
