"""M0-D1 房型 / 价格日历补门店维度（多店独立定价与独立房量的地基）。

背景：二店 1 个月内开业（2026-09-16 首次可售），但多店维度只做了一半——
``Room``/``Booking`` 已有 ``hotel_id``，而 ``room_types`` / ``price_calendar``
仍是租户级，且房量聚合查询不过滤门店 → 二店开业当天必然「房量算上一店」「房价串店」。

本迁移做三件事：
1. ``room_types`` 加 ``hotel_id``；唯一约束 ``(tenant_id, code)``
   → ``(tenant_id, hotel_id, code)``（允许两店各建同名房型）。
2. ``price_calendar`` 加 ``hotel_id``；唯一约束 ``(tenant_id, room_type_id, date)``
   → ``(tenant_id, hotel_id, room_type_id, date)``（两店同日同房型各自定价）。
3. 回填：现有房型 / 价格覆盖全部归属「其租户下的默认门店」（按 hotels.id 升序第一家）。

⚠️ SQLite 约束命名：本库的历史唯一约束是**匿名**创建（``UNIQUE (tenant_id, code)``
建出 ``sqlite_autoindex_*``），SQLAlchemy 反射时按批处理命名约定命名。
沿用仓库既有先例（``b8c9d0e1f2a3_m24_ar_hourly.py``）的 ``naming_convention``，
故旧约束的反射名 = ``uq_<table>_<首列>``：
- room_types   UNIQUE(tenant_id, code)            → ``uq_room_types_tenant_id``
- price_calendar UNIQUE(tenant_id, room_type_id, date) → ``uq_price_calendar_tenant_id``

回填策略：若某租户下有房型/价格但**没有任何门店**，迁移**主动报错中止**，
避免静默写入错误的 ``hotel_id``（宁可迁移失败，不可脏写）。

``down_revision`` 指向 M37 末位 ``d7e8f9a0b1c2``。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "j8e9f0a1b2c3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None

# 与 b8c9d0e1f2a3 / m24 迁移一致的命名约定：让反射出的匿名约束可被命名/引用
_NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _backfill_hotel_id(table: str, *, via_room_type: bool) -> None:
    """把 ``table`` 的 ``hotel_id`` 回填为「其租户下的第一门店」。

    ``via_room_type=True`` 时（price_calendar），跟随其所属房型的门店，
    保证 price_calendar.hotel_id 与 room_types.hotel_id 一致。
    """
    conn = op.get_bind()

    # 0) 一致性体检：有数据但无门店的租户 → 中止（不脏写）
    orphans = conn.execute(
        sa.text(
            f"""
            SELECT DISTINCT rt.tenant_id
            FROM {table} t JOIN room_types rt ON rt.id = t.room_type_id
            WHERE NOT EXISTS (SELECT 1 FROM hotels h WHERE h.tenant_id = rt.tenant_id)
            """
            if via_room_type
            else f"""
            SELECT DISTINCT t.tenant_id
            FROM {table} t
            WHERE NOT EXISTS (SELECT 1 FROM hotels h WHERE h.tenant_id = t.tenant_id)
            """
        )
    ).fetchall()
    if orphans:
        names = ", ".join(sorted(str(r[0]) for r in orphans))
        raise RuntimeError(
            f"[D1] 迁移中止：以下租户有 {table} 数据但没有任何门店，"
            f"无法确定 hotel_id 归属：{names}。请先补建门店或清理脏数据。"
        )

    if via_room_type:
        conn.execute(
            sa.text(
                f"""
                UPDATE {table}
                SET hotel_id = (
                    SELECT rt.hotel_id FROM room_types rt
                    WHERE rt.id = {table}.room_type_id
                )
                WHERE hotel_id IS NULL
                """
            )
        )
    else:
        conn.execute(
            sa.text(
                f"""
                UPDATE {table}
                SET hotel_id = (
                    SELECT h.id FROM hotels h
                    WHERE h.tenant_id = {table}.tenant_id
                    ORDER BY h.id
                    LIMIT 1
                )
                WHERE hotel_id IS NULL
                """
            )
        )

    remaining = conn.execute(
        sa.text(f"SELECT COUNT(*) FROM {table} WHERE hotel_id IS NULL")
    ).scalar()
    if remaining:
        raise RuntimeError(f"[D1] 迁移中止：{table} 仍有 {remaining} 行未回填 hotel_id。")


def upgrade() -> None:
    # ---------- 1) room_types ----------
    # 1a. 加 nullable 列 + 索引（SQLite 不能直接给已有表加无默认的 NOT NULL 列）
    with op.batch_alter_table("room_types", schema=None, naming_convention=_NAMING) as batch_op:
        batch_op.add_column(sa.Column("hotel_id", sa.BigInteger(), nullable=True))
        batch_op.create_index("ix_room_types_hotel_id", ["hotel_id"])
        # batch 模式（SQLite 走「建新表 + 拷数据」）要求约束必须显式命名，
        # 故不用 sa.ForeignKey 匿名形式，改用 create_foreign_key 命名创建。
        batch_op.create_foreign_key(
            "fk_room_types_hotel_id_hotels", "hotels", ["hotel_id"], ["id"]
        )

    # 1b. 回填（必须在加 NOT NULL 之前）
    _backfill_hotel_id("room_types", via_room_type=False)

    # 1c. 换约束：旧匿名 UNIQUE 名 = uq_room_types_tenant_id（首列 tenant_id）
    with op.batch_alter_table("room_types", schema=None, naming_convention=_NAMING) as batch_op:
        batch_op.drop_constraint("uq_room_types_tenant_id", type_="unique")
        batch_op.alter_column("hotel_id", existing_type=sa.BigInteger(), nullable=False)
        batch_op.create_unique_constraint(
            "uq_room_types_tenant_hotel_code", ["tenant_id", "hotel_id", "code"]
        )

    # ---------- 2) price_calendar ----------
    with op.batch_alter_table("price_calendar", schema=None, naming_convention=_NAMING) as batch_op:
        batch_op.add_column(sa.Column("hotel_id", sa.BigInteger(), nullable=True))
        batch_op.create_index("ix_price_calendar_hotel_id", ["hotel_id"])
        batch_op.create_foreign_key(
            "fk_price_calendar_hotel_id_hotels", "hotels", ["hotel_id"], ["id"]
        )

    _backfill_hotel_id("price_calendar", via_room_type=True)

    with op.batch_alter_table("price_calendar", schema=None, naming_convention=_NAMING) as batch_op:
        batch_op.drop_constraint("uq_price_calendar_tenant_id", type_="unique")
        batch_op.alter_column("hotel_id", existing_type=sa.BigInteger(), nullable=False)
        batch_op.create_unique_constraint(
            "uq_price_calendar_tenant_hotel_roomtype_date",
            ["tenant_id", "hotel_id", "room_type_id", "date"],
        )


def downgrade() -> None:
    """回退到 M37 末位状态。

    ⚠️ 恢复的旧唯一约束必须用**与 upgrade 端 drop 时相同的名字**
    （``uq_room_types_tenant_id`` / ``uq_price_calendar_tenant_id``）。
    因为 upgrade 靠命名约定定位匿名约束；若 downgrade 用别的名字重建，
    「降级后再升级」会因找不到 ``uq_room_types_tenant_id`` 而失败（往返不可逆）。
    """
    # ---------- 2) price_calendar ----------
    with op.batch_alter_table("price_calendar", schema=None, naming_convention=_NAMING) as batch_op:
        batch_op.drop_constraint("uq_price_calendar_tenant_hotel_roomtype_date", type_="unique")
        batch_op.create_unique_constraint("uq_price_calendar_tenant_id", ["tenant_id", "room_type_id", "date"])
        batch_op.drop_index("ix_price_calendar_hotel_id")
        batch_op.drop_column("hotel_id")

    # ---------- 1) room_types ----------
    with op.batch_alter_table("room_types", schema=None, naming_convention=_NAMING) as batch_op:
        batch_op.drop_constraint("uq_room_types_tenant_hotel_code", type_="unique")
        batch_op.create_unique_constraint("uq_room_types_tenant_id", ["tenant_id", "code"])
        batch_op.drop_index("ix_room_types_hotel_id")
        batch_op.drop_column("hotel_id")
