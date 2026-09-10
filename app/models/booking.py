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
        # 批次②：客源/会员检索
        Index("ix_bookings_tenant_source", "tenant_id", "guest_source_type"),
        Index("ix_bookings_tenant_member", "tenant_id", "member_no"),
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
    # ── 批次② 核心实体字段补全（维也纳字典对齐，全 additive）──
    guest_source_type: Mapped[str] = mapped_column(String(20), default="WI", nullable=False)  # WI上门/IM个人会员/CM公司会员/LP长包/GP团队/AM中介协议
    member_no: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 会员号/协议号
    member_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 会员类型
    is_vip: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # VIP
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 信息保密
    is_quick_depart: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 无停留离店
    is_print_real_price: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 打印真价
    is_add_point: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 计积分
    is_guarantee: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 是否担保（应触发预授权/押金）
    guarantee_hold_until: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 最长保留到（ISO8601）
    guarantor: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 担保人
    sales_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 销售员
    activity_code: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 活动编号
    upgrade_room_type_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("room_types.id", name="fk_bookings_upgrade_room_type_id_room_types"), nullable=True)  # 升级房型
    group_name: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 团队名称
    group_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 团队类型
    group_leader: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 团队领队
    group_tel: Mapped[str | None] = mapped_column(String(32), nullable=True)  # 领队电话
    email: Mapped[str | None] = mapped_column(String(128), nullable=True)  # 邮箱
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 国家（PSB 涉外上报）

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


class StayExtension(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """续住记录（M37-③）。

    每次 ``booking_service.extend_stay`` 落一条 WORM 记录（``is_valid`` 撤销置 false，
    不物理删）。``added_amount_cents`` 为本次续住新增房费（分），存在 OPEN 账单时由
    service 写 ``BillItem(ROOM_CHARGE, +added_amount)`` 累加 ``Bill.balance``。
    """

    __tablename__ = "stay_extensions"

    __table_args__ = (
        Index("ix_stay_ext_tenant_booking", "tenant_id", "booking_id"),
        Index("ix_stay_ext_tenant_bizdate", "tenant_id", "business_date"),
    )

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False)
    booking_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("bookings.id"), nullable=False)
    room_no: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bill_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("bills.id"), nullable=True)
    business_date: Mapped[str] = mapped_column(String(10), nullable=False)
    start_date: Mapped[str] = mapped_column(String(10), nullable=False)
    end_date: Mapped[str] = mapped_column(String(10), nullable=False)
    nights: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    added_amount_cents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    operator: Mapped[str] = mapped_column(String(64), nullable=False, default="front_desk")
