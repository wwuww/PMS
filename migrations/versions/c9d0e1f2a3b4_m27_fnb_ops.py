"""M27 餐饮运营深度：沽清 + 退菜 + 整单折扣。

- menu_items 加 sold_out（沽清 0/1）
- pos_order_items 加 voided / void_reason（退菜）
- pos_orders 加 discount_cents（整单折扣，分）

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "menu_items", sa.Column("sold_out", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "pos_order_items", sa.Column("voided", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "pos_order_items",
        sa.Column("void_reason", sa.String(128), nullable=True),
    )
    op.add_column(
        "pos_orders",
        sa.Column("discount_cents", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("pos_orders", "discount_cents")
    op.drop_column("pos_order_items", "void_reason")
    op.drop_column("pos_order_items", "voided")
    op.drop_column("menu_items", "sold_out")
