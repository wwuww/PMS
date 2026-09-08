"""审计日志（DEC-04 WORM 审计的前置落地，dev-plan BLK-04）。

记录所有敏感操作（改价/取消单/折扣/冲账/导出/登录等），留痕不可篡改；
查询接口（audit.view 权限）即导出能力（M8-2）。
"""

from datetime import UTC, datetime

from sqlalchemy import BigInteger, JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPkMixin, TenantMixin


class AuditLog(IntPkMixin, TenantMixin, Base):
    __tablename__ = "audit_logs"

    hotel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), default="", index=True)
    resource_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result: Mapped[str] = mapped_column(String(16), default="success")  # success|failure
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
