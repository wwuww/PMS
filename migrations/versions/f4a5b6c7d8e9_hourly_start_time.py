"""M32.17b 钟点房到离店时刻：bookings 增加 hourly_start_time（HH:MM）。

revision: f4a5b6c7d8e9
down_revision: f3b4c5d6e7f8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f4a5b6c7d8e9"
down_revision = "f3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("bookings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("hourly_start_time", sa.String(5), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("bookings", schema=None) as batch_op:
        batch_op.drop_column("hourly_start_time")
