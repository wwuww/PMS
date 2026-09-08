"""OTA 渠道直连模型（M29，A5）：渠道配置 + 外部订单幂等回链 + 房型映射 + 价格计划 + 推送日志。"""

from __future__ import annotations

from sqlalchemy import BigInteger, Date, DateTime, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class OtaChannelConfig(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """OTA 渠道接入配置（每租户每渠道一条）：签名密钥与推送开关。"""

    __tablename__ = "ota_channel_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel", name="uq_ota_tenant_channel"),
    )

    hotel_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)  # ota_ctrip|ota_meituan|ota_fliggy|sandbox
    app_key: Mapped[str] = mapped_column(String(64), default="")
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    push_enabled: Mapped[int] = mapped_column(Integer, default=1)  # 0/1 房量推送开关
    push_inventory_url: Mapped[str | None] = mapped_column(String(256))  # 真实渠道推送端点（沙箱可空）


class ChannelRoomMapping(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """OTA 房型映射：每渠道每酒店每 PMS 房型一行，定义 OTA 侧房型代码。

    - 唯一约束：(tenant_id, hotel_id, channel, pms_room_type_id)
    - external_room_type_code 用于 webhook 注入时反查 PMS 房型；
      也用于房量/价格推送时把 PMS 房型转换为渠道房型码。
    """

    __tablename__ = "channel_room_mappings"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "hotel_id", "channel", "pms_room_type_id",
            name="uq_chmap_tenant_hotel_channel_pms",
        ),
        Index(
            "ix_chmap_lookup",
            "tenant_id", "hotel_id", "channel", "external_room_type_code",
        ),
    )

    hotel_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    pms_room_type_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    external_room_type_code: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[int] = mapped_column(Integer, default=1)


class ChannelRatePlan(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """OTA 渠道价（按房型生效日覆盖 PMS base_price）。

    - 唯一约束：(tenant_id, hotel_id, channel, pms_room_type_id, effective_date)
    - price_cents 单位为分；effective_date 可空（null = 永久默认）。
    """

    __tablename__ = "channel_rate_plans"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "hotel_id", "channel", "pms_room_type_id", "effective_date",
            name="uq_rate_tenant_hotel_channel_pms_date",
        ),
    )

    hotel_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    pms_room_type_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    effective_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[int] = mapped_column(Integer, default=1)


class ChannelPushLog(IntPkMixin, TenantMixin, Base):
    """OTA 房量/价格推送日志（每次 push_inventory 一行，便于前台日志 Tab 排查）。

    - 字段：渠道、酒店、推送范围（days）、状态（SUCCESS/FAILED/DRY_RUN）、
      请求摘要、响应摘要、错误信息、操作员、trace_id、耗时（ms）。
    """

    __tablename__ = "channel_push_logs"
    __table_args__ = (
        Index("ix_push_log_tenant_created", "tenant_id", "created_at"),
    )

    hotel_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    days: Mapped[int] = mapped_column(Integer, default=7)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="SUCCESS")
    trace_id: Mapped[str] = mapped_column(String(64), default="")
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    request_summary: Mapped[str] = mapped_column(Text, default="")
    response_summary: Mapped[str] = mapped_column(Text, default="")
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    operator: Mapped[str] = mapped_column(String(64), default="admin")
    created_at: Mapped[object] = mapped_column(DateTime, nullable=False)
