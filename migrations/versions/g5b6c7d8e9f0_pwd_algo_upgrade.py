"""M32.18 阶段一：users 加 pwd_algo 列（M0-3 口令加固落库准备）。

- 存量行 pwd_algo='sha256'（即原 ``_hash_password`` 用 ``hashlib.sha256(salt+pwd)`` 那一档）。
- 登录时若检测到非 argon2id，由 ``RbacService`` 透明重哈希并写回；存量账号一个不丢。
- 向下兼容：column nullable=False + server_default 保证老数据也能落。

revision: g5b6c7d8e9f0
down_revision: f4a5b6c7d8e9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "g5b6c7d8e9f0"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "pwd_algo",
                sa.String(16),
                nullable=False,
                server_default=sa.text("'sha256'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("pwd_algo")
