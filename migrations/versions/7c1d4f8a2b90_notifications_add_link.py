"""notifications.link 通知中心点击跳转深链（M10-4 增强）

Revision ID: 7c1d4f8a2b90
Revises: 69a582a7c5cc
Create Date: 2026-09-04 07:20:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c1d4f8a2b90"
down_revision: Union[str, None] = "69a582a7c5cc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.add_column(sa.Column("link", sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("notifications", schema=None) as batch_op:
        batch_op.drop_column("link")
