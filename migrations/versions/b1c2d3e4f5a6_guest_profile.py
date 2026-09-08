"""guest_profile

Revision ID: b1c2d3e4f5a6
Revises: ae16e2cfc5a2
Create Date: 2026-09-04 16:25:00.000000

宾客档案 / 客史模型（M14，FR-GUEST）：覆盖散客与会员的统一档案视图。
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = '271462418bcd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'guests',
        sa.Column('id', sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('hotel_id', sa.BigInteger(), sa.ForeignKey('hotels.id'), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False, server_default=''),
        sa.Column('phone', sa.String(length=32), nullable=True),
        sa.Column('id_type', sa.String(length=8), nullable=True, server_default='ID'),
        sa.Column('id_no', sa.String(length=32), nullable=True),
        sa.Column('vip_level', sa.String(length=16), nullable=False, server_default='NORMAL'),
        sa.Column('gender', sa.String(length=4), nullable=True),
        sa.Column('birthday', sa.Date(), nullable=True),
        sa.Column('email', sa.String(length=64), nullable=True),
        sa.Column('address', sa.String(length=128), nullable=True),
        sa.Column('tags', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('stay_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('total_spend', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('member_id', sa.BigInteger(), sa.ForeignKey('members.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['hotel_id'], ['hotels.id']),
        sa.ForeignKeyConstraint(['member_id'], ['members.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'phone'),
    )
    with op.batch_alter_table('guests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_guests_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_guests_hotel_id'), ['hotel_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_guests_phone'), ['phone'], unique=False)
        batch_op.create_index(batch_op.f('ix_guests_member_id'), ['member_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('guests', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_guests_member_id'))
        batch_op.drop_index(batch_op.f('ix_guests_phone'))
        batch_op.drop_index(batch_op.f('ix_guests_hotel_id'))
        batch_op.drop_index(batch_op.f('ix_guests_tenant_id'))
    op.drop_table('guests')
