"""M31 核心缺口关闭：rooms.dnd 免打扰标记。

验收 #34：房态图需展示免打扰分类。DND 不影响可售状态，清扫派单守卫使用。

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("rooms") as batch:
        batch.add_column(sa.Column("dnd", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("rooms") as batch:
        batch.drop_column("dnd")
