"""M37 批次②：核心实体字段补全（维也纳数据字典对齐）。

- room_types 加 bed_number / short_name / en_name / descript / is_valid
- rooms 加 building_id / telephone / room_card_no / room_name / memo / is_valid
  + 索引 ix_rooms_tenant_building
- bookings 加 19 个字段（客源/会员/担保/团队/涉外等）
  + 索引 ix_bookings_tenant_source / ix_bookings_tenant_member
- guests 加 8 个字段（英文名/籍贯/民族/证件签发机关与有效期/头像等）
- members 加 member_no / card_type / join_date
  （member_no 唯一性在 service 层校验，避免 SQLite batch 加唯一约束的命名限制）
- rate_codes 加 stay_class / rate_type / valid_from / valid_to / is_overlay / week

全部 additive（nullable 或带 server_default），不删列、不改列类型、不改非空约束。
布尔列统一 server_default=sa.text("1"/"0")，规避 MySQL/SQLite 差异。

Revision ID: 3a7b9c2d4e6f
Revises: f2fa79c0e2e8
Create Date: 2026-09-07
"""

from alembic import op
import sqlalchemy as sa

revision = "3a7b9c2d4e6f"
down_revision = "f2fa79c0e2e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("room_types") as b:
        b.add_column(sa.Column("bed_number", sa.Integer(), nullable=False, server_default="1"))
        b.add_column(sa.Column("short_name", sa.String(32), nullable=True))
        b.add_column(sa.Column("en_name", sa.String(64), nullable=True))
        b.add_column(sa.Column("descript", sa.String(128), nullable=True))
        b.add_column(sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("1")))

    with op.batch_alter_table("rooms") as b:
        b.add_column(sa.Column("building_id", sa.String(32), nullable=True))
        b.add_column(sa.Column("telephone", sa.String(16), nullable=True))
        b.add_column(sa.Column("room_card_no", sa.String(50), nullable=True))
        b.add_column(sa.Column("room_name", sa.String(32), nullable=True))
        b.add_column(sa.Column("memo", sa.String(128), nullable=True))
        b.add_column(sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("1")))
        b.create_index("ix_rooms_tenant_building", ["tenant_id", "building_id"])

    with op.batch_alter_table("bookings") as b:
        b.add_column(sa.Column("guest_source_type", sa.String(20), nullable=False, server_default="WI"))
        b.add_column(sa.Column("member_no", sa.String(32), nullable=True))
        b.add_column(sa.Column("member_type", sa.String(32), nullable=True))
        b.add_column(sa.Column("is_vip", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        b.add_column(sa.Column("is_secret", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        b.add_column(sa.Column("is_quick_depart", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        b.add_column(sa.Column("is_print_real_price", sa.Boolean(), nullable=False, server_default=sa.text("1")))
        b.add_column(sa.Column("is_add_point", sa.Boolean(), nullable=False, server_default=sa.text("1")))
        b.add_column(sa.Column("is_guarantee", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        b.add_column(sa.Column("guarantee_hold_until", sa.String(32), nullable=True))
        b.add_column(sa.Column("guarantor", sa.String(64), nullable=True))
        b.add_column(sa.Column("sales_id", sa.String(64), nullable=True))
        b.add_column(sa.Column("activity_code", sa.String(32), nullable=True))
        b.add_column(sa.Column("upgrade_room_type_id", sa.BigInteger(), sa.ForeignKey("room_types.id", name="fk_bookings_upgrade_room_type_id_room_types"), nullable=True))
        b.add_column(sa.Column("group_name", sa.String(128), nullable=True))
        b.add_column(sa.Column("group_type", sa.String(32), nullable=True))
        b.add_column(sa.Column("group_leader", sa.String(64), nullable=True))
        b.add_column(sa.Column("group_tel", sa.String(32), nullable=True))
        b.add_column(sa.Column("email", sa.String(128), nullable=True))
        b.add_column(sa.Column("country", sa.String(64), nullable=True))
        b.create_index("ix_bookings_tenant_source", ["tenant_id", "guest_source_type"])
        b.create_index("ix_bookings_tenant_member", ["tenant_id", "member_no"])

    with op.batch_alter_table("guests") as b:
        b.add_column(sa.Column("en_name", sa.String(64), nullable=True))
        b.add_column(sa.Column("native_place", sa.String(64), nullable=True))
        b.add_column(sa.Column("nation", sa.String(32), nullable=True))
        b.add_column(sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.text("1")))
        b.add_column(sa.Column("come_time", sa.String(32), nullable=True))
        b.add_column(sa.Column("head_url", sa.String(255), nullable=True))
        b.add_column(sa.Column("id_doc_sign_org", sa.String(128), nullable=True))
        b.add_column(sa.Column("id_doc_valid_to", sa.String(10), nullable=True))

    with op.batch_alter_table("members") as b:
        b.add_column(sa.Column("member_no", sa.String(32), nullable=True))
        b.add_column(sa.Column("card_type", sa.String(32), nullable=True))
        b.add_column(sa.Column("join_date", sa.String(10), nullable=True))

    with op.batch_alter_table("rate_codes") as b:
        b.add_column(sa.Column("stay_class", sa.String(8), nullable=False, server_default="DR"))
        b.add_column(sa.Column("rate_type", sa.String(16), nullable=False, server_default="MULTIPLIER"))
        b.add_column(sa.Column("valid_from", sa.String(10), nullable=True))
        b.add_column(sa.Column("valid_to", sa.String(10), nullable=True))
        b.add_column(sa.Column("is_overlay", sa.Boolean(), nullable=False, server_default=sa.text("0")))
        b.add_column(sa.Column("week", sa.String(32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("rate_codes") as b:
        b.drop_column("week")
        b.drop_column("is_overlay")
        b.drop_column("valid_to")
        b.drop_column("valid_from")
        b.drop_column("rate_type")
        b.drop_column("stay_class")

    with op.batch_alter_table("members") as b:
        b.drop_column("join_date")
        b.drop_column("card_type")
        b.drop_column("member_no")

    with op.batch_alter_table("guests") as b:
        b.drop_column("id_doc_valid_to")
        b.drop_column("id_doc_sign_org")
        b.drop_column("head_url")
        b.drop_column("come_time")
        b.drop_column("is_valid")
        b.drop_column("nation")
        b.drop_column("native_place")
        b.drop_column("en_name")

    with op.batch_alter_table("bookings") as b:
        b.drop_index("ix_bookings_tenant_member")
        b.drop_index("ix_bookings_tenant_source")
        b.drop_column("country")
        b.drop_column("email")
        b.drop_column("group_tel")
        b.drop_column("group_leader")
        b.drop_column("group_type")
        b.drop_column("group_name")
        b.drop_column("upgrade_room_type_id")
        b.drop_column("activity_code")
        b.drop_column("sales_id")
        b.drop_column("guarantor")
        b.drop_column("guarantee_hold_until")
        b.drop_column("is_guarantee")
        b.drop_column("is_add_point")
        b.drop_column("is_print_real_price")
        b.drop_column("is_quick_depart")
        b.drop_column("is_secret")
        b.drop_column("is_vip")
        b.drop_column("member_type")
        b.drop_column("member_no")
        b.drop_column("guest_source_type")

    with op.batch_alter_table("rooms") as b:
        b.drop_index("ix_rooms_tenant_building")
        b.drop_column("is_valid")
        b.drop_column("memo")
        b.drop_column("room_name")
        b.drop_column("room_card_no")
        b.drop_column("telephone")
        b.drop_column("building_id")

    with op.batch_alter_table("room_types") as b:
        b.drop_column("is_valid")
        b.drop_column("descript")
        b.drop_column("en_name")
        b.drop_column("short_name")
        b.drop_column("bed_number")
