"""M18 开放 API 平台：应用、API Key、Webhook 订阅与投递记录。

设计要点：
- 租户内应用唯一编码 app_code；
- API Key 明文仅创建时返回一次，库存储 sha256 hash；
- Webhook 订阅按 topic 过滤，支持 HMAC-SHA256 签名；
- 投递记录留痕，支撑失败重试与对账。
"""

from __future__ import annotations

import json

from sqlalchemy import ForeignKey, BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class OpenApiApp(Base, IntPkMixin, TenantMixin, TimestampMixin):
    """第三方应用注册。"""

    __tablename__ = "openapi_apps"

    app_code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    callback_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    _events_subscribed: Mapped[str | None] = mapped_column(
        "events_subscribed", String(1024), nullable=True, default="[]"
    )  # JSON list of topic filters

    @property
    def events_subscribed(self) -> list[str]:
        try:
            return json.loads(self._events_subscribed or "[]")
        except json.JSONDecodeError:
            return []

    @events_subscribed.setter
    def events_subscribed(self, value: list[str] | None) -> None:
        self._events_subscribed = json.dumps(value or [])

    keys: Mapped[list["OpenApiKey"]] = relationship(
        "OpenApiKey", back_populates="app", lazy="selectin", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list["WebhookSubscription"]] = relationship(
        "WebhookSubscription", back_populates="app", lazy="selectin", cascade="all, delete-orphan"
    )


class OpenApiKey(Base, IntPkMixin, TimestampMixin):
    """应用 API Key：明文仅在创建时返回。"""

    __tablename__ = "openapi_keys"

    app_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("openapi_apps.id"), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    key_mask: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    revoked_at: Mapped[str | None] = mapped_column(String(32), nullable=True)

    app: Mapped["OpenApiApp"] = relationship("OpenApiApp", back_populates="keys")


class WebhookSubscription(Base, IntPkMixin, TenantMixin, TimestampMixin):
    """Webhook 订阅：应用按 topic 维度订阅事件。"""

    __tablename__ = "openapi_webhook_subscriptions"

    app_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("openapi_apps.id"), nullable=False)
    topic: Mapped[str] = mapped_column(String(128), nullable=False)  # exact topic or "*"
    endpoint_url: Mapped[str] = mapped_column(String(512), nullable=False)
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)

    app: Mapped["OpenApiApp"] = relationship("OpenApiApp", back_populates="subscriptions")
    deliveries: Mapped[list["WebhookDelivery"]] = relationship(
        "WebhookDelivery", back_populates="subscription", lazy="selectin", cascade="all, delete-orphan"
    )


class WebhookDelivery(Base, IntPkMixin, TimestampMixin):
    """Webhook 投递记录。"""

    __tablename__ = "openapi_webhook_deliveries"

    subscription_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("openapi_webhook_subscriptions.id"), nullable=False
    )
    event_topic: Mapped[str] = mapped_column(String(128), nullable=False)
    event_payload: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    attempted_at: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)

    subscription: Mapped["WebhookSubscription"] = relationship(
        "WebhookSubscription", back_populates="deliveries"
    )
