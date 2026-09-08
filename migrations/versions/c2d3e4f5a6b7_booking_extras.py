"""booking_extras

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-09-04 17:10:00.000000

在住附加服务（M14-2，FR-GUEST-EXT）：加床数 + 同住人姓名。
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('extra_bed_count', sa.Integer(), nullable=False, server_default=sa.text('0'))
        )
        batch_op.add_column(sa.Column('companion_names', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_column('companion_names')
        batch_op.drop_column('extra_bed_count')
