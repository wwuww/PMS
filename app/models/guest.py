"""宾客档案 / 客史模型（M14，FR-GUEST）。

区别于会员 CRM（members，储值/积分体系）：宾客档案覆盖所有到店客人
（散客 + 会员），记录证件、联系方式、偏好标签与累计客史，是绿云前台
「宾客档案」的统一视图。会员可通过 member_id 关联，但建档不强制会员身份。
"""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class Guest(IntPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "guests"
    # 同一租户内手机号去重（散客无手机号时允许多条空值，故不强制 NOT NULL）
    # M30 性能：id_no 此前零索引（3 处查询全表扫描），补 tenant_id 前导复合索引
    __table_args__ = (
        UniqueConstraint("tenant_id", "phone"),
        Index("ix_guests_tenant_idno", "tenant_id", "id_no"),
    )

    hotel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("hotels.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    id_type: Mapped[Optional[str]] = mapped_column(
        String(8), nullable=True, default="ID"
    )  # ID|PASSPORT|OFFICER|OTHER
    id_no: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    vip_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="NORMAL"
    )  # NORMAL|SILVER|GOLD|PLATINUM|DIAMOND
    gender: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)  # M|F
    birthday: Mapped[Optional[object]] = mapped_column(Date, nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # 客史标签：JSON 数组，如 ["高楼层","无烟房","安静房"]
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 偏好/备注
    stay_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 累计入住次数
    total_spend: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 累计消费（分）
    member_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("members.id"), nullable=True, index=True
    )
    # ── 批次② 字段补全（维也纳字典对齐，全 additive）──
    en_name: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 英文名
    native_place: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 籍贯
    nation: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 民族
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 是否有效
    come_time: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 最近来店时间（ISO8601）
    head_url: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 头像地址
    id_doc_sign_org: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 证件签发机关
    id_doc_valid_to: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 证件有效期至 YYYY-MM-DD

    @property
    def tag_list(self) -> list[str]:
        if not self.tags:
            return []
        try:
            data = json.loads(self.tags)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    def set_tags(self, values: list[str]) -> None:
        self.tags = json.dumps(list(values or []), ensure_ascii=False)
