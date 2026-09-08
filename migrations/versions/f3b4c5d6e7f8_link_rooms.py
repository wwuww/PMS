"""M32.15 在住联房：bookings 增加 link_group_id / is_link_master。

revision: f3b4c5d6e7f8
down_revision: f2a3b4c5d6e7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("bookings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("link_group_id", sa.String(36), nullable=True))
        batch_op.add_column(
            sa.Column("is_link_master", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.create_index("ix_bookings_link_group_id", ["link_group_id"])


def downgrade() -> None:
    with op.batch_alter_table("bookings", schema=None) as batch_op:
        batch_op.drop_index("ix_bookings_link_group_id")
        batch_op.drop_column("is_link_master")
        batch_op.drop_column("link_group_id")
