"""m30_bill_item_business_date

Revision ID: baea576c411d
Revises: 0848a1f0aa35
Create Date: 2026-09-08 09:56:19.313085
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'baea576c411d'
down_revision: Union[str, None] = '0848a1f0aa35'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 新增营业日列（M30：替换夜审 LIKE 判重为等值匹配）
    op.add_column('bill_items', sa.Column('business_date', sa.String(length=10), nullable=True))

    # 2. 历史数据回填：房租条目 description 形如「房租 YYYY-MM-DD」，取末 10 位即为营业日
    op.execute("UPDATE bill_items SET business_date = SUBSTR(description, -10) WHERE type='ROOM_CHARGE'")

    # 3. 复合索引：账单+类型+营业日，支撑夜审判重走索引等值命中
    op.create_index('ix_bill_items_bill_type_date', 'bill_items', ['bill_id', 'type', 'business_date'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_bill_items_bill_type_date', table_name='bill_items')
    op.drop_column('bill_items', 'business_date')
