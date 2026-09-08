"""m31_noshow_charge_first_night

Revision ID: f2fa79c0e2e8
Revises: baea576c411d
Create Date: 2026-09-08 15:37:48.124427
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2fa79c0e2e8'
down_revision: Union[str, None] = 'baea576c411d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # M31：NoShow 自动扣首晚房费配置（酒店级 + 租户级默认两层）
    # tenants 默认关闭，server_default=0 保证历史行不违反 NOT NULL
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'noshow_charge_first_night',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )

    with op.batch_alter_table('hotels', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('noshow_charge_first_night', sa.Boolean(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('hotels', schema=None) as batch_op:
        batch_op.drop_column('noshow_charge_first_night')

    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.drop_column('noshow_charge_first_night')
