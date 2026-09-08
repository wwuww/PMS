"""预订/订单模型（M2 预订引擎）。

状态机（M2）：CREATED（已订未到）→ CHECKED_IN（在住）→ CHECKED_OUT（已离）
                              ↘ CANCELLED（已取消）
创建时占用房型房量（库存由房量聚合推导，无独立计数器，避免并发竞态）；
入住时联动房态引擎锁定具体房间并转在住，退房联动转空脏。
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, BigInteger, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.channels.base import ChannelType
from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class BookingStatus(StrEnum):
    CREATED = "created"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    CANCELLED = "cancelled"
    NOSHOW = "noshow"  # 逾期应到未到（夜审自动标记 / 前台手动标记）


class Booking(IntPkMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "bookings"
    # M30：复合索引以 tenant_id 为前导（ShardingSphere 分片键 = tenant_id，无前导列会跨片广播）。
    # 旧 ix_bookings_hotel_checkin 无 tenant_id 前导，保留兼容历史迁移；
    # 新增同列 tenant_id 前导版本，优化器优先选更优者。
    __table_args__ = (
        Index("ix_bookings_hotel_checkin", "hotel_id", "check_in_date"),
        Index("ix_bookings_tenant_hotel_checkin", "tenant_id", "hotel_id", "check_in_date"),
        # 「按房号查在住单」四连（入住/联房/结转必经校验），收益极高
        Index("ix_bookings_tenant_status_room", "tenant_id", "status", "room_no"),
        # 夜审主循环
        Index("ix_bookings_hotel_room_status", "hotel_id", "room_no", "status"),
        # order_by(id desc) limit 1 → 索引尾部扫描，免 filesort
        Index("ix_bookings_tenant_room_id", "tenant_id", "room_no", "id"),
    )

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    room_type_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("room_types.id"), nullable=False, index=True)
    rate_code_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("rate_codes.id"))

    channel: Mapped[str] = mapped_column(String(32), default=ChannelType.DIRECT.value)
    # M29：OTA 直连外部订单回链（幂等键 = (tenant_id, external_channel, external_ref)）
    external_channel: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    external_ref: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    guest_name: Mapped[str] = mapped_column(String(64), nullable=False)
    guest_phone: Mapped[str | None] = mapped_column(String(32))
    id_doc_no: Mapped[str | None] = mapped_column(String(64))  # 证件号（PSB 涉外上报）

    check_in_date: Mapped[str] = mapped_column(String(10), nullable=False)   # YYYY-MM-DD
    check_out_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD
    room_no: Mapped[str | None] = mapped_column(String(16))  # 入住分配房号
    chat_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # AI 会话建单回链

    status: Mapped[str] = mapped_column(String(16), default=BookingStatus.CREATED.value, index=True)
    stay_type: Mapped[str] = mapped_column(String(8), default="daily")  # M24：daily|hourly（时租房）
    hourly_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)  # M24：时租时长（小时）
    # NoShow 原因：夜审自动标记写"逾期未到，夜审自动标记"，前台手动标记写人工原因
    noshow_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_price: Mapped[int | None] = mapped_column(Integer)  # 分
    extra_bed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 加床数
    companion_names: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 同住人姓名（JSON 数组）

    # M32.15：联房 —— 在住单之间联房（账务合并到主房场景）；各单保留自己的来离店日期
    link_group_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    is_link_master: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 主房标记
    hourly_start_time: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)  # M32.17b：钟点房到店时刻 HH:MM，离店=此时刻+hourly_hours

    @property
    def companion_list(self) -> list[str]:
        if not self.companion_names:
            return []
        try:
            data = json.loads(self.companion_names)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    def set_companions(self, values: list[str]) -> None:
        self.companion_names = json.dumps(list(values or []), ensure_ascii=False)

    @property
    def nights(self) -> int:
        """间夜数（按日期字符串差，ISO 格式可直接减）。"""
        ci = self.check_in_date
        co = self.check_out_date
        y1, m1, d1 = map(int, ci.split("-"))
        y2, m2, d2 = map(int, co.split("-"))
        from datetime import date

        return (date(y2, m2, d2) - date(y1, m1, d1)).days
