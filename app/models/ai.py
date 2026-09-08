"""AI 服务模型（M11/M12）：智能客服会话与对账预警。"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntPkMixin, TenantMixin, TimestampMixin


class ChatSession(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """M11 AI 客服会话。

    支持多渠道接入（wechat_mp/app/web），记录会话状态与满意度。
    """

    __tablename__ = "chat_sessions"

    channel: Mapped[str] = mapped_column(String(16), default="wechat_mp")  # wechat_mp|mini_app|web
    guest_name: Mapped[str | None] = mapped_column(String(64))
    guest_phone: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="bot")  # bot|handoff|closed
    intent: Mapped[str | None] = mapped_column(String(32))  # 最后识别到的意图
    satisfaction: Mapped[int | None] = mapped_column(default=None)  # 1-5 星
    handoff_reason: Mapped[str | None] = mapped_column(String(128))

    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )


class ChatMessage(IntPkMixin, TimestampMixin, Base):
    """M11 单条会话消息。"""

    __tablename__ = "chat_messages"

    session_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user|bot|human|system
    content: Mapped[str] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[float | None] = mapped_column(default=None)  # 0-1

    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")


class AlertNotification(IntPkMixin, TenantMixin, TimestampMixin, Base):
    """M12 AI 自动对账预警。

    独立模型便于后续扩展聚合/降噪/机器学习标记。
    """

    __tablename__ = "alert_notifications"

    hotel_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("hotels.id"), nullable=True, index=True)
    alert_type: Mapped[str] = mapped_column(String(32), index=True)  # amount_anomaly|duplicate_payment|missed_revenue|commission_diff|overage|shortage
    severity: Mapped[str] = mapped_column(String(16), default="warning")  # info|warning|critical
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text)
    ref_type: Mapped[str | None] = mapped_column(String(32))
    ref_id: Mapped[str | None] = mapped_column(String(64))  # 外部 ID 或本地 id 字符串化
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|acknowledged|resolved|false_positive
    suggested_action: Mapped[str | None] = mapped_column(String(256))
