"""店长 App 模型（M10，FR-APP）：移动审批 / 清扫工单 / 消息推送。"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class ApprovalTicket(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """移动审批单（M10-2，FR-APP-02）：折扣/冲账/超额预订/退款，审批≤2步。"""

    __tablename__ = "approval_tickets"

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # DISCOUNT|ADJUST|OVERBOOK|REFUND
    payload: Mapped[dict] = mapped_column(JSON, default=dict)  # 审批通过后的执行参数
    reason: Mapped[str] = mapped_column(String(256), default="")
    applicant: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)  # PENDING|APPROVED|REJECTED
    approver: Mapped[str | None] = mapped_column(String(64))
    decision_note: Mapped[str | None] = mapped_column(String(256))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ref_id: Mapped[int | None] = mapped_column(Integer)  # 执行落点（如 bill_id）


class HousekeepingTask(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """清扫/维修工单（M10-3，FR-APP-03 / FR-FT-04）：退房自动建单，完成联动净房。"""

    __tablename__ = "housekeeping_tasks"

    # M30 性能：list_tasks 是保洁/主管首页高频接口且无 limit；
    # 本索引覆盖 list_tasks 及 187/253/293 三处查询（分片键 tenant_id 前导）。
    __table_args__ = (Index("ix_hk_tenant_hotel_status", "tenant_id", "hotel_id", "status"),)

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    room_no: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(16), default="CLEANUP")  # CLEANUP|MAINTENANCE|INSPECT
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)  # PENDING|ASSIGNED|DONE|CANCELLED
    assignee: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16), default="MANUAL")  # AUTO_CHECKOUT|MANUAL
    note: Mapped[str] = mapped_column(String(256), default="")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Notification(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """站内消息推送（M10-4，FR-APP-04）：日报推送/审批待办提醒，已读回执。"""

    __tablename__ = "notifications"

    hotel_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=True, index=True)
    recipient: Mapped[str] = mapped_column(String(64), default="store_manager")
    channel: Mapped[str] = mapped_column(String(16), default="APP")  # APP|SMS（预留）
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    body: Mapped[str] = mapped_column(String(512), default="")
    ref_type: Mapped[str | None] = mapped_column(String(32))  # daily_report|approval|task...
    # 128 分库：ref_id 指向实体雪花 ID（巨整数），须用 BigInteger 否则 MySQL INT 溢出
    ref_id: Mapped[int | None] = mapped_column(BigInteger)
    # ③ 通知分级：critical 突破免打扰，normal 普通待办，info 提示/日报
    level: Mapped[str] = mapped_column(String(16), default="normal", index=True)
    # ③ 免打扰：处于租户免打扰时段且 level 非 critical 时置 True（不计入未读角标）
    muted: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 前端深链（点击消息直达业务页），形如 /reports?date=2026-09-03&type=dashboard
    link: Mapped[str | None] = mapped_column(String(255))
    # ④ 多接收人：本通知的最终接收角色列表（如 ["store_manager","front_desk"]）。
    # 由 push 按 ref_type 解析租户订阅配置后落库；缺订阅时回落为单 recipient。
    recipients: Mapped[list] = mapped_column(JSON, default=list)


class NotificationPreference(IntPkMixin, TenantMixin, Base):
    """通知偏好（③ 免打扰）：每租户一行，配置安静时段与突破级别。"""

    __tablename__ = "notification_preferences"

    dnd_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # 安静时段起止（本地 HH:MM），支持跨午夜（如 22:00–08:00）
    dnd_start: Mapped[str] = mapped_column(String(5), default="22:00")
    dnd_end: Mapped[str] = mapped_column(String(5), default="08:00")


class NotificationSubscription(IntPkMixin, TenantMixin, Base):
    """④ 角色订阅配置：每租户每个 ref_type 一行，配置哪些角色接收该类通知。

    与 ② 的 REF_LINK_TEMPLATES / ③ 的分级免打扰正交：本表决定「谁收到」，
    分级决定「重要程度」，免打扰决定「何时不打扰」。缺配置时由
    NotificationService.DEFAULT_SUBSCRIBERS 回落到历史单接收人语义。
    """

    __tablename__ = "notification_subscriptions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "ref_type", name="uq_sub_tenant_ref"),
    )

    ref_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 接收角色列表（自由字符串，如 "store_manager"/"front_desk"），空列表=无推送
    recipients: Mapped[list] = mapped_column(JSON, default=list)


class Complaint(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """投诉工单（M28，A2 收尾）：与住客/预订强关联，处理流转闭环。"""

    __tablename__ = "complaints"

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    booking_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("bookings.id"), nullable=True, index=True)
    guest_name: Mapped[str] = mapped_column(String(64), nullable=False)
    guest_phone: Mapped[str | None] = mapped_column(String(32), index=True)
    room_no: Mapped[str | None] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(16), default="FRONT_DESK")  # FRONT_DESK|PHONE|APP|OTA
    category: Mapped[str] = mapped_column(String(32), default="SERVICE")  # SERVICE|FACILITY|HYGIENE|NOISE|BILLING|OTHER
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)  # OPEN|HANDLING|RESOLVED|CANCELLED
    description: Mapped[str] = mapped_column(String(512), default="")
    handler: Mapped[str | None] = mapped_column(String(64))
    resolution: Mapped[str | None] = mapped_column(String(512))
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportSnapshot(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """周报/月报快照（M32，验收 #14）：夜审周期切换时固化经营指标，防重算漂移。"""

    __tablename__ = "report_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "hotel_id", "period_type", "period_start",
            name="ix_report_snapshots_tenant_hotel_period",
        ),
    )

    hotel_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=False, index=True)
    period_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # WEEKLY|MONTHLY
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    metrics: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # dashboard 聚合 JSON
    source: Mapped[str] = mapped_column(String(16), default="AUTO")  # AUTO(夜审)|MANUAL
